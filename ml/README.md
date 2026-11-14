# MediGuard AI – Machine Learning & Inference Pipeline
> **PyTorch 12-Lead ECG Analysis & Experimental Decision Support**

## Clinical & Engineering Guidelines
1. **Research & Decision-Support Only**:
   - Model predictions are *experimental decision-support indicators*, NOT calibrated probabilities or diagnoses.
   - All frontend presentations must clearly state: "Experimental Model Scores".
2. **Signal Format Requirement**:
   - The ML inference engine operates **exclusively** on raw digital 12-lead waveforms (e.g., WFDB format `.dat`/`.hea`, raw voltage arrays sampled at 500 Hz / 250 Hz, or digital CSV arrays).
   - **No OCR or image-based visual waveform reconstruction** is used for ML scoring. Scanned ECG images and PDFs are routed through separate document archiving pipelines.
3. **Model Scores (PTB-XL Diagnostic Superclasses)**:
   - `norm_score`: Normal ECG pattern score [0.0 - 1.0]
   - `mi_score`: Myocardial Infarction pattern score [0.0 - 1.0]
   - `sttc_score`: ST/T-Change ischemic pattern score [0.0 - 1.0]
   - `cd_score`: Conduction Disturbance pattern score [0.0 - 1.0]
   - `hyp_score`: Hypertrophy pattern score [0.0 - 1.0]
4. **Demonstration Data Fallback**:
   - If no trained model checkpoint (`saved_models/mediguard_ecg_v1.pt`) is found on disk, the pipeline flags all inferences as `is_demo: True` and prefixes output with `"DEMONSTRATION DATA"`. Fabricated or uncalibrated mock inferences are strictly identified.
