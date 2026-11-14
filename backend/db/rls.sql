-- ==============================================================================
-- MediGuard AI – Row-Level Security (RLS) Policies
-- Intelligent Cardiac Monitoring. Smarter Clinical Decisions.
--
-- Security Rules:
-- 1. Deny by default on all tables.
-- 2. Staff can read/write patients and ecg_reports, but NOT doctor_reviews.
-- 3. Cardiologists can read assigned patients (and all patients if admin) and write doctor_reviews.
-- 4. Users read only their own notifications.
-- 5. Audit logs: insert-only for service_role, read-only for admin.
-- ==============================================================================

-- 0. CLEAN DATABASE ROLE & SCHEMA COMPATIBILITY SETUP
-- Ensures script applies cleanly on fresh standalone PostgreSQL or Supabase
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'authenticated') THEN
        CREATE ROLE authenticated;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'service_role') THEN
        CREATE ROLE service_role;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'anon') THEN
        CREATE ROLE anon;
    END IF;
END $$;

CREATE SCHEMA IF NOT EXISTS auth;
CREATE OR REPLACE FUNCTION auth.uid()
RETURNS UUID AS $$
BEGIN
    RETURN NULLIF(current_setting('request.jwt.claim.sub', true), '')::uuid;
EXCEPTION WHEN OTHERS THEN
    RETURN NULL;
END;
$$ LANGUAGE plpgsql STABLE;

-- 1. ENABLE ROW LEVEL SECURITY ON ALL 10 TABLES
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE patients ENABLE ROW LEVEL SECURITY;
ALTER TABLE cardiac_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE ecg_reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE ecg_analysis ENABLE ROW LEVEL SECURITY;
ALTER TABLE doctor_reviews ENABLE ROW LEVEL SECURITY;
ALTER TABLE notifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE follow_ups ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE jobs ENABLE ROW LEVEL SECURITY;

-- 2. HELPER FUNCTIONS FOR ROLE AND PERMISSIONS
CREATE OR REPLACE FUNCTION get_current_user_role()
RETURNS VARCHAR AS $$
DECLARE
    user_role VARCHAR;
BEGIN
    -- Check if running via service role key
    IF (NULLIF(current_setting('request.jwt.claims', true), '')::jsonb ->> 'role') = 'service_role' THEN
        RETURN 'service_role';
    END IF;

    -- Look up role from public.users table for current auth.uid()
    SELECT role INTO user_role
    FROM users
    WHERE id = auth.uid();

    RETURN COALESCE(user_role, 'anonymous');
END;
$$ LANGUAGE plpgsql SECURITY DEFINER STABLE;

CREATE OR REPLACE FUNCTION is_admin()
RETURNS BOOLEAN AS $$
BEGIN
    RETURN get_current_user_role() IN ('admin', 'service_role');
END;
$$ LANGUAGE plpgsql SECURITY DEFINER STABLE;

CREATE OR REPLACE FUNCTION is_cardiologist()
RETURNS BOOLEAN AS $$
BEGIN
    RETURN get_current_user_role() IN ('cardiologist', 'admin', 'service_role');
END;
$$ LANGUAGE plpgsql SECURITY DEFINER STABLE;

CREATE OR REPLACE FUNCTION is_clinical_staff()
RETURNS BOOLEAN AS $$
BEGIN
    RETURN get_current_user_role() IN ('staff', 'admin', 'service_role');
END;
$$ LANGUAGE plpgsql SECURITY DEFINER STABLE;

-- ==============================================================================
-- 3. TABLE SPECIFIC POLICIES
-- ==============================================================================

-- ------------------------------------------------------------------------------
-- 3.1 USERS
-- Authenticated users can view their own profile; admins can view & manage all users.
-- ------------------------------------------------------------------------------
DROP POLICY IF EXISTS "Users can read own profile" ON users;
CREATE POLICY "Users can read own profile" ON users
    FOR SELECT TO authenticated
    USING (id = auth.uid() OR is_admin());

DROP POLICY IF EXISTS "Admins can insert or update users" ON users;
CREATE POLICY "Admins can insert or update users" ON users
    FOR ALL TO authenticated
    USING (is_admin())
    WITH CHECK (is_admin());

DROP POLICY IF EXISTS "Service role full access users" ON users;
CREATE POLICY "Service role full access users" ON users
    FOR ALL TO service_role
    USING (true)
    WITH CHECK (true);

-- ------------------------------------------------------------------------------
-- 3.2 PATIENTS
-- Staff: read and write all patient records.
-- Cardiologist: read assigned patients (or all if admin).
-- ------------------------------------------------------------------------------
DROP POLICY IF EXISTS "Staff can read all patients" ON patients;
CREATE POLICY "Staff can read all patients" ON patients
    FOR SELECT TO authenticated
    USING (is_clinical_staff());

DROP POLICY IF EXISTS "Staff can insert patients" ON patients;
CREATE POLICY "Staff can insert patients" ON patients
    FOR INSERT TO authenticated
    WITH CHECK (is_clinical_staff());

