"""
MediGuard AI – Background ECG Inference Worker
Processes asynchronous ECG inference jobs polled from the jobs queue.
Features:
- Transactional / thread-safe claiming with atomic state transitions
- Retries with exponential backoff and max attempts
- Dead worker recovery: timed-out processing jobs are re-queued
- Status updates: pending -> processing -> completed / failed
- Web requests never block on ML inference
Run worker via: python -m backend.worker.worker
"""
import sys
import io
import time
import signal
import logging
import argparse
from pathlib import Path
from typing import Tuple, Dict, Any, Optional
import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

from backend.services.db_service import db_service
from backend.services.storage_service import storage_service
from backend.services.inference_service import inference_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] (worker) %(message)s"
)
logger = logging.getLogger("mediguard.worker")

STANDARD_LEADS = ["I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"]


def parse_csv_ecg_bytes(csv_bytes: bytes) -> Tuple:
    """
    Parse uploaded CSV bytes into standard 12-lead numpy array (shape: 12, T).
    Supports:
    1. Column-oriented: headers contain lead names (I, II, III... or lead_0..lead_11)
    2. Row-oriented: 12 rows corresponding to 12 leads
    3. Unlabeled matrix with 12 columns
    """
    text_io = io.StringIO(csv_bytes.decode("utf-8", errors="replace"))
    df = pd.read_csv(text_io)

    # Clean column names
    col_map = {c: str(c).strip().upper() for c in df.columns}
    upper_cols = [col_map[c] for c in df.columns]

    lead_indices = []
    for lead in STANDARD_LEADS:
        lead_u = lead.upper()
        if lead_u in upper_cols:
            orig_col = [c for c, u in col_map.items() if u == lead_u][0]
            lead_indices.append(orig_col)

    if len(lead_indices) == 12:
        # All 12 standard leads matched by header
        signal = df[lead_indices].values.T.astype(np.float32)
    elif df.shape[1] >= 12:
        # First 12 columns
        signal = df.iloc[:, :12].values.T.astype(np.float32)
    elif df.shape[0] == 12:
        # 12 rows
        signal = df.values.astype(np.float32)
    else:
        raise ValueError(
            f"Invalid ECG CSV dimensions: {df.shape}. Expected 12 leads (columns or rows) representing "
            f"standard 12-lead channels ({', '.join(STANDARD_LEADS)})."
        )

    # Validate signal duration (minimum 250 samples / ~2.5s at 100Hz)
    if signal.shape[1] < 200:
        raise ValueError(f"Signal duration too short: {signal.shape[1]} samples. Minimum required is 200 samples.")

    return signal


