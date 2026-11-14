-- ==============================================================================
-- MediGuard AI – Core PostgreSQL Database Schema
-- Intelligent Cardiac Monitoring. Smarter Clinical Decisions.
--
-- Tables: users, patients, cardiac_history, ecg_reports, ecg_analysis,
--         doctor_reviews, notifications, follow_ups, audit_logs, jobs.
-- ==============================================================================

-- 1. EXTENSIONS
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 2. SEQUENCES
-- Auto-incrementing sequence for formatted clinical patient codes (e.g. MG-2026-000123)
CREATE SEQUENCE IF NOT EXISTS patient_code_seq START WITH 1 INCREMENT BY 1;

-- 3. UTILITY FUNCTIONS & TRIGGERS

-- Automatically update updated_at timestamp on row modification
CREATE OR REPLACE FUNCTION set_updated_at_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Format patient code trigger: MG-YYYY-000000
CREATE OR REPLACE FUNCTION generate_patient_code()
RETURNS TRIGGER AS $$
DECLARE
    current_yr TEXT;
    seq_val BIGINT;
BEGIN
    IF NEW.patient_code IS NULL OR NEW.patient_code = '' THEN
        current_yr := TO_CHAR(NOW(), 'YYYY');
        seq_val := NEXTVAL('patient_code_seq');
        NEW.patient_code := 'MG-' || current_yr || '-' || LPAD(seq_val::TEXT, 6, '0');
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ==============================================================================
-- 4. TABLE DEFINITIONS
-- ==============================================================================

-- ------------------------------------------------------------------------------
-- 4.1 USERS
-- Integrates with Supabase Auth or internal directory
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) NOT NULL UNIQUE,
    full_name VARCHAR(255) NOT NULL,
    role VARCHAR(32) NOT NULL CHECK (role IN ('admin', 'staff', 'cardiologist')),
    department VARCHAR(128) DEFAULT 'Cardiology',
    phone VARCHAR(32),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER trg_users_updated_at
BEFORE UPDATE ON users
FOR EACH ROW EXECUTE FUNCTION set_updated_at_timestamp();

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
CREATE INDEX IF NOT EXISTS idx_users_created_at ON users(created_at);

