# MediGuard AI – Supabase Setup Guide
**Intelligent Cardiac Monitoring. Smarter Clinical Decisions.**

This guide details the exact steps to configure your live PostgreSQL database, authentication, and secure private storage buckets on Supabase.

---

## 📋 Prerequisites
- A Supabase account ([supabase.com](https://supabase.com))
- Supabase Project created in your preferred cloud region

---

## Step 1: Create a New Supabase Project
1. Log in to the [Supabase Dashboard](https://supabase.com/dashboard).
2. Click **New Project**.
3. Name the project `mediguard-ai`.
4. Choose a strong Database Password (store it in your password manager).
5. Select your desired region and click **Create new project**.

---

## Step 2: Execute Database Schema (`schema.sql`)
1. In the Supabase Dashboard, navigate to the **SQL Editor** (icon on left navigation bar).
2. Click **New Query**.
3. Copy the entire contents of [backend/db/schema.sql](file:///C:/Users/YOGA%20F9IN/.gemini/antigravity/scratch/mediguard-ai/backend/db/schema.sql).
4. Paste it into the SQL Editor and click **Run**.
5. Verify that the 10 core tables are created:
   - `users`
   - `patients`
   - `cardiac_history`
   - `ecg_reports`
   - `ecg_analysis`
   - `doctor_reviews`
   - `notifications`
   - `follow_ups`
   - `audit_logs`
   - `jobs`

---

## Step 3: Apply Row-Level Security Policies (`rls.sql`)
1. In the **SQL Editor**, open another **New Query**.
2. Copy the entire contents of [backend/db/rls.sql](file:///C:/Users/YOGA%20F9IN/.gemini/antigravity/scratch/mediguard-ai/backend/db/rls.sql).
3. Paste into the editor and click **Run**.
4. Navigate to **Authentication > Policies** to verify:
   - RLS is **Enabled** on all 10 tables.
   - Staff cannot read or insert into `doctor_reviews`.
   - Cardiologists can read assigned patients and write doctor reviews.
   - Audit logs are read-only for admin.

---

## Step 4: Create the Private Storage Bucket (`ecg-files`)
1. In the Supabase Dashboard, click on **Storage** in the left menu.
2. Click **New Bucket**.
3. Enter Bucket Name: `ecg-files`.
4. Ensure **Public bucket is UNCHECKED (Private)**.
   *Clinical waveforms, DICOM files, and patient reports must remain private and authenticated.*
5. Under Bucket Policies, configure read/write permissions for `authenticated` users with staff/cardiologist roles, or manage via backend service-role key.

---

## Step 5: Configure Supabase Auth Users
You can create the 5 synthetic demo users in **Authentication > Users** in Supabase:
- `admin@mediguard.local` (Password: `AdminPass123!`)
- `staff1@mediguard.local` (Password: `StaffPass123!`)
- `staff2@mediguard.local` (Password: `StaffPass123!`)
- `cardio1@mediguard.local` (Password: `CardioPass123!`)
- `cardio2@mediguard.local` (Password: `CardioPass123!`)

Once users are registered in Supabase Auth, insert their corresponding profile records into `public.users` matching their Auth UUID:
```sql
-- Link Supabase auth.users to public.users table
INSERT INTO public.users (id, email, full_name, role, department)
VALUES
  ('<AUTH_USER_UUID_ADMIN>', 'admin@mediguard.local', 'Dr. Sarah Chen, MD', 'admin', 'Cardiology & Clinical Informatics'),
  ('<AUTH_USER_UUID_STAFF1>', 'staff1@mediguard.local', 'RN Robert Davis', 'staff', 'Cardiac Care Unit (CCU)'),
  ('<AUTH_USER_UUID_STAFF2>', 'staff2@mediguard.local', 'RN Maria Santos', 'staff', 'Telemetry Monitoring Ward'),
  ('<AUTH_USER_UUID_CARDIO1>', 'cardio1@mediguard.local', 'Dr. Alexander Hayes, FACC', 'cardiologist', 'Interventional Cardiology'),
  ('<AUTH_USER_UUID_CARDIO2>', 'cardio2@mediguard.local', 'Dr. Priya Patel, FESC', 'cardiologist', 'Electrophysiology')
ON CONFLICT (email) DO UPDATE SET
  role = EXCLUDED.role,
  full_name = EXCLUDED.full_name;
```

---

## Step 6: Configure `.env` File
In your project root, open `.env` and fill in the values obtained from **Project Settings > API**:

```env
FLASK_ENV=development
DEBUG=True
PORT=5000

# Supabase API Settings
SUPABASE_URL=https://<your-project-ref>.supabase.co
SUPABASE_ANON_KEY=eyJhbGciOi...
SUPABASE_SERVICE_ROLE_KEY=eyJhbGciOi... # RULE 6: Strictly server-side only!
SUPABASE_JWT_SECRET=your-supabase-jwt-secret
SUPABASE_ECG_BUCKET=ecg-files

# Switch off offline demo mode when connecting to live Supabase
OFFLINE_DEMO_MODE=false
```

---

## Step 7: Verify Connection
Run the test suite or seed script against your Supabase instance:
```bash
python backend/db/seed.py
pytest
```
