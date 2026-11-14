"""
MediGuard AI – 12-Lead ECG Signal Preprocessing & Signal Quality Pipeline
Bandwidth: 0.5 - 40.0 Hz (Butterworth zero-phase filtfilt)
Fixed Order: I, II, III, aVR, aVL, aVF, V1, V2, V3, V4, V5, V6
Duration: 10.0 seconds (1000 samples @ 100 Hz, 5000 samples @ 500 Hz)
Standardization: Train-set statistics ONLY (no test leakage)
"""

import os
import json
import logging
from typing import Dict, List, Tuple, Optional, Union
import numpy as np
from scipy import signal as sp_signal

logger = logging.getLogger("mediguard.preprocessing")

STANDARD_LEADS = ["I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"]
LEAD_NAME_ALIASES = {
    "i": "I", "ii": "II", "iii": "III",
    "avr": "aVR", "avl": "aVL", "avf": "aVF",
    "v1": "V1", "v2": "V2", "v3": "V3", "v4": "V4", "v5": "V5", "v6": "V6"
}


def butter_bandpass_filter(data: np.ndarray, lowcut: float = 0.5, highcut: float = 40.0, fs: float = 100.0, order: int = 2) -> np.ndarray:
    """
    Apply zero-phase forward-backward Butterworth band-pass filter (0.5 - 40 Hz).
    Removes baseline wander (lowcut) and high-frequency muscle / 50-60Hz interference (highcut).
    Input: (12, L) or (L, 12).
    """
    nyq = 0.5 * fs
    low = max(0.01, lowcut / nyq)
    high = min(0.99, highcut / nyq)

    # Avoid invalid filter bounds
    if low >= high:
        low = 0.01
        high = 0.95

    b, a = sp_signal.butter(order, [low, high], btype="bandpass")
    
    # Process lead-by-lead along time axis
    filtered = np.zeros_like(data, dtype=np.float32)
    if data.shape[0] == 12:
        for ch in range(12):
            lead_data = np.nan_to_num(data[ch, :], nan=0.0, posinf=0.0, neginf=0.0)
            if np.std(lead_data) < 1e-6:
                filtered[ch, :] = lead_data
            else:
                filtered[ch, :] = sp_signal.filtfilt(b, a, lead_data).astype(np.float32)
    else:
        for ch in range(12):
            lead_data = np.nan_to_num(data[:, ch], nan=0.0, posinf=0.0, neginf=0.0)
            if np.std(lead_data) < 1e-6:
                filtered[:, ch] = lead_data
            else:
                filtered[:, ch] = sp_signal.filtfilt(b, a, lead_data).astype(np.float32)

    return filtered


def assess_signal_quality(raw_signal: np.ndarray, fs: float = 100.0) -> Dict[str, Union[float, str, bool]]:
    """
    Assess raw 12-lead ECG recording quality before clinical inference.
    Metrics evaluated:
    - Flatline ratio: leads/segments with zero voltage fluctuation (> 0.5 sec)
    - Amplitude clipping: values saturated beyond physiological ECG range (> 5.0 mV)
    - High-frequency noise estimate: ratio of power above 40 Hz
    - Returns composite quality score (0.0 to 1.0) and qualitative rating.
    """
    # Standardize to (12, L)
    if raw_signal.shape[0] != 12 and raw_signal.shape[1] == 12:
        sig = raw_signal.T
    else:
        sig = raw_signal

    num_leads, length = sig.shape
    if num_leads != 12:
        return {
            "overall_quality": 0.0,
            "rating": "poor",
            "is_acceptable": False,
            "flatline_leads": 12,
            "clipping_ratio": 1.0,
            "noise_ratio": 1.0,
            "reasons": [f"Expected 12 leads, found {num_leads}"]
        }

    reasons = []
    flatline_count = 0
    clipping_points = 0
    total_points = num_leads * length

    for i in range(12):
        lead = np.nan_to_num(sig[i, :])
        lead_std = np.std(lead)
        # Check for dead/disconnected leads
        if lead_std < 1e-4:
            flatline_count += 1
        # Check for amplifier saturation (> 5 mV or < -5 mV)
        clipping_points += np.sum(np.abs(lead) > 5.0)

    flatline_ratio = flatline_count / 12.0
    clipping_ratio = clipping_points / max(1, total_points)

    # Estimate high-frequency noise ratio (> 40 Hz power vs total)
    if fs > 80.0:
        highcut = min(fs / 2.0 - 1.0, 40.0)
        b_hp, a_hp = sp_signal.butter(2, highcut / (0.5 * fs), btype="highpass")
        noise_powers = []
        for i in range(12):
            lead = np.nan_to_num(sig[i, :])
            if np.std(lead) > 1e-4:
                hp = sp_signal.filtfilt(b_hp, a_hp, lead)
                noise_powers.append(np.mean(hp ** 2) / (np.mean(lead ** 2) + 1e-6))
        noise_ratio = float(np.mean(noise_powers)) if noise_powers else 0.0
    else:
        noise_ratio = 0.0

    # Composite quality score calculation
    quality_score = 1.0 - (0.5 * flatline_ratio) - (0.3 * min(1.0, clipping_ratio * 20)) - (0.2 * min(1.0, noise_ratio * 5))
    quality_score = max(0.0, min(1.0, float(quality_score)))

    if flatline_count >= 3:
        reasons.append(f"{flatline_count} leads are flatlined or disconnected")
    if clipping_ratio > 0.05:
        reasons.append(f"Amplifier clipping detected ({clipping_ratio * 100:.1f}% points)")
    if noise_ratio > 0.20:
        reasons.append(f"High-frequency EMG noise ({noise_ratio * 100:.1f}%)")

    if quality_score >= 0.80:
        rating = "good"
        acceptable = True
    elif quality_score >= 0.55:
        rating = "acceptable"
        acceptable = True
    else:
        rating = "poor"
        acceptable = False

    return {
        "overall_quality": round(quality_score, 3),
        "rating": rating,
        "is_acceptable": acceptable,
        "flatline_leads": int(flatline_count),
        "clipping_ratio": round(float(clipping_ratio), 4),
        "noise_ratio": round(float(noise_ratio), 4),
        "reasons": reasons
    }