-- ------------------------------------------------------------------------------
-- 4.2 PATIENTS
-- Synthetic cardiac patient records (angioplasty, stents, MI)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS patients (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_code VARCHAR(32) NOT NULL UNIQUE,
    first_name VARCHAR(128) NOT NULL,
    last_name VARCHAR(128) NOT NULL,
    dob DATE NOT NULL,
    gender VARCHAR(16) NOT NULL CHECK (gender IN ('male', 'female', 'other')),
    blood_group VARCHAR(8) CHECK (blood_group IN ('A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-')),
    contact_phone VARCHAR(32),
    emergency_contact VARCHAR(255),
    primary_cardiologist_id UUID REFERENCES users(id) ON DELETE SET NULL,
    admission_date TIMESTAMPTZ,
    room_bed VARCHAR(64),
    urgency VARCHAR(32) NOT NULL DEFAULT 'routine' CHECK (urgency IN ('routine', 'urgent', 'stat_emergency')),
    is_archived BOOLEAN NOT NULL DEFAULT FALSE,
    is_synthetic BOOLEAN NOT NULL DEFAULT TRUE, -- Compliance with Rule 5 (Synthetic data only)
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER trg_patients_code_gen
BEFORE INSERT ON patients
FOR EACH ROW EXECUTE FUNCTION generate_patient_code();

CREATE TRIGGER trg_patients_updated_at
BEFORE UPDATE ON patients
FOR EACH ROW EXECUTE FUNCTION set_updated_at_timestamp();

CREATE INDEX IF NOT EXISTS idx_patients_code ON patients(patient_code);
CREATE INDEX IF NOT EXISTS idx_patients_primary_cardiologist ON patients(primary_cardiologist_id);
CREATE INDEX IF NOT EXISTS idx_patients_admission_date ON patients(admission_date);
CREATE INDEX IF NOT EXISTS idx_patients_created_at ON patients(created_at);

-- ------------------------------------------------------------------------------
-- 4.3 CARDIAC HISTORY
-- Longitudinal clinical cardiology tracking (angioplasty, stents, prior MI)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cardiac_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id UUID NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    condition_type VARCHAR(128) NOT NULL,
    diagnosis_date DATE,
    prior_mi BOOLEAN NOT NULL DEFAULT FALSE,
    prior_stent BOOLEAN NOT NULL DEFAULT FALSE,
    prior_cabg BOOLEAN NOT NULL DEFAULT FALSE,
    angioplasty_date DATE,
    stent_count INT NOT NULL DEFAULT 0,
    stent_type VARCHAR(128), -- e.g. "Everolimus-Eluting Stent (DES)"
    stent_location VARCHAR(128), -- e.g. "Proximal LAD 3.0x18mm", "Mid RCA 3.5x22mm"
    stent_details TEXT, -- e.g. "LAD Drug-Eluting Stent 3.0x18mm placed 2024-03-12"
    ejection_fraction NUMERIC(5,2) CHECK (ejection_fraction >= 10.0 AND ejection_fraction <= 85.0),
    risk_factors TEXT[], -- e.g. ARRAY['hypertension', 'type_2_diabetes', 'hyperlipidemia']
    comorbidities TEXT[], -- e.g. ARRAY['CKD Stage 3', 'COPD', 'Peripheral Artery Disease']
    medications TEXT[], -- legacy text array
    medications_structured JSONB DEFAULT '[]'::jsonb, -- structured: [{"name": "Aspirin", "dose": "81mg", "freq": "Daily"}]
    allergies TEXT[] DEFAULT ARRAY[]::TEXT[], -- e.g. ARRAY['Penicillin', 'Iodinated Contrast']
    doctor_comments TEXT,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER trg_cardiac_history_updated_at
BEFORE UPDATE ON cardiac_history
FOR EACH ROW EXECUTE FUNCTION set_updated_at_timestamp();

CREATE INDEX IF NOT EXISTS idx_cardiac_history_patient_id ON cardiac_history(patient_id);
CREATE INDEX IF NOT EXISTS idx_cardiac_history_created_at ON cardiac_history(created_at);

-- ------------------------------------------------------------------------------
-- 4.4 ECG REPORTS
-- Digital waveforms & archived documents with triage priority
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ecg_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id UUID NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    uploaded_by UUID REFERENCES users(id) ON DELETE SET NULL,
    assigned_cardiologist_id UUID REFERENCES users(id) ON DELETE SET NULL,
    recording_time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    file_path VARCHAR(512) NOT NULL,
    file_name VARCHAR(255) NOT NULL,
    file_type VARCHAR(32) NOT NULL CHECK (file_type IN ('digital_12lead', 'image', 'pdf', 'dicom_ecg')),
    urgency VARCHAR(32) NOT NULL DEFAULT 'routine' CHECK (urgency IN ('routine', 'urgent', 'stat_emergency')),
    status VARCHAR(32) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'analyzed', 'reviewed', 'flagged_urgent')),
    sampling_rate INT DEFAULT 500, -- Hz
    leads_present VARCHAR(64) DEFAULT 'I,II,III,aVR,aVL,aVF,V1,V2,V3,V4,V5,V6',
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER trg_ecg_reports_updated_at
BEFORE UPDATE ON ecg_reports
FOR EACH ROW EXECUTE FUNCTION set_updated_at_timestamp();

CREATE INDEX IF NOT EXISTS idx_ecg_reports_patient_id ON ecg_reports(patient_id);
CREATE INDEX IF NOT EXISTS idx_ecg_reports_uploaded_by ON ecg_reports(uploaded_by);
CREATE INDEX IF NOT EXISTS idx_ecg_reports_assigned_cardio ON ecg_reports(assigned_cardiologist_id);
CREATE INDEX IF NOT EXISTS idx_ecg_reports_status ON ecg_reports(status);
CREATE INDEX IF NOT EXISTS idx_ecg_reports_urgency ON ecg_reports(urgency);
CREATE INDEX IF NOT EXISTS idx_ecg_reports_created_at ON ecg_reports(created_at);

