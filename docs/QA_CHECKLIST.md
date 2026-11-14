# MediGuard AI – Clinical Verification & Manual QA Checklist

This checklist outlines the manual QA verification procedures to ensure that the MediGuard AI clinical cardiology prototype is functioning safely and adheres to all non-negotiable medical rules.

---

## 1. Authentication & Role-Based Access Control (RBAC)

- [ ] **Admin Login**:
  - Sign in as `admin@mediguard.local` / `AdminPass123!` (or `Admin@123`).
  - Verify access to: Patient Registry, Ingest Waveform, Doctor Reviews, System Audit Trail.
  - Verify admin badge displays: `ADMIN` in top bar.
- [ ] **Staff Login**:
  - Sign in as `staff1@mediguard.local` / `StaffPass123!`.
  - Verify access to: Register New Patient, Ingest Waveform, View Patient Profiles.
  - Verify Doctor Reviews navigation item is disabled or blocked (`403 Forbidden`).
  - Verify System Audit Trail is disabled or blocked (`403 Forbidden`).
- [ ] **Cardiologist Login**:
  - Sign in as `cardio1@mediguard.local` / `CardioPass123!`.
  - Verify access to: Prioritised Review Queue, Review Workspace, Signing Doctor Reviews.
  - Verify "Register New Patient" button is hidden (reserved for staff/admin).

---

## 2. Emergency Protocol (Rule 9 Verification)

- [ ] Click **"🚨 Emergency Protocol"** in the top navigation bar.
  - Verify internal hotlines modal opens displaying:
    - Code Blue: Ext. 2222
    - Cath Lab (STAT): Ext. 4400
    - Cardiac ICU: Ext. 3300
  - Click **"📋 Open Triage Checklist"** and confirm bedside ACS checklist appears with interactive items (ECG within 10m, Aspirin 325mg, Oxygen titration, Nitroglycerin evaluation, Dual IV & troponin).
- [ ] **Symptom Escalation**:
  - In patient profile or upload form, record an acute symptom (e.g. `chest_pain`).
  - Verify patient status immediately switches to `stat_emergency`.
  - Verify cardiologist receives an instant emergency notification without waiting for any ML job.

---

## 3. Multi-Pipeline ECG Ingestion (Rule 4 Verification)

- [ ] **Digital 12-Lead CSV Upload**:
  - Upload `samples/ecg/sample_12lead_acute_stemi.csv` with sampling rate 100 Hz.
  - Verify routed to `digital_12lead` pipeline.
  - Verify worker completes inference.
  - Inspect analysis modal: verify Chart.js 12-lead signal plots and 5 experimental score bars (`NORM`, `MI`, `STTC`, `CD`, `HYP`) labelled *"Experimental model score (uncalibrated)"*.
- [ ] **Clinical PDF Upload**:
  - Upload `samples/ecg/patient_MG-2026-000101_12lead_ecg.pdf`.
  - Verify routed to `pdf` pipeline.
  - Verify status marked `not_compatible_ml` (*"Not compatible with ML analysis – awaiting cardiologist review"*).
  - Verify **NO model scores** and **NO OCR interpretation** are shown.
- [ ] **Scanned Image Upload**:
  - Upload `samples/ecg/sample_scanned_rhythm_strip.jpg`.
  - Verify routed to `image` pipeline and marked `not_compatible_ml`.
- [ ] **Spoofed File Rejection**:
  - Upload `samples/ecg/sample_corrupted_spoofed.csv` (executable disguised as CSV).
  - Verify rejected with `400 Validation Error` (magic byte mismatch).

---

## 4. Prioritisation Engine & Safety Guardrails

- [ ] Inspect **Prioritised Review Queue**:
  - Verify patients are sorted: `URGENT` -> `PROMPT` -> `ROUTINE`.
  - Verify human-readable reason pills are shown for every decision.
- [ ] **Safety Rule Verification**:
  - Confirm that an elevated ML score (e.g. MI score 0.99) **never** creates an `URGENT` priority on its own without clinician urgency, acute symptoms, or recent PCI.

---

## 5. Review Workspace & Structured Signing

- [ ] Click **"Review"** on an unreviewed report in the priority queue.
  - Confirm Cardiologist Review Workspace modal opens.
  - Verify patient cardiac summary (stents, EF%, room) is loaded.
  - Enter structured findings:
    - Rhythm: *Normal Sinus Rhythm*
    - ST/T Wave: *ST Elevation (V2-V4 Anteroseptal)*
    - Conduction: *Normal AV Conduction*
    - Diagnosis: *Acute Anterior STEMI*
    - Recommendation: *Immediate Cath Lab Transfer*
  - Click **"💾 Save Draft"**: verify success toast; reopen workspace and confirm values persist.
  - Click **"✍️ Sign & Finalize Review"**:
    - Confirm report status updates to `reviewed`.
    - Confirm review appears in append-only history with `Version 1`.
    - If follow-up date was selected, confirm appointment appears in patient profile.

---

## 6. Notifications & In-App Bell

- [ ] Click the bell icon 🔔 in the top bar:
  - Verify unread count badge matches pending notifications.
  - Click **"Mark All Read"** and confirm badge resets to 0.
  - Verify duplicate uploads within 5 minutes do not flood notifications (cooldown active).
  - Verify emergency flag alerts are **never suppressed**.
