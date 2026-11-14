"""
MediGuard AI – Row-Level Security (RLS) & RBAC Verification Suite
Verifies SQL declarations, role functions, and active access rules across all tables.
"""
import sys
import logging
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from backend.app import create_app
from backend.config import TestConfig
from backend.db.seed import seed_all
from backend.services.db_service import db_service
from backend.services.auth_service import AuthService

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("mediguard.rls_verify")

REQUIRED_TABLES = [
    "users", "patients", "cardiac_history", "ecg_reports", "ecg_analysis",
    "doctor_reviews", "notifications", "follow_ups", "audit_logs", "jobs"
]

def verify_sql_rls_declarations():
    """Verify that backend/db/rls.sql enables RLS on all 10 tables and defines policies."""
    rls_path = BASE_DIR / "backend" / "db" / "rls.sql"
    assert rls_path.exists(), f"Missing {rls_path}"
    content = rls_path.read_text(encoding="utf-8").lower()

    logger.info("1. Verifying RLS enabled on all 10 core tables in SQL...")
    for table in REQUIRED_TABLES:
        pattern = f"alter table {table} enable row level security"
        assert pattern in content, f"Table '{table}' does not have RLS enabled in rls.sql"
        logger.info("   [OK] RLS enabled on: %s", table)

    logger.info("2. Verifying role security helper functions in SQL...")
    assert "create or replace function get_current_user_role" in content
    assert "create or replace function is_admin" in content
    assert "create or replace function is_cardiologist" in content
    assert "create or replace function is_clinical_staff" in content
    assert "create or replace function auth.uid" in content
    logger.info("   [OK] All 5 security functions defined.")

    logger.info("3. Verifying key table security policies in SQL...")
    assert "staff can read all patients" in content
    assert "cardiologists can view assigned patients" in content
    assert "cardiologists can create and sign doctor reviews" in content
    assert "admins can view audit logs" in content
    assert "users can view own notifications" in content
    logger.info("   [OK] All key RLS policies present in SQL.")