DROP POLICY IF EXISTS "Staff can update patients" ON patients;
CREATE POLICY "Staff can update patients" ON patients
    FOR UPDATE TO authenticated
    USING (is_clinical_staff())
    WITH CHECK (is_clinical_staff());

DROP POLICY IF EXISTS "Cardiologists can view assigned patients" ON patients;
CREATE POLICY "Cardiologists can view assigned patients" ON patients
    FOR SELECT TO authenticated
    USING (
        is_admin() OR
        (get_current_user_role() = 'cardiologist' AND primary_cardiologist_id = auth.uid())
    );

DROP POLICY IF EXISTS "Service role full access patients" ON patients;
CREATE POLICY "Service role full access patients" ON patients
    FOR ALL TO service_role
    USING (true)
    WITH CHECK (true);

-- ------------------------------------------------------------------------------
-- 3.3 CARDIAC HISTORY
-- Clinical staff and assigned cardiologists can read; staff and cardiologists can update.
-- ------------------------------------------------------------------------------
DROP POLICY IF EXISTS "Clinical staff can view cardiac history" ON cardiac_history;
CREATE POLICY "Clinical staff can view cardiac history" ON cardiac_history
    FOR SELECT TO authenticated
    USING (
        is_clinical_staff() OR
        is_admin() OR
        (get_current_user_role() = 'cardiologist' AND EXISTS (
            SELECT 1 FROM patients p
            WHERE p.id = cardiac_history.patient_id AND p.primary_cardiologist_id = auth.uid()
        ))
    );

DROP POLICY IF EXISTS "Clinical staff can manage cardiac history" ON cardiac_history;
CREATE POLICY "Clinical staff can manage cardiac history" ON cardiac_history
    FOR ALL TO authenticated
    USING (is_clinical_staff() OR is_cardiologist())
    WITH CHECK (is_clinical_staff() OR is_cardiologist());

DROP POLICY IF EXISTS "Service role full access cardiac_history" ON cardiac_history;
CREATE POLICY "Service role full access cardiac_history" ON cardiac_history
    FOR ALL TO service_role
    USING (true)
    WITH CHECK (true);

-- ------------------------------------------------------------------------------
-- 3.4 ECG REPORTS
-- Staff can read/write reports. Cardiologists can view assigned or urgent reports.
-- ------------------------------------------------------------------------------
DROP POLICY IF EXISTS "Staff can read all ecg reports" ON ecg_reports;
CREATE POLICY "Staff can read all ecg reports" ON ecg_reports
    FOR SELECT TO authenticated
    USING (is_clinical_staff());

DROP POLICY IF EXISTS "Staff can upload ecg reports" ON ecg_reports;
CREATE POLICY "Staff can upload ecg reports" ON ecg_reports
    FOR INSERT TO authenticated
    WITH CHECK (is_clinical_staff());

DROP POLICY IF EXISTS "Staff can update ecg reports" ON ecg_reports;
CREATE POLICY "Staff can update ecg reports" ON ecg_reports
    FOR UPDATE TO authenticated
    USING (is_clinical_staff())
    WITH CHECK (is_clinical_staff());

DROP POLICY IF EXISTS "Cardiologists can view assigned or escalated ecg reports" ON ecg_reports;
CREATE POLICY "Cardiologists can view assigned or escalated ecg reports" ON ecg_reports
    FOR SELECT TO authenticated
    USING (
        is_admin() OR
        (get_current_user_role() = 'cardiologist' AND (
            assigned_cardiologist_id = auth.uid() OR
            urgency IN ('urgent', 'stat_emergency') OR
            status = 'flagged_urgent'
        ))
    );

DROP POLICY IF EXISTS "Service role full access ecg_reports" ON ecg_reports;
CREATE POLICY "Service role full access ecg_reports" ON ecg_reports
    FOR ALL TO service_role
    USING (true)
    WITH CHECK (true);

-- ------------------------------------------------------------------------------
-- 3.5 ECG ANALYSIS
-- Read access for clinical staff and assigned cardiologists.
-- Write access restricted to service_role / background worker.
-- ------------------------------------------------------------------------------
DROP POLICY IF EXISTS "Clinical team can view ecg analysis" ON ecg_analysis;
CREATE POLICY "Clinical team can view ecg analysis" ON ecg_analysis
    FOR SELECT TO authenticated
    USING (
        is_admin() OR
        is_clinical_staff() OR
        is_cardiologist()
    );

DROP POLICY IF EXISTS "Only service role or admin can write ecg analysis" ON ecg_analysis;
CREATE POLICY "Only service role or admin can write ecg analysis" ON ecg_analysis
    FOR ALL TO authenticated
    USING (is_admin())
    WITH CHECK (is_admin());

DROP POLICY IF EXISTS "Service role full access ecg_analysis" ON ecg_analysis;
CREATE POLICY "Service role full access ecg_analysis" ON ecg_analysis
    FOR ALL TO service_role
    USING (true)
    WITH CHECK (true);

