"""
MediGuard AI – Dick Grayson (MG-2026-000120) 12-Lead Digital ECG Generator
Generates a calibrated 10-second digital 12-lead ECG CSV file at 100 Hz (1,000 samples)
accurately reflecting his clinical profile:
- Patient: Dick (Synthetic) Grayson
- Patient Code: MG-2026-000120 (UUID: 44444444-4444-4444-4444-444444440120)
- Age/Gender: 42 M (DOB: 1984-03-20)
- Location: Step-Down 101 | Urgency: Routine
- Condition: Athletic Heart with Ischemic Episode (Post-PCI LAD Stent, EF 64%)
- ECG Hallmarks:
  * High voltage QRS (physiologic left ventricular athletic hypertrophy)
  * Early repolarization pattern (J-point elevation 0.08 to 0.12 mV in V2-V5 with concave upward ST)
  * Sinus bradycardia (~58 bpm, athletic basal rhythm, RR interval ~1.034s)
  * Normal 12-lead standard leads: I, II, III, aVR, aVL, aVF, V1, V2, V3, V4, V5, V6
"""
from pathlib import Path
import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
SAMPLES_DIR = BASE_DIR / "samples" / "ecg"
FRONTEND_SAMPLES_DIR = BASE_DIR / "frontend" / "samples"
SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
FRONTEND_SAMPLES_DIR.mkdir(parents=True, exist_ok=True)

CSV_PATH = SAMPLES_DIR / "patient_MG-2026-000120_12lead_ecg.csv"
FRONTEND_CSV_PATH = FRONTEND_SAMPLES_DIR / "patient_MG-2026-000120_12lead_ecg.csv"

STANDARD_LEADS = ["I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"]


def generate_grayson_ecg(duration_sec: float = 10.0, sampling_rate: float = 100.0, hr_bpm: float = 58.0) -> pd.DataFrame:
    num_samples = int(duration_sec * sampling_rate)
    t = np.linspace(0, duration_sec, num_samples, endpoint=False)
    cycle_period = 60.0 / hr_bpm  # ~1.034s for 58 bpm athletic heart

    # Athletic heart lead configs (prominent R voltage, early repol concave ST, robust T waves)
    lead_configs = {
        "I":   {"r": 0.95, "s": -0.15, "st":  0.04, "t":  0.28, "q": -0.06, "p": 0.12},
        "II":  {"r": 1.45, "s": -0.20, "st":  0.06, "t":  0.36, "q": -0.05, "p": 0.15},
        "III": {"r": 0.60, "s": -0.22, "st":  0.02, "t":  0.14, "q": -0.02, "p": 0.06},
        "aVR": {"r": 0.15, "s": -1.25, "st": -0.04, "t": -0.26, "q":  0.00, "p": -0.11},
        "aVL": {"r": 0.70, "s": -0.12, "st":  0.03, "t":  0.20, "q": -0.05, "p": 0.09},
        "aVF": {"r": 0.95, "s": -0.18, "st":  0.04, "t":  0.24, "q": -0.04, "p": 0.11},
        "V1":  {"r": 0.40, "s": -1.35, "st":  0.08, "t":  0.15, "q":  0.00, "p": 0.08},
        "V2":  {"r": 0.90, "s": -1.60, "st":  0.12, "t":  0.42, "q":  0.00, "p": 0.10},  # J-point elevation
        "V3":  {"r": 1.35, "s": -1.15, "st":  0.10, "t":  0.48, "q": -0.04, "p": 0.12},
        "V4":  {"r": 1.95, "s": -0.45, "st":  0.08, "t":  0.52, "q": -0.08, "p": 0.14},  # High R amplitude
        "V5":  {"r": 1.80, "s": -0.25, "st":  0.06, "t":  0.46, "q": -0.10, "p": 0.14},
        "V6":  {"r": 1.40, "s": -0.15, "st":  0.04, "t":  0.34, "q": -0.08, "p": 0.12},
    }

    rng = np.random.RandomState(120)
    data = {}

    for lead in STANDARD_LEADS:
        cfg = lead_configs[lead]
        sig = np.zeros(num_samples, dtype=np.float64)

        for i, ti in enumerate(t):
            cycle_t = ti % cycle_period
            val = 0.0

            # P Wave (0.10s to 0.20s)
            if 0.10 <= cycle_t < 0.20:
                val += cfg["p"] * np.sin((cycle_t - 0.10) * np.pi / 0.10)

            # Q Wave (0.26s to 0.29s)
            elif 0.26 <= cycle_t < 0.29:
                val += cfg["q"] * np.sin((cycle_t - 0.26) * np.pi / 0.03)

            # R Wave (0.29s to 0.36s)
            elif 0.29 <= cycle_t < 0.36:
                val += cfg["r"] * np.sin((cycle_t - 0.29) * np.pi / 0.07)

            # S Wave (0.36s to 0.41s)
            elif 0.36 <= cycle_t < 0.41:
                val += cfg["s"] * np.sin((cycle_t - 0.36) * np.pi / 0.05)

            # Early Repolarization ST Segment (0.41s to 0.58s)
            if 0.41 <= cycle_t <= 0.58:
                val += cfg["st"]

            # Robust T Wave (0.50s to 0.72s)
            if 0.50 <= cycle_t < 0.72:
                val += cfg["t"] * np.sin((cycle_t - 0.50) * np.pi / 0.22)

            # Subtle baseline respiratory wander (0.12 Hz)
            val += 0.010 * np.sin(2 * np.pi * 0.12 * ti)

            sig[i] = val

        # Clean sensor noise
        noise = rng.normal(0, 0.007, num_samples)
        data[lead] = np.round(sig + noise, 4)

    df = pd.DataFrame(data, columns=STANDARD_LEADS)
    return df


def main():
    df = generate_grayson_ecg()
    df.to_csv(CSV_PATH, index=False)
    df.to_csv(FRONTEND_CSV_PATH, index=False)
    print(f"Generated CSV File: {CSV_PATH}")
    print(f"File Size:          {CSV_PATH.stat().st_size} bytes")
    print(f"Dimensions:         {df.shape[0]} rows x {df.shape[1]} columns")
    print(f"Leads:              {list(df.columns)}")


if __name__ == "__main__":
    main()