-- ------------------------------------------------------------------------------
-- 4.5 ECG ANALYSIS
-- Experimental deep learning inference scores (PTB-XL classes)
-- Strictly marked as experimental decision support, not definitive diagnosis.
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ecg_analysis (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    report_id UUID NOT NULL REFERENCES ecg_reports(id) ON DELETE CASCADE,
    model_version VARCHAR(64) NOT NULL DEFAULT 'mediguard_ecg_v1.0.0',
    norm_score NUMERIC(5,4) NOT NULL CHECK (norm_score >= 0.0 AND norm_score <= 1.0),
    mi_score NUMERIC(5,4) NOT NULL CHECK (mi_score >= 0.0 AND mi_score <= 1.0),
    sttc_score NUMERIC(5,4) NOT NULL CHECK (sttc_score >= 0.0 AND sttc_score <= 1.0),
    cd_score NUMERIC(5,4) NOT NULL CHECK (cd_score >= 0.0 AND cd_score <= 1.0),
    hyp_score NUMERIC(5,4) NOT NULL CHECK (hyp_score >= 0.0 AND hyp_score <= 1.0),
    signal_quality VARCHAR(32) NOT NULL DEFAULT 'high' CHECK (signal_quality IN ('high', 'moderate', 'noisy', 'unusable')),
    limitations TEXT DEFAULT 'Research/clinical decision support only. Model scores are experimental indicators, not calibrated diagnostic probabilities. Verified physician review mandatory.',
    is_demo BOOLEAN NOT NULL DEFAULT FALSE,
    raw_predictions JSONB DEFAULT '{}'::jsonb,
    disclaimer_acknowledged BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER trg_ecg_analysis_updated_at
BEFORE UPDATE ON ecg_analysis
FOR EACH ROW EXECUTE FUNCTION set_updated_at_timestamp();

CREATE INDEX IF NOT EXISTS idx_ecg_analysis_report_id ON ecg_analysis(report_id);
CREATE INDEX IF NOT EXISTS idx_ecg_analysis_model_version ON ecg_analysis(model_version);
CREATE INDEX IF NOT EXISTS idx_ecg_analysis_is_demo ON ecg_analysis(is_demo);
CREATE INDEX IF NOT EXISTS idx_ecg_analysis_created_at ON ecg_analysis(created_at);

-- ------------------------------------------------------------------------------
-- 4.6 DOCTOR REVIEWS
-- Certified clinical findings, verified diagnosis, and model agreement.
-- Doctors own 100% of the clinical diagnosis.
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS doctor_reviews (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    report_id UUID NOT NULL REFERENCES ecg_reports(id) ON DELETE CASCADE,
    cardiologist_id UUID REFERENCES users(id) ON DELETE SET NULL,
    clinical_findings TEXT NOT NULL,
    diagnosis TEXT NOT NULL,
    recommendation TEXT NOT NULL,
    agreement_with_model VARCHAR(32) NOT NULL CHECK (
        agreement_with_model IN ('agreed', 'partially_agreed', 'disagreed', 'inconclusive', 'not_applicable')
    ),
    is_urgent_escalation BOOLEAN NOT NULL DEFAULT FALSE,
    signed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER trg_doctor_reviews_updated_at
BEFORE UPDATE ON doctor_reviews
FOR EACH ROW EXECUTE FUNCTION set_updated_at_timestamp();

CREATE INDEX IF NOT EXISTS idx_doctor_reviews_report_id ON doctor_reviews(report_id);
CREATE INDEX IF NOT EXISTS idx_doctor_reviews_cardiologist ON doctor_reviews(cardiologist_id);
CREATE INDEX IF NOT EXISTS idx_doctor_reviews_agreement ON doctor_reviews(agreement_with_model);
CREATE INDEX IF NOT EXISTS idx_doctor_reviews_urgent ON doctor_reviews(is_urgent_escalation);
CREATE INDEX IF NOT EXISTS idx_doctor_reviews_created_at ON doctor_reviews(created_at);

-- ------------------------------------------------------------------------------
-- 4.7 NOTIFICATIONS
-- Real-time alerts and urgent findings dispatch to physicians
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    recipient_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    message TEXT NOT NULL,
    severity VARCHAR(32) NOT NULL DEFAULT 'info' CHECK (severity IN ('info', 'warning', 'critical', 'emergency')),
    link VARCHAR(255),
    is_read BOOLEAN NOT NULL DEFAULT FALSE,
    dedupe_key VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER trg_notifications_updated_at
BEFORE UPDATE ON notifications
FOR EACH ROW EXECUTE FUNCTION set_updated_at_timestamp();

CREATE INDEX IF NOT EXISTS idx_notifications_recipient_id ON notifications(recipient_id);
CREATE INDEX IF NOT EXISTS idx_notifications_is_read ON notifications(is_read);
CREATE INDEX IF NOT EXISTS idx_notifications_severity ON notifications(severity);
CREATE INDEX IF NOT EXISTS idx_notifications_dedupe_key ON notifications(dedupe_key);
CREATE INDEX IF NOT EXISTS idx_notifications_created_at ON notifications(created_at);

-- ------------------------------------------------------------------------------
-- 4.8 FOLLOW UPS
-- Post-procedure tracking for stent/MI recovery & outpatient checkups
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS follow_ups (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id UUID NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    doctor_id UUID REFERENCES users(id) ON DELETE SET NULL,
    scheduled_date DATE NOT NULL,
    follow_up_type VARCHAR(128) NOT NULL DEFAULT 'Post-Stent Routine Follow-up',
    status VARCHAR(32) NOT NULL DEFAULT 'scheduled' CHECK (status IN ('scheduled', 'completed', 'cancelled', 'missed')),
    notes TEXT,
    completed_at TIMESTAMPTZ,
    outcome TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER trg_follow_ups_updated_at
BEFORE UPDATE ON follow_ups
FOR EACH ROW EXECUTE FUNCTION set_updated_at_timestamp();

CREATE INDEX IF NOT EXISTS idx_follow_ups_patient_id ON follow_ups(patient_id);
CREATE INDEX IF NOT EXISTS idx_follow_ups_doctor_id ON follow_ups(doctor_id);
CREATE INDEX IF NOT EXISTS idx_follow_ups_status ON follow_ups(status);
CREATE INDEX IF NOT EXISTS idx_follow_ups_scheduled_date ON follow_ups(scheduled_date);
CREATE INDEX IF NOT EXISTS idx_follow_ups_created_at ON follow_ups(created_at);

-- ------------------------------------------------------------------------------
-- 4.9 AUDIT LOGS
-- Immutable clinical compliance audit trail. Log-once, read-only for admin.
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID, -- Nullable for unauthenticated or failed login events
    user_role VARCHAR(32),
    action VARCHAR(128) NOT NULL,
    entity_type VARCHAR(64) NOT NULL,
    entity_id VARCHAR(128),
    ip_address VARCHAR(64),
    user_agent TEXT,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_user_id ON audit_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_action ON audit_logs(action);
CREATE INDEX IF NOT EXISTS idx_audit_logs_entity ON audit_logs(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs(created_at);

-- ------------------------------------------------------------------------------
-- 4.10 JOBS
-- Async processing queue for ML inference, batch imports, notification dispatch
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_type VARCHAR(64) NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    status VARCHAR(32) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
    attempts INT NOT NULL DEFAULT 0,
    max_attempts INT NOT NULL DEFAULT 3,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER trg_jobs_updated_at
BEFORE UPDATE ON jobs
FOR EACH ROW EXECUTE FUNCTION set_updated_at_timestamp();

CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_job_type ON jobs(job_type);
CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at);