def verify_active_rbac_enforcement():
    """Simulate API requests across roles to ensure RBAC and RLS isolation."""
    logger.info("4. Testing live RBAC & RLS role enforcement via API test client...")
    app = create_app(TestConfig)

    with app.app_context():
        seed_all()
        admin_user = db_service.get_user_by_email("admin@mediguard.local")
        staff_user = db_service.get_user_by_email("staff1@mediguard.local")
        cardio_user = db_service.get_user_by_email("cardio1@mediguard.local")
        fresh_admin_user = db_service.get_user_by_email("fresh_admin@mediguard.local")

        assert admin_user, "Admin user missing"
        assert staff_user, "Staff user missing"
        assert cardio_user, "Cardiologist user missing"
        assert fresh_admin_user, "Fresh admin user missing"

        admin_tok = AuthService.generate_token(admin_user)
        staff_tok = AuthService.generate_token(staff_user)
        cardio_tok = AuthService.generate_token(cardio_user)
        fresh_admin_tok = AuthService.generate_token(fresh_admin_user)

    client = app.test_client()

    # Rule A: Staff cannot access doctor reviews (403 Forbidden)
    r = client.get("/api/reviews", headers={"Authorization": f"Bearer {staff_tok}"})
    assert r.status_code == 403, f"Expected 403 for staff on /api/reviews, got {r.status_code}"
    logger.info("   [PASS] Staff blocked from Doctor Reviews (403 Forbidden)")

    # Rule B: Cardiologist can access doctor reviews (200 OK)
    r = client.get("/api/reviews", headers={"Authorization": f"Bearer {cardio_tok}"})
    assert r.status_code == 200, f"Expected 200 for cardio on /api/reviews, got {r.status_code}"
    logger.info("   [PASS] Cardiologist allowed on Doctor Reviews (200 OK)")

    # Rule C: Staff cannot access audit logs (403 Forbidden)
    r = client.get("/api/audit/logs", headers={"Authorization": f"Bearer {staff_tok}"})
    assert r.status_code == 403, f"Expected 403 for staff on /api/audit/logs, got {r.status_code}"
    logger.info("   [PASS] Staff blocked from Audit Logs (403 Forbidden)")

    # Rule D: Cardiologist cannot access audit logs (403 Forbidden)
    r = client.get("/api/audit/logs", headers={"Authorization": f"Bearer {cardio_tok}"})
    assert r.status_code == 403, f"Expected 403 for cardio on /api/audit/logs, got {r.status_code}"
    logger.info("   [PASS] Cardiologist blocked from Audit Logs (403 Forbidden)")

    # Rule E: Admin can access audit logs (200 OK)
    r = client.get("/api/audit/logs", headers={"Authorization": f"Bearer {admin_tok}"})
    assert r.status_code == 200, f"Expected 200 for admin on /api/audit/logs, got {r.status_code}"
    logger.info("   [PASS] Primary Admin allowed on Audit Logs (200 OK)")

    # Rule F: Freshly generated Admin can also access audit logs (200 OK)
    r = client.get("/api/audit/logs", headers={"Authorization": f"Bearer {fresh_admin_tok}"})
    assert r.status_code == 200, f"Expected 200 for fresh admin on /api/audit/logs, got {r.status_code}"
    logger.info("   [PASS] Fresh Admin account allowed on Audit Logs (200 OK)")

    # Rule G: Unauthenticated request rejected (401 Unauthorized)
    r = client.get("/api/patients")
    assert r.status_code == 401, f"Expected 401 for unauthenticated on /api/patients, got {r.status_code}"
    logger.info("   [PASS] Unauthenticated request denied (401 Unauthorized)")

    # Rule H: Authenticated user can read patients (200 OK)
    r = client.get("/api/patients", headers={"Authorization": f"Bearer {staff_tok}"})
    assert r.status_code == 200, f"Expected 200 for staff on /api/patients, got {r.status_code}"
    logger.info("   [PASS] Staff authorized for Patient registry (200 OK)")

    # Rule I: Staff blocked from Prioritised Review Queue (403 Forbidden)
    r = client.get("/api/reviews/queue", headers={"Authorization": f"Bearer {staff_tok}"})
    assert r.status_code == 403, f"Expected 403 for staff on /api/reviews/queue, got {r.status_code}"
    logger.info("   [PASS] Staff blocked from Prioritised Review Queue (403 Forbidden)")

    # Rule J: Cardiologist allowed on Prioritised Review Queue (200 OK)
    r = client.get("/api/reviews/queue", headers={"Authorization": f"Bearer {cardio_tok}"})
    assert r.status_code == 200, f"Expected 200 for cardio on /api/reviews/queue, got {r.status_code}"
    logger.info("   [PASS] Cardiologist allowed on Prioritised Review Queue (200 OK)")

    # Rule K: Staff blocked from saving Review Drafts (403 Forbidden)
    r = client.post("/api/reviews/draft", json={"report_id": "rep-test"}, headers={"Authorization": f"Bearer {staff_tok}"})
    assert r.status_code == 403, f"Expected 403 for staff on /api/reviews/draft, got {r.status_code}"
    logger.info("   [PASS] Staff blocked from saving Review Drafts (403 Forbidden)")

    # Rule L: Unauthenticated access to Notifications blocked (401 Unauthorized)
    r = client.get("/api/notifications")
    assert r.status_code == 401, f"Expected 401 for unauth on /api/notifications, got {r.status_code}"
    logger.info("   [PASS] Unauthenticated access to Notifications denied (401 Unauthorized)")


def main():
    print("=" * 65)
    print("  MEDIGUARD AI – ROW LEVEL SECURITY (RLS) & RBAC VERIFICATION")
    print("=" * 65)
    verify_sql_rls_declarations()
    verify_active_rbac_enforcement()
    print("=" * 65)
    print("  ALL RLS & RBAC VERIFICATION CHECKS PASSED SUCCESSFULLY (12/12)")
    print("=" * 65)


if __name__ == "__main__":
    main()