def enforce_lead_order(signal: np.ndarray, lead_names: List[str]) -> np.ndarray:
    """
    Reorder signal channels to match the standard 12-lead clinical order:
    ['I', 'II', 'III', 'aVR', 'aVL', 'aVF', 'V1', 'V2', 'V3', 'V4', 'V5', 'V6'].
    Input signal can be (12, L) or (L, 12). Returns (12, L).
    """
    if signal.shape[0] != 12 and signal.shape[1] == 12:
        sig = signal.T
    else:
        sig = signal

    if sig.shape[0] != 12:
        raise ValueError(f"Expected 12 leads, got shape: {signal.shape}")

    # Standardize lead name casing
    normalized_names = [LEAD_NAME_ALIASES.get(name.strip().lower(), name.strip()) for name in lead_names]
    name_to_idx = {name: i for i, name in enumerate(normalized_names)}

    ordered_sig = np.zeros_like(sig, dtype=np.float32)
    for target_idx, target_name in enumerate(STANDARD_LEADS):
        if target_name in name_to_idx:
            src_idx = name_to_idx[target_name]
            ordered_sig[target_idx, :] = sig[src_idx, :]
        else:
            # Fallback: keep original index if lead name mapping incomplete
            ordered_sig[target_idx, :] = sig[target_idx, :]

    return ordered_sig


def standardize_signal_length(signal: np.ndarray, target_length: int = 1000) -> np.ndarray:
    """
    Ensure the signal length along the time axis is exactly target_length (e.g. 1000 for 10s @ 100Hz).
    Input: (12, L). Returns (12, target_length).
    """
    curr_len = signal.shape[1]
    if curr_len == target_length:
        return signal

    if curr_len > target_length:
        # Center crop
        start = (curr_len - target_length) // 2
        return signal[:, start:start + target_length]
    else:
        # Zero-pad symmetrically
        pad_left = (target_length - curr_len) // 2
        pad_right = target_length - curr_len - pad_left
        return np.pad(signal, ((0, 0), (pad_left, pad_right)), mode="constant", constant_values=0.0)


