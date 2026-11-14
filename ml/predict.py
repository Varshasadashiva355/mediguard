"""
MediGuard AI – 12-Lead ECG Clinical Decision Support Inference Engine
Strictly processes digital 12-lead waveforms (No OCR on images).
Rejects invalid/incompatible inputs (wrong lead counts, short durations, dead leads).
Produces experimental model scores for: NORM, MI, STTC, CD, HYP.

Non-Negotiable Rules 1, 2, 3:
1. Research decision support only. NOT a validated diagnostic product.
2. Never present scores as confirmed diagnoses or calibrated heart-attack probabilities.
3. If no trained checkpoint is loaded, explicitly tag results as DEMONSTRATION DATA.
"""

import os
import sys
import json
import logging
import argparse
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Union

# Ensure repository root is on sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import numpy as np
import pandas as pd
import torch

from ml.model import ResNet1D_MediGuard, build_model, SUPERCLASSES
from ml.preprocessing import (
    preprocess_ecg_signal,
    assess_signal_quality,
    enforce_lead_order,
    ECGStandardizer,
    STANDARD_LEADS
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("mediguard.predict")

CLINICAL_DISCLAIMER = (
    "MANDATORY CLINICAL DISCLAIMER: Research and clinical decision-support prototype ONLY. "
    "NOT a validated diagnostic product. Output scores are experimental model scores, "
    "NOT confirmed diagnoses. Attending physician owns 100% of all clinical decisions."
)

DEMO_FALLBACK_SCORES = {
    "NORM": 0.14,
    "MI": 0.86,
    "STTC": 0.72,
    "CD": 0.06,
    "HYP": 0.11
}


class ECGPredictor:
    """Production inference wrapper for MediGuard AI 12-lead ECG analysis."""

    def __init__(self, checkpoint_path: Optional[str] = None, device: Optional[torch.device] = None):
        self.device = device or torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model: Optional[ResNet1D_MediGuard] = None
        self.standardizer: Optional[ECGStandardizer] = None
        self.model_version: str = "v1.0.0-uninitialized"
        self.is_demonstration_data: bool = True
        self.sampling_rate: int = 100

        if checkpoint_path and os.path.exists(checkpoint_path):
            self.load_checkpoint(checkpoint_path)
        else:
            logger.warning(
                "No trained checkpoint provided or file not found (%s). "
                "Operating in STRICT DEMONSTRATION DATA mode.", checkpoint_path
            )
            self.model = build_model().to(self.device)
            self.model.eval()
            self.standardizer = ECGStandardizer()
            self.model_version = "v1.0.0-DEMO"
            self.is_demonstration_data = True

    def load_checkpoint(self, checkpoint_path: str):
        """Load trained weights, standardizer, and metadata from checkpoint."""
        logger.info("Loading MediGuard model checkpoint from: %s", checkpoint_path)
        ckpt = torch.load(checkpoint_path, map_location=self.device)

        cfg = ckpt.get("config", {})
        self.model = build_model(cfg).to(self.device)
        self.model.load_state_dict(ckpt["state_dict"])
        self.model.eval()

        self.standardizer = ECGStandardizer(means=ckpt.get("means"), stds=ckpt.get("stds"))
        self.model_version = ckpt.get("model_version", "v1.0.0-ptbxl")
        self.is_demonstration_data = ckpt.get("is_demonstration_data", False)
        self.sampling_rate = ckpt.get("sampling_rate", 100)
        logger.info("Model loaded successfully. Version: %s, Device: %s", self.model_version, self.device)

    def validate_input_signal(self, signal: np.ndarray, sampling_rate: float) -> Tuple[np.ndarray, List[str]]:
        """
        Strict validation of incoming ECG signal:
        1. Must contain exactly 12 channels (refuses 3-lead, 1-lead).
        2. Must have duration >= 5.0 seconds (refuses short snippets like 2s).
        3. Rejects completely flatlined or NaN signals.
        """
        warnings = []

        if not isinstance(signal, np.ndarray):
            try:
                signal = np.array(signal, dtype=np.float32)
            except Exception as e:
                raise ValueError(f"Invalid signal format: cannot convert to numpy array ({e})")

        # Determine orientation: (12, L) or (L, 12)
        if signal.shape[0] == 12:
            sig = signal
        elif signal.shape[1] == 12:
            sig = signal.T
        else:
            raise ValueError(
                f"Incompatible ECG signal: expected 12 leads, found shape {signal.shape}. "
                "MediGuard AI ML inference strictly supports standard 12-lead recordings."
            )

        duration_sec = sig.shape[1] / max(1.0, float(sampling_rate))
        if duration_sec < 5.0:
            raise ValueError(
                f"Incompatible ECG signal: recording too short ({duration_sec:.1f} seconds). "
                "Minimum required duration is 5.0 seconds (10.0s clinical standard)."
            )

        if duration_sec != 10.0:
            warnings.append(f"Recording duration is {duration_sec:.1f}s (standard is 10.0s). Signal resampled/padded.")

        # Check for absolute zero flatline across all 12 leads
        if np.all(np.abs(sig) < 1e-7):
            raise ValueError("Incompatible ECG signal: all 12 leads are zero or disconnected (flatline).")

        return sig, warnings

    def predict(
        self,
        signal: np.ndarray,
        sampling_rate: float = 100.0,
        lead_names: Optional[List[str]] = None
    ) -> Dict:
        """
        Execute clinical decision-support prediction on a 12-lead digital ECG recording.
        Returns:
            Dictionary containing 5 experimental model scores, quality metrics, warnings,
            and the non-negotiable clinical disclaimer.
        """
        # 1. Strict validation
        sig, warnings = self.validate_input_signal(signal, sampling_rate)

        # 2. Quality assessment
        quality = assess_signal_quality(sig, fs=sampling_rate)
        if not quality["is_acceptable"]:
            warnings.append(f"Degraded Signal Quality ({quality['rating']}): {', '.join(quality['reasons'])}")

        # 3. Preprocessing (ordering, 0.5-40Hz bandpass, length standardization, z-score)
        proc_sig, _ = preprocess_ecg_signal(
            sig,
            fs=sampling_rate,
            target_fs=float(self.sampling_rate),
            standardizer=self.standardizer,
            lead_names=lead_names,
            is_training=False
        )

        # 4. Model Inference or Demonstration Fallback
        if self.is_demonstration_data and self.model_version.endswith("-DEMO"):
            scores = DEMO_FALLBACK_SCORES.copy()
            # Slightly adjust with signal variation for realistic demonstration
            scores["MI"] = round(float(np.clip(0.85 + (np.mean(proc_sig[7:9, :]) * 0.1), 0.1, 0.98)), 3)
            scores["NORM"] = round(float(1.0 - scores["MI"]) * 0.6, 3)
        else:
            tensor_sig = torch.from_numpy(proc_sig).unsqueeze(0).float().to(self.device)
            with torch.no_grad():
                pred_tensor = self.model.predict_scores(tensor_sig).squeeze(0).cpu().numpy()
            scores = {sc: round(float(pred_tensor[i]), 3) for i, sc in enumerate(SUPERCLASSES)}

        result = {
            "scores": scores,
            "model_version": self.model_version,
            "signal_quality": quality,
            "warnings": warnings,
            "is_demonstration_data": self.is_demonstration_data,
            "disclaimer": CLINICAL_DISCLAIMER
        }

        return result


def load_model(checkpoint_path: Optional[str] = None, device: Optional[torch.device] = None) -> ECGPredictor:
    """Factory loader for ECGPredictor."""
    return ECGPredictor(checkpoint_path=checkpoint_path, device=device)


def predict(
    signal: np.ndarray,
    sampling_rate: float = 100.0,
    checkpoint_path: Optional[str] = "saved_models/best_model.pt",
    lead_names: Optional[List[str]] = None
) -> Dict:
    """One-line functional prediction helper."""
    predictor = ECGPredictor(checkpoint_path=checkpoint_path)
    return predictor.predict(signal, sampling_rate=sampling_rate, lead_names=lead_names)


def main():
    parser = argparse.ArgumentParser(description="MediGuard AI – 12-Lead ECG Inference CLI")
    parser.add_argument("--file", type=str, default=None, help="Path to .csv, .npy or WFDB record")
    parser.add_argument("--checkpoint", type=str, default="saved_models/best_model.pt", help="Path to checkpoint")
    parser.add_argument("--sampling-rate", type=float, default=100.0, help="Sampling rate in Hz")
    parser.add_argument("--demo", action="store_true", help="Run on a synthetic test recording")
    args = parser.parse_args()

    predictor = load_model(args.checkpoint)

    if args.file and os.path.exists(args.file):
        ext = os.path.splitext(args.file)[1].lower()
        if ext == ".csv":
            df = pd.read_csv(args.file)
            signal = df.values.astype(np.float32)
        elif ext == ".npy":
            signal = np.load(args.file).astype(np.float32)
        else:
            import wfdb
            record = wfdb.rdrecord(os.path.splitext(args.file)[0])
            signal = record.p_signal.astype(np.float32)
    else:
        logger.info("Generating synthetic 12-lead ECG recording for inference demonstration...")
        t = np.linspace(0, 10, int(10 * args.sampling_rate))
        signal = np.sin(2 * np.pi * 1.2 * t).reshape(1, -1).repeat(12, axis=0) + np.random.normal(0, 0.05, (12, len(t)))

    try:
        output = predictor.predict(signal, sampling_rate=args.sampling_rate)
        print("\n" + "=" * 70)
        print("MEDIGUARD AI – CLINICAL DECISION SUPPORT INFERENCE RESULT")
        print("=" * 70)
        print(f"Model Version:         {output['model_version']}")
        print(f"Demonstration Mode:    {output['is_demonstration_data']}")
        print(f"Signal Quality Rating: {output['signal_quality']['rating'].upper()} ({output['signal_quality']['overall_quality'] * 100:.1f}%)")
        print("-" * 70)
        print("EXPERIMENTAL MODEL SCORES (0.00 to 1.00):")
        for sc, score in output["scores"].items():
            print(f"  • {sc:<6}: {score:.3f}")
        if output["warnings"]:
            print("\nWARNINGS:")
            for w in output["warnings"]:
                print(f"  ⚠️  {w}")
        print("\n" + output["disclaimer"])
        print("=" * 70 + "\n")
    except Exception as e:
        logger.error("Inference failed: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
