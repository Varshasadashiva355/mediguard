"""
MediGuard AI – Beatrice Campbell (MG-2026-000104) 12-Lead Digital ECG Generator
Generates a calibrated 10-second digital 12-lead ECG CSV file at 100 Hz (1,000 samples)
accurately reflecting her clinical profile:
- Patient: Beatrice (Synthetic) Campbell
- Patient Code: MG-2026-000104 (UUID: 44444444-4444-4444-4444-444444440104)
- Age/Gender: 66 F (DOB: 1960-08-15)
- Location: CCU Bed 2 | Urgency: Urgent
- Clinical Presentation: NSTEMI with Multi-Vessel Disease (Awaiting Cath, Prior MI, EF 45%)
- ECG Hallmarks:
  * ST-elevation in aVR (+0.65 mV) indicating severe subendocardial ischemia / multi-vessel CAD
  * Diffuse horizontal ST-depression in lateral and precordial leads (I, II, aVL, V4-V6: -0.25 to -0.35 mV)
  * Symmetrical T-wave inversions in V3-V6, I, aVL
  * Normal axis, sinus rhythm at 84 bpm (cardiac cycle ~0.714s)
  * Standard 100 Hz sampling rate, 1,000 samples (10.0 seconds), 12 diagnostic channels.
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

OUTPUT_DIR = BASE_DIR / "samples" / "ecg"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
CSV_PATH = OUTPUT_DIR / "patient_MG-2026-000104_12lead_ecg.csv"

STANDARD_LEADS = ["I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"]


def generate_beatrice_campbell_ecg(
    duration_sec: float = 10.0,
    sampling_rate: float = 100.0,
    hr_bpm: float = 84.0
) -> pd.DataFrame:
    """
    Generates a 12-lead physiological ECG waveform for NSTEMI with Multi-vessel Disease.
    """
    num_samples = int(duration_sec * sampling_rate)
    t = np.linspace(0, duration_sec, num_samples, endpoint=False)
    cycle_period = 60.0 / hr_bpm  # ~0.714s for 84 bpm

    # Lead-specific waveform parameter definitions
    # (r_amp, s_amp, st_shift, t_amp, q_amp, p_amp)
    lead_configs = {
        # Limb leads
        "I":   {"r": 0.85, "s": -0.15, "st": -0.22, "t": -0.20, "q": -0.08, "p": 0.12},
        "II":  {"r": 1.15, "s": -0.20, "st": -0.28, "t": -0.18, "q": -0.05, "p": 0.14},
        "III": {"r": 0.45, "s": -0.25, "st": -0.06, "t":  0.08, "q": -0.02, "p": 0.05},
        "aVR": {"r": 0.15, "s": -1.10, "st": +0.65, "t": +0.25, "q":  0.00, "p": -0.10},  # Prominent aVR ST-elevation
        "aVL": {"r": 0.60, "s": -0.10, "st": -0.20, "t": -0.15, "q": -0.06, "p": 0.08},
        "aVF": {"r": 0.75, "s": -0.20, "st": -0.12, "t": -0.05, "q": -0.04, "p": 0.10},

        # Precordial leads (V1-V6)
        "V1":  {"r": 0.30, "s": -1.25, "st": +0.15, "t":  0.10, "q":  0.00, "p": 0.08},
        "V2":  {"r": 0.65, "s": -1.35, "st": -0.05, "t": -0.12, "q":  0.00, "p": 0.10},  # Biphasic/inverted
        "V3":  {"r": 0.95, "s": -0.90, "st": -0.15, "t": -0.22, "q": -0.04, "p": 0.12},  # Deep T-wave inversion
        "V4":  {"r": 1.45, "s": -0.45, "st": -0.32, "t": -0.28, "q": -0.08, "p": 0.14},  # Marked ST depression
        "V5":  {"r": 1.60, "s": -0.25, "st": -0.35, "t": -0.30, "q": -0.10, "p": 0.14},  # Marked ST depression
        "V6":  {"r": 1.25, "s": -0.15, "st": -0.26, "t": -0.24, "q": -0.09, "p": 0.12},  # Lateral ST depression
    }

    # Deterministic seed for reproducible clinical data
    rng = np.random.RandomState(42)
    ecg_dict = {}

    for lead in STANDARD_LEADS:
        cfg = lead_configs[lead]
        lead_signal = np.zeros(num_samples, dtype=np.float64)

        for i, ti in enumerate(t):
            cycle_t = ti % cycle_period
            val = 0.0

            # 1. P Wave: Atrial Depolarization (~80ms: 0.06s to 0.14s)
            if 0.06 <= cycle_t < 0.14:
                val += cfg["p"] * np.sin((cycle_t - 0.06) * np.pi / 0.08)

            # 2. PR Segment (AV Node conduction delay: 0.14s to 0.19s)
            # 3. Q Wave: Septal Depolarization (~30ms: 0.19s to 0.22s)
            elif 0.19 <= cycle_t < 0.22:
                val += cfg["q"] * np.sin((cycle_t - 0.19) * np.pi / 0.03)

            # 4. R Wave: Major Ventricular Depolarization (~60ms: 0.22s to 0.28s)
            elif 0.22 <= cycle_t < 0.28:
                val += cfg["r"] * np.sin((cycle_t - 0.22) * np.pi / 0.06)

            # 5. S Wave: Late Ventricular Depolarization (~40ms: 0.28s to 0.32s)
            elif 0.28 <= cycle_t < 0.32:
                val += cfg["s"] * np.sin((cycle_t - 0.28) * np.pi / 0.04)

            # 6. ST Segment: Subendocardial Ischemia (~160ms: 0.32s to 0.48s)
            if 0.32 <= cycle_t <= 0.48:
                val += cfg["st"]

            # 7. T Wave: Ventricular Repolarization (~180ms: 0.44s to 0.62s)
            if 0.44 <= cycle_t < 0.62:
                val += cfg["t"] * np.sin((cycle_t - 0.44) * np.pi / 0.18)

            # Mild physiological baseline wander (respiratory ~0.15 Hz)
            val += 0.012 * np.sin(2 * np.pi * 0.15 * ti)

            lead_signal[i] = val

        # Add slight realistic high-frequency sensor noise (SNR > 30 dB)
        noise = rng.normal(0, 0.008, num_samples)
        ecg_dict[lead] = np.round(lead_signal + noise, 4)

    df = pd.DataFrame(ecg_dict, columns=STANDARD_LEADS)
    return df


def main():
    print("=" * 70)
    print("Generating Digital 12-Lead ECG CSV for Beatrice Campbell (MG-2026-000104)...")
    print("=" * 70)

    df = generate_beatrice_campbell_ecg(
        duration_sec=10.0,
        sampling_rate=100.0,
        hr_bpm=84.0
    )

    df.to_csv(CSV_PATH, index=False)
    file_size = CSV_PATH.stat().st_size
    print(f"Generated CSV File: {CSV_PATH.name}")
    print(f"File Path:          {CSV_PATH}")
    print(f"File Size:          {file_size} bytes")
    print(f"Dimensions:         {df.shape[0]} rows x {df.shape[1]} columns")
    print(f"Leads Present:      {', '.join(df.columns)}")
    print(f"Duration:           10.0 seconds @ 100.0 Hz")
    print("-" * 70)
    print("First 5 rows preview:")
    print(df.head())
    print("=" * 70)


if __name__ == "__main__":
    main()