class ECGStandardizer:
    """
    Lead-wise z-score standardizer computed STRICTLY on the training fold.
    Guarantees zero data leakage from validation or test folds.
    """

    def __init__(self, means: Optional[Union[np.ndarray, List]] = None, stds: Optional[Union[np.ndarray, List]] = None):
        self.means = np.array(means, dtype=np.float32).reshape(12, 1) if means is not None else np.zeros((12, 1), dtype=np.float32)
        self.stds = np.array(stds, dtype=np.float32).reshape(12, 1) if stds is not None else np.ones((12, 1), dtype=np.float32)

    def fit(self, train_signals: List[np.ndarray]) -> "ECGStandardizer":
        """
        Fit means and standard deviations across all training fold 12-lead signals.
        train_signals: list of (12, L) arrays.
        """
        all_leads = [[] for _ in range(12)]
        for sig in train_signals:
            for ch in range(12):
                all_leads[ch].append(sig[ch, :])

        computed_means = []
        computed_stds = []
        for ch in range(12):
            concat = np.concatenate(all_leads[ch])
            m = float(np.mean(concat))
            s = float(np.std(concat))
            computed_means.append(m)
            computed_stds.append(s if s > 1e-4 else 1.0)

        self.means = np.array(computed_means, dtype=np.float32).reshape(12, 1)
        self.stds = np.array(computed_stds, dtype=np.float32).reshape(12, 1)
        logger.info("Fitted ECGStandardizer on %d training records.", len(train_signals))
        return self

    def transform(self, signal: np.ndarray) -> np.ndarray:
        """
        Apply z-score normalization: (signal - mean) / std.
        Input: (12, L).
        """
        return ((signal - self.means) / self.stds).astype(np.float32)

    def save(self, filepath: str) -> None:
        """Serialize standardization parameters to JSON."""
        data = {
            "means": self.means.flatten().tolist(),
            "stds": self.stds.flatten().tolist(),
            "leads": STANDARD_LEADS
        }
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)

    @classmethod
    def load(cls, filepath: str) -> "ECGStandardizer":
        """Load standardization parameters from JSON."""
        with open(filepath, "r") as f:
            data = json.load(f)
        return cls(means=data["means"], stds=data["stds"])


def apply_training_augmentations(signal: np.ndarray, rng: Optional[np.random.RandomState] = None) -> np.ndarray:
    """
    Data augmentations applied STRICTLY during training on the training fold:
    1. Random amplitude scaling: 0.8x to 1.2x
    2. Random temporal shift: roll +/- 5% along time axis
    3. Slight additive Gaussian noise: std = 0.02
    """
    if rng is None:
        rng = np.random.RandomState()

    aug = signal.copy()

    # 1. Amplitude scale
    scale = rng.uniform(0.85, 1.15)
    aug = aug * scale

    # 2. Time shift (circular roll)
    shift_samples = rng.randint(-50, 50)
    aug = np.roll(aug, shift_samples, axis=1)

    # 3. Additive Gaussian noise
    noise = rng.normal(0, 0.02, size=aug.shape).astype(np.float32)
    aug = aug + noise

    return aug.astype(np.float32)


def preprocess_ecg_signal(
    raw_signal: np.ndarray,
    fs: float = 100.0,
    target_fs: float = 100.0,
    standardizer: Optional[ECGStandardizer] = None,
    lead_names: Optional[List[str]] = None,
    is_training: bool = False,
    rng: Optional[np.random.RandomState] = None
) -> Tuple[np.ndarray, Dict]:
    """
    Full end-to-end preprocessing pipeline for a single 12-lead ECG recording:
    1. Assess signal quality
    2. Enforce standard lead order
    3. Resample if sampling rate differs from target_fs
    4. Butterworth band-pass filter (0.5 - 40 Hz)
    5. Standardize length (10 seconds)
    6. Z-score normalization using training-fold statistics
    7. Apply augmentations (if is_training == True)
    """
    # 1. Assess quality
    quality = assess_signal_quality(raw_signal, fs=fs)

    # 2. Reorder leads
    if lead_names is not None:
        sig = enforce_lead_order(raw_signal, lead_names)
    else:
        sig = raw_signal.T if (raw_signal.shape[0] != 12 and raw_signal.shape[1] == 12) else raw_signal

    # 3. Resample if necessary
    if abs(fs - target_fs) > 1.0:
        target_len = int(sig.shape[1] * (target_fs / fs))
        sig = sp_signal.resample(sig, target_len, axis=1).astype(np.float32)

    # 4. Band-pass filter
    sig = butter_bandpass_filter(sig, lowcut=0.5, highcut=40.0, fs=target_fs, order=2)

    # 5. Standardize length (10.0 seconds)
    target_samples = int(10.0 * target_fs)
    sig = standardize_signal_length(sig, target_samples)

    # 6. Normalize with training standardizer
    if standardizer is not None:
        sig = standardizer.transform(sig)

    # 7. Training augmentations
    if is_training:
        sig = apply_training_augmentations(sig, rng=rng)

    return sig.astype(np.float32), quality
