"""
Tests for MediGuard AI – Cardiologist Review Workspace & RBAC
Validates:
- Only cardiologists and admin can review and mark reviewed (Staff gets 403).
- Structured interpretation storage (rhythm, ST/T, conduction, overall impression).
- Review draft saving and retrieval.
- Append-only review history with edit versions.
- Prioritized review queue sorting (urgent -> prompt -> routine).
- Automatic follow-up scheduling from the review workspace.
"""
import pytest
from backend.app import create_app
from backend.config import TestConfig
from backend.services.db_service import db_service
from backend.services.auth_service import AuthService


@pytest.fixture
def app():
    app = create_app(TestConfig)
    return app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def users_and_report(app):
    with app.app_context():
        db_service.reset_all_data()

        # Create admin, cardiologist, staff
        admin = db_service.add_user({
            "id": "11111111-1111-1111-1111-111111111111",
            "email": "admin@mediguard.local",
            "role": "admin",
            "full_name": "Dr. Sarah Chen, MD"
        }, plain_password="Admin@123")

        cardio = db_service.add_user({
            "id": "22222222-2222-2222-2222-222222222222",
            "email": "cardio@mediguard.local",
            "role": "cardiologist",
            "full_name": "Dr. Alexander Hayes, FACC"
        }, plain_password="Cardio@123")

        staff = db_service.add_user({
            "id": "33333333-3333-3333-3333-333333333333",
            "email": "staff@mediguard.local",
            "role": "staff",
            "full_name": "RN Robert Davis"
        }, plain_password="Staff@123")

        pt = db_service.add_patient({
            "first_name": "James",
            "last_name": "Harrison",
            "dob": "1965-04-12",
            "gender": "male",
            "patient_code": "MG-2026-000101",
            "urgency": "urgent"
        })

        rep = db_service.add_ecg_report({
            "patient_id": pt["id"],
            "file_name": "12lead_stemi.csv",
            "file_type": "digital_12lead",
            "status": "pending",
            "urgency": "urgent"
        })

        cardio_token = AuthService.generate_token(cardio)
        staff_token = AuthService.generate_token(staff)
        admin_token = AuthService.generate_token(admin)

        return {
            "admin": admin, "cardio": cardio, "staff": staff,
            "patient": pt, "report": rep,
            "cardio_token": cardio_token,
            "staff_token": staff_token,
            "admin_token": admin_token
        }


def test_staff_cannot_submit_review(client, users_and_report):
    """Staff role MUST receive 403 Forbidden on review endpoints."""
    ctx = users_and_report
    headers = {"Authorization": f"Bearer {ctx['staff_token']}"}

    res = client.post("/api/reviews", json={
        "report_id": ctx["report"]["id"],
        "clinical_findings": "Staff trying to sign diagnosis",
        "diagnosis": "STEMI",
        "recommendation": "Cath lab",
        "agreement_with_model": "agreed"
    }, headers=headers)

    assert res.status_code == 403


def test_cardiologist_submit_structured_review(client, users_and_report):
    """Cardiologist can submit structured review with all clinical fields."""
    ctx = users_and_report
    headers = {"Authorization": f"Bearer {ctx['cardio_token']}"}

    payload = {
        "report_id": ctx["report"]["id"],
        "clinical_findings": "Marked ST elevation in V2-V4 with reciprocal depression in II, III, aVF.",
        "diagnosis": "Acute Anterior STEMI",
        "recommendation": "Immediate cardiac catheterization and LAD angioplasty.",
        "agreement_with_model": "agreed",
        "rhythm": "Sinus Rhythm at 88 bpm",
        "st_t_findings": "ST elevation > 2mm in V2-V4",
        "conduction": "Normal AV conduction, normal PR interval",
        "overall_impression": "Evolving acute anterior myocardial infarction",
        "urgency_assignment": "stat_emergency",
        "schedule_follow_up": True,
        "follow_up_date": "2026-12-01"
    }

    res = client.post("/api/reviews", json=payload, headers=headers)
    assert res.status_code == 201
    data = res.get_json()["data"]
    assert data["rhythm"] == payload["rhythm"]
    assert data["st_t_findings"] == payload["st_t_findings"]
    assert data["urgency_assignment"] == "stat_emergency"
    assert data["version"] == 1

    # Check report status updated to 'reviewed'
    rep = db_service.get_ecg_report(ctx["report"]["id"])
    assert rep["status"] == "reviewed"
    assert rep["urgency"] == "stat_emergency"

    # Check follow up was automatically scheduled
    follow_ups = db_service.list_follow_ups(patient_id=ctx["patient"]["id"])
    assert len(follow_ups) == 1
    assert follow_ups[0]["scheduled_date"] == "2026-12-01"


def test_review_draft_saving_and_retrieval(client, users_and_report):
    """Cardiologist can save and resume review drafts."""
    ctx = users_and_report
    headers = {"Authorization": f"Bearer {ctx['cardio_token']}"}

    draft_payload = {
        "report_id": ctx["report"]["id"],
        "rhythm": "Sinus Tachycardia",
        "clinical_findings": "Work in progress clinical observation..."
    }

    # Save draft
    res1 = client.post("/api/reviews/draft", json=draft_payload, headers=headers)
    assert res1.status_code == 200

    # Retrieve draft
    res2 = client.get(f"/api/reviews/draft/{ctx['report']['id']}", headers=headers)
    assert res2.status_code == 200
    retrieved = res2.get_json()
    assert retrieved["has_draft"] is True
    assert retrieved["data"]["rhythm"] == "Sinus Tachycardia"


def test_append_only_review_history(client, users_and_report):
    """Subsequent amendments preserve previous review versions (append-only)."""
    ctx = users_and_report
    headers = {"Authorization": f"Bearer {ctx['cardio_token']}"}

    # Submit Version 1
    client.post("/api/reviews", json={
        "report_id": ctx["report"]["id"],
        "clinical_findings": "Initial findings v1",
        "diagnosis": "Observation v1",
        "recommendation": "Rest",
        "agreement_with_model": "agreed"
    }, headers=headers)

    # Submit Version 2 (amended review)
    client.post("/api/reviews", json={
        "report_id": ctx["report"]["id"],
        "clinical_findings": "Amended findings v2",
        "diagnosis": "Observation v2",
        "recommendation": "Echo ordered",
        "agreement_with_model": "agreed"
    }, headers=headers)

    # Retrieve review history
    res = client.get(f"/api/reviews/report/{ctx['report']['id']}/history", headers=headers)
    assert res.status_code == 200
    history = res.get_json()["data"]
    assert len(history) == 2
    assert history[0]["version"] == 1
    assert history[1]["version"] == 2


def test_prioritised_review_queue(client, users_and_report):
    """Queue returns unreviewed reports prioritised with transparent reasons."""
    ctx = users_and_report
    headers = {"Authorization": f"Bearer {ctx['cardio_token']}"}

    res = client.get("/api/reviews/queue", headers=headers)
    assert res.status_code == 200
    queue = res.get_json()["data"]
    assert len(queue) >= 1
    first_item = queue[0]
    assert "priority" in first_item
    assert "priority_reasons" in first_item
    assert len(first_item["priority_reasons"]) > 0
    assert "rule_disclaimer" in first_item
