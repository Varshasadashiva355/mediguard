"""
MediGuard AI – Role-Based Access Control (RBAC) Test Suite
Strictly verifies that Staff tokens are rejected (403) on Cardiologist-only endpoints,
Cardiologists can access reviews, and Admin can access audit logs.
"""
import uuid
from backend.services.audit_service import audit_service


def test_staff_rejected_on_cardiologist_endpoint(client, staff_token):
    """
    CRITICAL ACCEPTANCE CRITERIA:
    A staff token is rejected with 403 Forbidden on a cardiologist-only endpoint.
    """
    resp = client.get("/api/reviews", headers={"Authorization": f"Bearer {staff_token}"})
    assert resp.status_code == 403, f"Expected 403 Forbidden for staff on /api/reviews, got {resp.status_code}"
    body = resp.get_json()
    assert body["error"] == "Forbidden"
    assert "Access denied" in body["message"]

    # Verify audit log captures RBAC_ACCESS_DENIED
    denied_logs = audit_service.get_logs(action="RBAC_ACCESS_DENIED")
    assert len(denied_logs) > 0
    assert denied_logs[0]["metadata"]["user_role"] == "staff"


def test_cardiologist_allowed_on_reviews_endpoint(client, cardio_token):
    """Cardiologist is authorized (200 OK) on reviews endpoint."""
    resp = client.get("/api/reviews", headers={"Authorization": f"Bearer {cardio_token}"})
    assert resp.status_code == 200
    assert "data" in resp.get_json()


def test_cardiologist_can_submit_doctor_review(client, cardio_token):
    """Cardiologist can submit and sign a clinical review."""
    fake_report_id = str(uuid.uuid4())
    payload = {
        "report_id": fake_report_id,
        "clinical_findings": "Sinus rhythm with ST-segment elevation in leads V2-V4. Consistent with acute anterior STEMI.",
        "diagnosis": "Acute Anterior Wall ST-Elevation Myocardial Infarction",
        "recommendation": "Activate emergency cardiac catheterization lab immediately for primary PCI.",
        "agreement_with_model": "agreed",
        "is_urgent_escalation": True
    }
    resp = client.post(
        "/api/reviews",
        headers={"Authorization": f"Bearer {cardio_token}"},
        json=payload
    )
    assert resp.status_code == 201
    res_data = resp.get_json()["data"]
    assert res_data["agreement_with_model"] == "agreed"
    assert res_data["is_urgent_escalation"] is True


def test_staff_cannot_submit_doctor_review(client, staff_token):
    """Staff cannot create or sign a clinical review."""
    payload = {
        "report_id": str(uuid.uuid4()),
        "clinical_findings": "Review attempt by staff nurse",
        "diagnosis": "Suspicion of ischemia",
        "recommendation": "Urgent consult",
        "agreement_with_model": "agreed"
    }
    resp = client.post(
        "/api/reviews",
        headers={"Authorization": f"Bearer {staff_token}"},
        json=payload
    )
    assert resp.status_code == 403


def test_admin_access_to_audit_logs(client, admin_token, cardio_token, staff_token):
    """Only Admin can access system audit logs."""
    # Staff rejected (403)
    resp_staff = client.get("/api/audit/logs", headers={"Authorization": f"Bearer {staff_token}"})
    assert resp_staff.status_code == 403

    # Cardiologist rejected (403)
    resp_cardio = client.get("/api/audit/logs", headers={"Authorization": f"Bearer {cardio_token}"})
    assert resp_cardio.status_code == 403

    # Admin authorized (200)
    resp_admin = client.get("/api/audit/logs", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp_admin.status_code == 200
    assert "data" in resp_admin.get_json()