-- ------------------------------------------------------------------------------
-- 3.6 DOCTOR REVIEWS
-- Strict Rule: Staff cannot read or write doctor reviews.
-- Only cardiologists (and admins) can read and write doctor reviews.
-- ------------------------------------------------------------------------------
DROP POLICY IF EXISTS "Cardiologists and admins can view doctor reviews" ON doctor_reviews;
CREATE POLICY "Cardiologists and admins can view doctor reviews" ON doctor_reviews
    FOR SELECT TO authenticated
    USING (is_cardiologist());

DROP POLICY IF EXISTS "Cardiologists can create and sign doctor reviews" ON doctor_reviews;
CREATE POLICY "Cardiologists can create and sign doctor reviews" ON doctor_reviews
    FOR INSERT TO authenticated
    WITH CHECK (
        is_cardiologist() AND (cardiologist_id = auth.uid() OR is_admin())
    );

DROP POLICY IF EXISTS "Cardiologists can update their own doctor reviews" ON doctor_reviews;
CREATE POLICY "Cardiologists can update their own doctor reviews" ON doctor_reviews
    FOR UPDATE TO authenticated
    USING (
        is_admin() OR (is_cardiologist() AND cardiologist_id = auth.uid())
    )
    WITH CHECK (
        is_admin() OR (is_cardiologist() AND cardiologist_id = auth.uid())
    );

DROP POLICY IF EXISTS "Service role full access doctor_reviews" ON doctor_reviews;
CREATE POLICY "Service role full access doctor_reviews" ON doctor_reviews
    FOR ALL TO service_role
    USING (true)
    WITH CHECK (true);

-- ------------------------------------------------------------------------------
-- 3.7 NOTIFICATIONS
-- Strict Rule: Users read only their own notifications.
-- ------------------------------------------------------------------------------
DROP POLICY IF EXISTS "Users can view own notifications" ON notifications;
CREATE POLICY "Users can view own notifications" ON notifications
    FOR SELECT TO authenticated
    USING (recipient_id = auth.uid() OR is_admin());

DROP POLICY IF EXISTS "Users can mark own notifications as read" ON notifications;
CREATE POLICY "Users can mark own notifications as read" ON notifications
    FOR UPDATE TO authenticated
    USING (recipient_id = auth.uid())
    WITH CHECK (recipient_id = auth.uid());

DROP POLICY IF EXISTS "Service role full access notifications" ON notifications;
CREATE POLICY "Service role full access notifications" ON notifications
    FOR ALL TO service_role
    USING (true)
    WITH CHECK (true);

-- ------------------------------------------------------------------------------
-- 3.8 FOLLOW UPS
-- Clinical staff and assigned doctors can read and schedule follow-ups.
-- ------------------------------------------------------------------------------
DROP POLICY IF EXISTS "Clinical staff and doctors can view follow ups" ON follow_ups;
CREATE POLICY "Clinical staff and doctors can view follow ups" ON follow_ups
    FOR SELECT TO authenticated
    USING (is_clinical_staff() OR is_cardiologist());

DROP POLICY IF EXISTS "Clinical staff and doctors can manage follow ups" ON follow_ups;
CREATE POLICY "Clinical staff and doctors can manage follow ups" ON follow_ups
    FOR ALL TO authenticated
    USING (is_clinical_staff() OR is_cardiologist())
    WITH CHECK (is_clinical_staff() OR is_cardiologist());

DROP POLICY IF EXISTS "Service role full access follow_ups" ON follow_ups;
CREATE POLICY "Service role full access follow_ups" ON follow_ups
    FOR ALL TO service_role
    USING (true)
    WITH CHECK (true);

-- ------------------------------------------------------------------------------
-- 3.9 AUDIT LOGS
-- Strict Rule: Insert-only for service role / backend; read-only for admin.
-- Deny update or delete for all users to guarantee audit immutability.
-- ------------------------------------------------------------------------------
DROP POLICY IF EXISTS "Admins can view audit logs" ON audit_logs;
CREATE POLICY "Admins can view audit logs" ON audit_logs
    FOR SELECT TO authenticated
    USING (is_admin());

DROP POLICY IF EXISTS "Service role can insert audit logs" ON audit_logs;
CREATE POLICY "Service role can insert audit logs" ON audit_logs
    FOR INSERT TO service_role
    WITH CHECK (true);

DROP POLICY IF EXISTS "Backend authenticated can insert audit logs" ON audit_logs;
CREATE POLICY "Backend authenticated can insert audit logs" ON audit_logs
    FOR INSERT TO authenticated
    WITH CHECK (true);

-- ------------------------------------------------------------------------------
-- 3.10 JOBS
-- Service role only
-- ------------------------------------------------------------------------------
DROP POLICY IF EXISTS "Service role can manage jobs" ON jobs;
CREATE POLICY "Service role can manage jobs" ON jobs
    FOR ALL TO service_role
    USING (true)
    WITH CHECK (true);

DROP POLICY IF EXISTS "Admins can view jobs" ON jobs;
CREATE POLICY "Admins can view jobs" ON jobs
    FOR SELECT TO authenticated
    USING (is_admin());