def process_single_job(job: dict) -> bool:
    """Process a single claimed inference job."""
    job_id = job["id"]
    payload = job.get("payload", {})
    report_id = payload.get("report_id")
    patient_id = payload.get("patient_id")
    sampling_rate = float(payload.get("sampling_rate", 100.0))

    logger.info("Processing job %s for report %s (Attempt %d/%d)",
                job_id, report_id, job.get("attempts", 1), job.get("max_attempts", 3))

    try:
        report = db_service.get_ecg_report(report_id)
        if not report:
            raise ValueError(f"ECG Report {report_id} not found in database.")

        file_type = report.get("file_type", "")
        if file_type != "digital_12lead":
            logger.warning("Report %s is type '%s'. Skipping ML inference pipeline.", report_id, file_type)
            db_service.complete_job(job_id, {"skipped": True, "reason": "Non-ML file type"})
            return True

        # Retrieve file bytes from storage
        file_tuple = storage_service.get_file_bytes(report_id)
        if not file_tuple:
            raise FileNotFoundError(f"Storage file for report {report_id} not found.")

        file_bytes, filename, content_type = file_tuple

        # Parse CSV signal
        signal = parse_csv_ecg_bytes(file_bytes)

        # Run ResNet-1D inference
        analysis_result = inference_service.run_inference_on_signal(
            signal=signal,
            sampling_rate=sampling_rate,
            report_id=report_id
        )

        db_service.complete_job(job_id, {
            "model_version": analysis_result.get("model_version"),
            "signal_quality": analysis_result.get("signal_quality"),
            "is_demo": analysis_result.get("is_demo")
        })

        # Phase 5 Notification Dispatches
        try:
            from backend.services.notification_service import notification_service, NOTIFICATION_TYPES
            rep = db_service.get_ecg_report(report_id)
            if rep:
                notification_service.notify_cardiologists_for_patient(
                    patient_id=rep["patient_id"],
                    notif_type=NOTIFICATION_TYPES["ANALYSIS_COMPLETE"],
                    title=f"ECG Analysis Complete ({rep.get('file_name', '12-lead')})",
                    message="Model inference complete. Waveform & experimental scores ready for doctor review.",
                    severity="info",
                    entity_type="ecg_report",
                    entity_id=report_id,
                    deep_link=f"dashboard.html?report_id={report_id}"
                )
                scores = analysis_result.get("scores", {})
                mi_score = scores.get("MI", 0.0)
                sttc_score = scores.get("STTC", 0.0)
                if mi_score >= 0.65 or sttc_score >= 0.65:
                    notification_service.notify_cardiologists_for_patient(
                        patient_id=rep["patient_id"],
                        notif_type=NOTIFICATION_TYPES["CONCERNING_FINDING"],
                        title=f"Concerning Finding: Elevated Score ({'MI' if mi_score >= 0.65 else 'STTC'})",
                        message=f"Experimental score elevated ({max(mi_score, sttc_score):.2f}). Prompt doctor review recommended.",
                        severity="warning",
                        entity_type="ecg_report",
                        entity_id=report_id,
                        deep_link=f"dashboard.html?report_id={report_id}"
                    )
        except Exception as ne:
            logger.warning("Could not dispatch analysis notification: %s", ne)

        logger.info("Successfully completed inference job %s for report %s", job_id, report_id)
        return True

    except Exception as e:
        logger.error("Job %s failed on attempt %d: %s", job_id, job.get("attempts", 1), e)
        db_service.fail_job(job_id, str(e))
        db_service.update_ecg_report(report_id, {"status": "failed", "notes": f"Analysis failed: {str(e)}"})
        return False


class BackgroundWorker:
    def __init__(self, poll_interval: float = 1.0, timeout_seconds: int = 60):
        self.poll_interval = poll_interval
        self.timeout_seconds = timeout_seconds
        self.running = True

    def stop(self, *args):
        logger.info("Stopping worker gracefully...")
        self.running = False

    def run_once(self) -> int:
        """Process all currently pending jobs and return count processed."""
        processed = 0
        while True:
            job = db_service.claim_next_job(job_type="ecg_inference", timeout_seconds=self.timeout_seconds)
            if not job:
                break
            process_single_job(job)
            processed += 1
        return processed

    def run(self):
        """Continuous polling loop."""
        logger.info("MediGuard Background Worker started. Polling for ECG inference jobs...")
        signal.signal(signal.SIGINT, self.stop)
        signal.signal(signal.SIGTERM, self.stop)

        while self.running:
            job = db_service.claim_next_job(job_type="ecg_inference", timeout_seconds=self.timeout_seconds)
            if job:
                process_single_job(job)
            else:
                time.sleep(self.poll_interval)


def main():
    parser = argparse.ArgumentParser(description="MediGuard AI ECG Inference Worker")
    parser.add_argument("--once", action="store_true", help="Process pending jobs once and exit")
    parser.add_argument("--interval", type=float, default=1.0, help="Polling interval in seconds")
    parser.add_argument("--timeout", type=int, default=60, help="Job lock timeout for dead-worker recovery")
    args = parser.parse_args()

    worker = BackgroundWorker(poll_interval=args.interval, timeout_seconds=args.timeout)
    if args.once:
        count = worker.run_once()
        print(f"Processed {count} jobs.")
    else:
        worker.run()


if __name__ == "__main__":
    main()
