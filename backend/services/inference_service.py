"""
MediGuard AI – ECG Inference Service
Bridges the Flask application and background worker to the Phase 3 ResNet-1D PyTorch model.
Enforces Non-Negotiable Rules:
- Rule 1: Research/clinical decision-support prototype ONLY. NOT a validated diagnostic product.
- Rule 2: Scores are strictly "experimental model scores", never confirmed diagnoses or calibrated heart-attack probabilities.
- Rule 3: If no trained checkpoint is found, tags output as DEMONSTRATION DATA (is_demo=true).
- Rule 4: Digital 12-lead waveforms ONLY (no OCR or fake interpretations).
"""
import os
import logging
from pathlib import Path
from typing import Dict, Any, Optional
import numpy as np

from backend.services.db_service import db_service

logger = logging.getLogger("mediguard.inference")

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_CHECKPOINT = BASE_DIR / "saved_models" / "best_model.pt"

MANDATORY_DISCLAIMER = (
    "Research and clinical decision-support prototype ONLY. NOT a validated diagnostic product. "
    "Output scores are experimental uncalibrated model scores, NOT confirmed diagnoses. "
    "Attending physicians retain 100% ownership and legal responsibility for every clinical diagnosis and triage decision."
)

DEMO_FALLBACK_SCORES = {
    "NORM": 0.14,
    "MI": 0.86,
    "STTC": 0.72,
    "CD": 0.06,
    "HYP": 0.11
}


class InferenceService:
    def __init__(self, checkpoint_path: Optional[Path] = None):
        self.checkpoint_path = checkpoint_path or DEFAULT_CHECKPOINT
        self.has_checkpoint = self.checkpoint_path.exists()
        self._predictor = None

    def _get_predictor(self):
        if self._predictor is None:
            from ml.predict import load_model
            ckpt_str = str(self.checkpoint_path) if self.has_checkpoint else None
            self._predictor = load_model(ckpt_str)
        return self._predictor

    def run_inference_on_signal(
        self,
        signal: np.ndarray,
        sampling_rate: float = 100.0,
        report_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Run ResNet-1D inference on preprocessed 12-lead signal (shape: 12, T).
        Stores analysis record in database.
        """
        if not self.has_checkpoint and not self.checkpoint_path.exists():
            logger.warning("No trained checkpoint at %s. Marking as DEMONSTRATION DATA.", self.checkpoint_path)
            res = {
                "model_version": "v1.0.0-DEMO",
                "is_demonstration_data": True,
                "signal_quality": {
                    "rating": "moderate",
                    "overall_quality": 0.85,
                    "lead_qualities": {f"lead_{i}": 0.85 for i in range(12)}
                },
                "scores": DEMO_FALLBACK_SCORES,
                "warnings": ["Operating in DEMONSTRATION DATA mode (no trained model weights loaded)."],
                "disclaimer": MANDATORY_DISCLAIMER
            }
        else:
            predictor = self._get_predictor()
            res = predictor.predict(signal, sampling_rate=sampling_rate)

        # Map to database analysis record
        scores = res.get("scores", {})
        norm_score = float(scores.get("NORM", 0.0))
        mi_score = float(scores.get("MI", 0.0))
        sttc_score = float(scores.get("STTC", 0.0))
        cd_score = float(scores.get("CD", 0.0))
        hyp_score = float(scores.get("HYP", 0.0))
        quality = res.get("signal_quality", {}).get("rating", "high")
        is_demo = res.get("is_demonstration_data", False)
        model_version = res.get("model_version", "mediguard_ecg_v1.0.0")

        analysis_record = {
            "report_id": report_id or "unassigned",
            "model_version": model_version,
            "norm_score": norm_score,
            "mi_score": mi_score,
            "sttc_score": sttc_score,
            "cd_score": cd_score,
            "hyp_score": hyp_score,
            "signal_quality": quality,
            "limitations": MANDATORY_DISCLAIMER,
            "is_demo": is_demo,
            "raw_predictions": res
        }

        if report_id:
            db_service.add_ecg_analysis(analysis_record)
            # Update report status to 'analyzed' (or 'flagged_urgent' if high MI/STTC)
            rep_status = "flagged_urgent" if (mi_score >= 0.70 or sttc_score >= 0.70) else "analyzed"
            db_service.update_ecg_report(report_id, {"status": rep_status})

        return analysis_record


# Global singleton instance
inference_service = InferenceService()
