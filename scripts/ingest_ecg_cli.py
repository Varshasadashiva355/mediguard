"""
MediGuard AI – Direct ECG Ingestion CLI
Provides a direct, reliable command-line alternative to upload and analyze ECG files
without needing to interact with the browser modal or file picker.

Usage:
    python scripts/ingest_ecg_cli.py                          # Ingests Beatrice Campbell's 12-lead ECG
    python scripts/ingest_ecg_cli.py --file <path_to_file>   # Ingests specific ECG file
    python scripts/ingest_ecg_cli.py --patient MG-2026-000101 # Ingests for James Harrison
"""
import sys
import uuid
import argparse
from pathlib import Path
from datetime import datetime, timezone

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from backend.app import create_app
from backend.services.db_service import db_service
from backend.services.storage_service import storage_service
from backend.services.inference_service import inference_service
from backend.worker.worker import parse_csv_ecg_bytes


def ingest(patient_code: str = "MG-2026-000104", file_path: str = None):
    app = create_app()
    with app.app_context():
        print("=" * 75)
        print("  MEDIGUARD AI – DIRECT ECG CLI INGESTION PIPELINE")
        print("=" * 75)

        # 1. Locate Patient
        from backend.db.seed import seed_all
        if len(db_service.patients) == 0:
            seed_all()

        patients, _ = db_service.list_patients(include_archived=True)
        patient = None
        for p in patients:
            if p.get("patient_code") == patient_code:
                patient = p
                break

        if not patient:
            print(f"❌ Error: Patient with code '{patient_code}' not found in database.")
            return False

        patient_id = patient["id"]
        patient_name = f"{patient.get('first_name')} {patient.get('last_name')}"
        print(f"✓ Patient:       {patient_name} [{patient_code}] (Bed: {patient.get('room_bed')})")

        # 2. Locate ECG file
        if not file_path:
            file_path = BASE_DIR / "samples" / "ecg" / "patient_MG-2026-000104_12lead_ecg.csv"
        else:
            file_path = Path(file_path)

        if not file_path.exists():
            print(f"❌ Error: ECG file '{file_path}' does not exist.")
            return False

        file_bytes = file_path.read_bytes()
        file_name = file_path.name
        print(f"✓ Target File:   {file_name} ({len(file_bytes)} bytes)")

        # 3. Upload to Private Encrypted Storage
        report_id = str(uuid.uuid4())
        mime = "text/csv" if file_name.endswith(".csv") else "application/pdf"
        storage_meta = storage_service.upload_ecg_file(
            patient_id=patient_id,
            report_id=report_id,
            original_filename=file_name,
            file_bytes=file_bytes,
            content_type=mime
        )
        print(f"✓ Storage Path:  {storage_meta['storage_path']} (SHA-256: {storage_meta['sha256'][:16]}...)")

        # 4. Ingest and Run ResNet-1D ML Inference
        if file_name.endswith(".csv"):
            signal = parse_csv_ecg_bytes(file_bytes)
            print(f"✓ Signal Parsed: 12 Leads x {signal.shape[1]} samples (Duration: {signal.shape[1]/100.0:.1f}s)")
            
            # Store in DB
            ecg_record = db_service.add_ecg_report({
                "id": report_id,
                "patient_id": patient_id,
                "uploaded_by": "00000000-0000-0000-0000-000000000002",  # Clinical Staff user ID
                "recording_time": datetime.now(timezone.utc).isoformat(),
                "file_path": storage_meta["storage_path"],
                "file_name": file_name,
                "file_type": "digital_12lead",
                "urgency": "urgent",
                "status": "analyzed",
                "sampling_rate": 100,
                "leads_present": "I,II,III,aVR,aVL,aVF,V1,V2,V3,V4,V5,V6",
                "notes": f"Ingested via MediGuard Direct CLI for {patient_name}."
            })

            # Run ML analysis
            analysis = inference_service.run_inference_on_signal(signal, sampling_rate=100.0, report_id=report_id)
            print("-" * 75)
            print("EXPERIMENTAL MODEL SCORES:")
            print(f"  • MI (Myocardial Infarction):     {analysis.get('mi_score', 0.0):.3f}")
            print(f"  • STTC (ST/T Segment Changes):     {analysis.get('sttc_score', 0.0):.3f}")
            print(f"  • NORM (Normal Rhythm):            {analysis.get('norm_score', 0.0):.3f}")
            print(f"  • CD (Conduction Disturbance):     {analysis.get('cd_score', 0.0):.3f}")
            print(f"  • HYP (Hypertrophy):               {analysis.get('hyp_score', 0.0):.3f}")
            print(f"  • Signal Quality:                  {analysis.get('signal_quality', 'high').upper()}")
            print("-" * 75)
        else:
            # Document review pipeline
            ecg_record = db_service.add_ecg_report({
                "id": report_id,
                "patient_id": patient_id,
                "uploaded_by": "00000000-0000-0000-0000-000000000002",
                "recording_time": datetime.now(timezone.utc).isoformat(),
                "file_path": storage_meta["storage_path"],
                "file_name": file_name,
                "file_type": "pdf_report",
                "urgency": "urgent",
                "status": "awaiting_cardiologist_review",
                "sampling_rate": 0,
                "leads_present": "I,II,III,aVR,aVL,aVF,V1,V2,V3,V4,V5,V6",
                "notes": "Clinical PDF document routed to physician review queue."
            })
            print("✓ Routed directly to Cardiologist Review Workspace (No automated ML scoring).")

        signed_url_info = storage_service.generate_signed_url(patient_id=patient_id, report_id=report_id, expires_in_minutes=60)
        print(f"✓ Report ID:     {report_id}")
        url_val = signed_url_info.get("signed_url") if isinstance(signed_url_info, dict) else signed_url_info
        print(f"✓ View URL:      {url_val}")
        print("=" * 75)
        print("SUCCESS: ECG Report is now stored, analyzed, and available in the dashboard!")
        print("=" * 75)
        return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MediGuard Direct ECG CLI Ingestion")
    parser.add_argument("--patient", default="MG-2026-000104", help="Patient Code (e.g. MG-2026-000104)")
    parser.add_argument("--file", default=None, help="Path to ECG file (CSV or PDF)")
    args = parser.parse_args()
    ingest(patient_code=args.patient, file_path=args.file)
