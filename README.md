# MediGuard AI – Cardiology Patient Monitoring & Clinical Decision Support

[![Status: Prototype / Research Decision-Support](https://img.shields.io/badge/Clinical_Status-Prototype_%2F_Decision--Support_Only-teal.svg)](#mandatory-clinical-disclaimer)
[![Python Version](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://python.org)
[![Deep Learning Framework](https://img.shields.io/badge/PyTorch-ResNet--1D_PTB--XL-ee4c2c.svg)](https://pytorch.org)
[![Standards](https://img.shields.io/badge/ECG_Standard-12--Lead_AHA%2FACC-success.svg)](#ecg-ingestion-pipelines)

---

## ⚠️ Mandatory Clinical Decision-Support Disclaimer

> [!IMPORTANT]
> **RESEARCH AND CLINICAL DECISION-SUPPORT PROTOTYPE ONLY**  
> MediGuard AI is designed strictly as a clinical workflow accelerator and decision-support aid. It is **NOT** a certified Medical Device, diagnostic software, or substitute for trained clinical judgment.  
> 
> 1. **Physician Ownership**: The attending licensed physician/cardiologist retains **100% legal, diagnostic, and clinical responsibility** for all patient evaluations, diagnoses, prescriptions, and interventions.
> 2. **Uncalibrated Model Scores**: Model outputs represent experimental probabilistic tendencies on the uncalibrated interval `[0.00, 1.00]`. They are **never** confirmed diagnostic conclusions.
> 3. **Format Routing Rules**: Automated ML inference operates exclusively on validated **Digital 12-lead waveforms (CSV)**. Scanned paper ECG strips (JPG/PNG) and clinical PDF reports route directly to physician review queues with **zero automated scoring**.

---

## 🫀 Overview

**MediGuard AI** is an intelligent cardiology patient monitoring and clinical triage platform. It streamlines the ingestion, analysis, and clinical review of 12-lead electrocardiograms (ECGs) while maintaining strict clinical governance, audit logging, and role-based access control.

### Key Capabilities
- **Digital 12-Lead ECG Waveform Ingestion**: Ingestion and validation of raw voltage signals across standard leads (`I`, `II`, `III`, `aVR`, `aVL`, `aVF`, `V1`, `V2`, `V3`, `V4`, `V5`, `V6`).
- **ResNet-1D Deep Learning Architecture**: Pretrained on the 21,799-recording **PTB-XL** clinical electrocardiography dataset.
- **5 PTB-XL Superclasses**:
  - `NORM`: Normal Sinus Conduction / Baseline Rhythm
  - `MI`: Myocardial Infarction / Ischemia Patterns
  - `STTC`: ST / T-Wave Abnormalities & Repolarization Changes
  - `CD`: Conduction Disturbance (e.g., LBBB, RBBB, AV Blocks)
  - `HYP`: Ventricular & Atrial Hypertrophy
- **Interactive Multi-Lead Waveform Viewer**: High-frequency canvas rendering (Chart.js) with lead isolation filters and time-synced calibration grids.
- **Priority Triage Queue**: Dynamic urgency categorization (`Stat Emergency` → `Urgent` → `Routine`).
- **Cryptographic Audit Trail**: Immutable logging of all waveform uploads, model inferences, and doctor sign-offs with SHA-256 integrity verification.

---

## 🏗️ Architecture

```
                       ┌────────────────────────────────────────┐
                       │     Frontend Clinical Web Dashboard    │
                       │    (HTML5 / CSS3 / JavaScript ES6)     │
                       └───────────────────┬────────────────────┘
                                           │ REST / JSON (JWT Auth)
                                           ▼
                       ┌────────────────────────────────────────┐
                       │         Flask RESTful API Layer        │
                       │   (/api/auth, /api/ecg, /api/patients) │
                       └───────────────────┬────────────────────┘
                                           │
                    ┌──────────────────────┴──────────────────────┐
                    │                                             │
                    ▼                                             ▼
     ┌─────────────────────────────┐               ┌─────────────────────────────┐
     │  ResNet-1D Inference Engine │               │   Storage & DB Services     │
     │   (PyTorch CPU/CUDA)        │               │   (Encrypted Storage,       │
     │   PTB-XL 5 Superclasses     │               │    Audit Log, SQLite/PG)    │
     └─────────────────────────────┘               └─────────────────────────────┘
```

---

## 🚀 Quick Start Guide

### 1. Prerequisites
- Python 3.10+ (Python 3.11 recommended)
- Git 2.30+

### 2. Clone Repository & Setup Virtual Environment
```bash
# Clone the repository
git clone https://github.com/varshasadashiva/mediguard.git
cd mediguard

# Create and activate virtual environment
python -m venv .venv

# Windows:
.\.venv\Scripts\activate

# macOS / Linux:
source .venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Run the MediGuard Server
```bash
python run.py
```
Open your browser and navigate to:
```
http://127.0.0.1:5000/dashboard.html
```

---

## 👥 Default Clinical Demonstration Accounts

| Role | Email | Password | Access Level |
| :--- | :--- | :--- | :--- |
| **Admin** | `admin@mediguard.local` | `AdminPass123!` | System settings, audit logs, user management |
| **Cardiologist** | `cardio1@mediguard.local` | `CardioPass123!` | Full clinical review, ML waveform analysis, diagnosis sign-off |
| **Cardiologist** | `cardio2@mediguard.local` | `CardioPass123!` | Full clinical review, ML waveform analysis, diagnosis sign-off |
| **Clinical Staff** | `staff1@mediguard.local` | `StaffPass123!` | Patient intake, 12-lead ECG file ingestion, triage scheduling |

---

## 📁 Repository Directory Structure

```text
mediguard/
├── backend/
│   ├── blueprints/           # Modular Flask routes (ecg, auth, patients, dashboard)
│   ├── services/             # Core business logic (db, storage, inference, audit)
│   ├── worker/               # Background task queue & signal parsing
│   └── app.py                # Application factory & middleware configuration
├── frontend/
│   ├── dashboard.html        # Unified clinical cardiology workstation
│   ├── index.html            # Authentication & landing portal
│   ├── css/                  # Responsive styling & clinical theme tokens
│   ├── js/                   # Dashboard controllers, API clients, waveform renderers
│   └── samples/              # Verified synthetic 12-lead digital ECG benchmarks
├── ml/
│   ├── models/               # PyTorch ResNet-1D neural network definitions
│   ├── predict.py            # Signal ingestion and 5-class probability scoring
│   └── train.py              # PTB-XL dataset training pipeline
├── saved_models/
│   └── best_model.pt         # Calibrated ResNet-1D PyTorch model checkpoint
├── samples/
│   └── ecg/                  # Reference clinical 12-lead CSV waveforms
├── scripts/                  # CLI ingestion utilities and database seeding
├── tests/                    # Unit, integration, and security test suites
├── requirements.txt          # Python dependency specifications
└── README.md                 # Project documentation & clinical protocols
```

---

## 📄 License & Compliance Notice

This software is developed strictly for research, educational, and workflow demonstration purposes. In accordance with medical device regulations (FDA 21 CFR Part 820 / EU MDR 2017/745), this prototype is not cleared for autonomous clinical diagnostics.
