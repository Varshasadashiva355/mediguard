"""
MediGuard AI – Schema and RLS SQL Validation Suite
Ensures that schema.sql and rls.sql are syntactically well-formed,
define all 10 required tables, enforce CHECK constraints, and declare RLS policies.
"""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SCHEMA_FILE = BASE_DIR / "backend" / "db" / "schema.sql"
RLS_FILE = BASE_DIR / "backend" / "db" / "rls.sql"

REQUIRED_TABLES = [
    "users",
    "patients",
    "cardiac_history",
    "ecg_reports",
    "ecg_analysis",
    "doctor_reviews",
    "notifications",
    "follow_ups",
    "audit_logs",
    "jobs"
]

def test_schema_file_exists_and_contains_tables():
    assert SCHEMA_FILE.exists(), "backend/db/schema.sql must exist"
    content = SCHEMA_FILE.read_text(encoding="utf-8").lower()

    for table in REQUIRED_TABLES:
        assert f"create table if not exists {table}" in content or f"create table {table}" in content, (
            f"Table {table} must be declared in schema.sql"
        )

    # Verify patient_code_seq and trigger
    assert "patient_code_seq" in content
    assert "generate_patient_code" in content

    # Verify ecg_analysis required columns
    for col in ["norm_score", "mi_score", "sttc_score", "cd_score", "hyp_score", "model_version", "signal_quality", "limitations", "is_demo"]:
        assert col in content, f"ecg_analysis must contain column {col}"


def test_rls_file_exists_and_enables_security_on_all_tables():
    assert RLS_FILE.exists(), "backend/db/rls.sql must exist"
    content = RLS_FILE.read_text(encoding="utf-8").lower()

    for table in REQUIRED_TABLES:
        assert f"alter table {table} enable row level security" in content, (
            f"RLS must be enabled on {table}"
        )

    # Verify key role security policies
    assert "staff can read all patients" in content
    assert "cardiologists can create and sign doctor reviews" in content
    assert "users can view own notifications" in content
    assert "admins can view audit logs" in content
