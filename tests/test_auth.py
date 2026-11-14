"""
MediGuard AI – Authentication & Audit Log Test Suite
Validates login for each role, credential rejection, token validation, audit logging, and logout.
"""
import pytest
from backend.services.audit_service import audit_service


def test_login_success_all_roles(client):
    """Test login succeeds for Admin, Staff, and Cardiologist."""
    users_to_test = [
        ("admin@mediguard.local", "AdminPass123!", "admin"),
        ("staff1@mediguard.local", "StaffPass123!", "staff"),
        ("cardio1@mediguard.local", "CardioPass123!", "cardiologist"),
    ]

    for email, password, expected_role in users_to_test:
        resp = client.post("/api/auth/login", json={"email": email, "password": password})
        assert resp.status_code == 200, f"Login failed for {email}: {resp.get_json()}"
        data = resp.get_json()["data"]
        assert "access_token" in data
        assert data["user"]["role"] == expected_role
        assert data["user"]["email"] == email


def test_login_failure_wrong_password(client):
    """Wrong password returns 401 and writes audit log."""
    resp = client.post("/api/auth/login", json={
        "email": "cardio1@mediguard.local",
        "password": "WrongPassword999!"
    })
    assert resp.status_code == 401
    err = resp.get_json()
    assert err["error"] == "Unauthorized"

    # Verify audit log recorded LOGIN_FAILURE
    logs = audit_service.get_logs(action="LOGIN_FAILURE")
    assert len(logs) > 0
    latest_failure = logs[0]
    assert latest_failure["entity_id"] == "cardio1@mediguard.local"


def test_login_validation_errors(client):
    """Missing fields return 400 Bad Request."""
    resp = client.post("/api/auth/login", json={"email": "admin@mediguard.local"})
    assert resp.status_code == 400

    resp = client.post("/api/auth/login", data="Not-JSON", content_type="application/json")
    assert resp.status_code == 400


def test_get_me_authenticated(client, staff_token):
    """Valid token returns current user profile and permissions."""
    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {staff_token}"})
    assert resp.status_code == 200
    user_info = resp.get_json()["data"]
    assert user_info["role"] == "staff"
    assert user_info["email"] == "staff1@mediguard.local"
    assert user_info["permissions"]["is_staff"] is True
    assert user_info["permissions"]["can_write_doctor_reviews"] is False


def test_get_me_unauthorized(client):
    """Missing or invalid token returns 401."""
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401

    resp = client.get("/api/auth/me", headers={"Authorization": "Bearer invalid.fake.token"})
    assert resp.status_code == 401


def test_logout(client, cardio_token):
    """Logout endpoint invalidates session and creates LOGOUT audit entry."""
    resp = client.post("/api/auth/logout", headers={"Authorization": f"Bearer {cardio_token}"})
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "success"

    # Verify audit log recorded LOGOUT
    logs = audit_service.get_logs(action="LOGOUT")
    assert len(logs) > 0
