"""
MediGuard AI – Resilience & Recovery Test Suite
Tests /health endpoint, database availability reporting, backup/restore scripts,
fresh admin account generation, and encrypted ECG manifest integrity.
"""
import pytest
from pathlib import Path
from backend.services.auth_service import AuthService
from backend.services.db_service import db_service
from scripts.generate_ecg_manifest import verify_all_in_dir, create_sample_encrypted_ecg_suite
from scripts.test_backup_restore import (
    test_scripts_exist,
    test_script_contents_and_flags,
    test_backup_integrity_hash_simulation
)


def test_health_endpoints(client):
    """Test both /health and /api/health respond with 200 and healthy status."""
    for ep in ["/health", "/api/health"]:
        resp = client.get(ep)
        assert resp.status_code == 200, f"Expected 200 on {ep}, got {resp.status_code}"
        data = resp.get_json()
        assert data["status"] == "healthy"
        assert "database" in data
        assert data["database"]["users_count"] >= 5
        assert data["database"]["patients_count"] >= 30
        assert "disclaimer" in data


def test_fresh_admin_account_credentials(client):
    """Verify fresh admin account can sign in and obtain admin token."""
    creds_file = Path(__file__).resolve().parent.parent / "admin_credentials.txt"
    assert creds_file.exists(), "admin_credentials.txt must exist"

    lines = creds_file.read_text(encoding="utf-8").splitlines()
    email = None
    password = None
    for line in lines:
        if line.startswith("Email:"):
            email = line.split(":", 1)[1].strip()
        elif line.startswith("Password:"):
            password = line.split(":", 1)[1].strip()

    assert email and password, "Failed to read fresh admin credentials from file"

    resp = client.post("/api/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, f"Login failed for fresh admin: {resp.get_json()}"
    data = resp.get_json()["data"]
    assert data["user"]["role"] == "admin"
    assert "access_token" in data

    # Verify fresh admin token has access to admin-only audit logs
    token = data["access_token"]
    audit_resp = client.get("/api/audit/logs", headers={"Authorization": f"Bearer {token}"})
    assert audit_resp.status_code == 200


def test_backup_and_restore_scripts():
    """Verify pg_backup and pg_restore scripts and integrity verification."""
    test_scripts_exist()
    test_script_contents_and_flags()
    test_backup_integrity_hash_simulation()


def test_encrypted_ecg_manifest_integrity():
    """Verify per-file manifest generation and SHA-256 verification."""
    create_sample_encrypted_ecg_suite()
    passed, failed = verify_all_in_dir()
    assert passed >= 4
    assert failed == 0
