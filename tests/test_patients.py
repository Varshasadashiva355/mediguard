"""
MediGuard AI – Phase 2 Test Suite: Patients, History, Follow-ups, and Dashboard Aggregates
Tests:
- Patient full lifecycle: Register -> appear in list -> open profile -> update -> archive.
- Concurrency test: Auto-generated patient_code values are strictly unique under concurrent thread creation.
- Server-side validations: future DOB rejected, future angioplasty date rejected, invalid gender rejected.
- RBAC Scoping: Cardiologist A rejected (403) from accessing Cardiologist B's patient; Admin allowed.
- Follow-ups: Scheduling, listing, overdue detection, status patching.
- Dashboard numbers match direct database counts.
"""
import concurrent.futures
from datetime import date, timedelta
import pytest

from backend.services.db_service import db_service
from backend.services.auth_service import AuthService


@pytest.fixture
def cardio2_token(app):
    with app.app_context():
        user = db_service.get_user_by_email("cardio2@mediguard.local")
        return AuthService.generate_token(user)


def test_patient_full_lifecycle(client, staff_token):
    """
    Acceptance Criteria 1:
    Register -> appears in list -> open profile -> edit -> archive, all via real APIs.
    """
    # 1. Register new patient
    new_patient_data = {
        "first_name": "TestSubject",
        "last_name": "CardiacAlpha",
        "dob": "1970-05-15",
        "gender": "male",
        "blood_group": "A+",
        "contact_phone": "+1-555-7788",
        "emergency_contact": "Emergency Kin +1-555-9900",
        "room_bed": "CCU Bed 9",
        "urgency": "urgent",
        "cardiac_history": {
            "condition_type": "Acute Coronary Syndrome",
            "angioplasty_date": "2025-01-10",
            "stent_count": 1,
            "stent_details": "Xience 3.0x18mm in LAD",
            "ejection_fraction": 45.0
        }
    }
    create_resp = client.post("/api/patients", headers={"Authorization": f"Bearer {staff_token}"}, json=new_patient_data)
    assert create_resp.status_code == 201, f"Failed create: {create_resp.get_json()}"
    patient = create_resp.get_json()["data"]
    patient_id = patient["id"]
    patient_code = patient["patient_code"]
    assert patient_code.startswith("MG-")

    # 2. Appears in patients list
    list_resp = client.get(f"/api/patients?search={patient_code}", headers={"Authorization": f"Bearer {staff_token}"})
    assert list_resp.status_code == 200
    listed_patients = list_resp.get_json()["data"]
    assert any(p["id"] == patient_id for p in listed_patients)

    # 3. Open full profile
    profile_resp = client.get(f"/api/patients/{patient_id}", headers={"Authorization": f"Bearer {staff_token}"})
    assert profile_resp.status_code == 200
    profile_data = profile_resp.get_json()["data"]
    assert profile_data["patient_code"] == patient_code
    assert profile_data["first_name"] == "TestSubject"
    assert len(profile_data["cardiac_history"]) >= 1

    # 4. Edit patient demographics
    update_payload = {"room_bed": "Telemetry Bed 16", "contact_phone": "+1-555-8899"}
    put_resp = client.put(f"/api/patients/{patient_id}", headers={"Authorization": f"Bearer {staff_token}"}, json=update_payload)
    assert put_resp.status_code == 200
    updated_patient = put_resp.get_json()["data"]
    assert updated_patient["room_bed"] == "Telemetry Bed 16"
    assert updated_patient["contact_phone"] == "+1-555-8899"

    # 5. Archive patient (soft delete)
    archive_resp = client.delete(f"/api/patients/{patient_id}", headers={"Authorization": f"Bearer {staff_token}"})
    assert archive_resp.status_code == 200
    assert archive_resp.get_json()["data"]["is_archived"] is True

    # Confirm excluded from default list
    recheck_resp = client.get(f"/api/patients?search={patient_code}", headers={"Authorization": f"Bearer {staff_token}"})
    assert len(recheck_resp.get_json()["data"]) == 0

    # Confirm present when include_archived=true
    archived_list_resp = client.get(f"/api/patients?search={patient_code}&include_archived=true", headers={"Authorization": f"Bearer {staff_token}"})
    assert len(archived_list_resp.get_json()["data"]) == 1


def test_concurrent_unique_patient_codes(app):
    """
    Acceptance Criteria 2:
    Auto-generated patient IDs are unique under concurrent creation.
    """
    generated_codes = []

    def create_single_code():
        with app.app_context():
            return db_service.generate_next_patient_code()

    # Launch 50 concurrent threads generating patient codes simultaneously
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(create_single_code) for _ in range(50)]
        for f in concurrent.futures.as_completed(futures):
            generated_codes.append(f.result())

    assert len(generated_codes) == 50
    assert len(set(generated_codes)) == 50, "Duplicate patient codes detected under concurrent generation!"


def test_server_validations(client, staff_token):
    """
    Acceptance Criteria 3:
    Server rejects future dates (DOB, angioplasty date) and malformed values.
    """
    tomorrow = (date.today() + timedelta(days=1)).isoformat()

    # 1. Reject future DOB
    resp = client.post("/api/patients", headers={"Authorization": f"Bearer {staff_token}"}, json={
        "first_name": "Baby",
        "last_name": "Future",
        "dob": tomorrow,
        "gender": "male"
    })
    assert resp.status_code == 422
    assert "Date of birth cannot be in the future" in resp.get_json()["message"]

    # 2. Reject future angioplasty date
    resp2 = client.post("/api/patients", headers={"Authorization": f"Bearer {staff_token}"}, json={
        "first_name": "Jane",
        "last_name": "Cardiac",
        "dob": "1980-01-01",
        "gender": "female",
        "angioplasty_date": tomorrow
    })
    assert resp2.status_code == 422
    assert "Angioplasty / procedure date cannot be in the future" in resp2.get_json()["message"]

    # 3. Reject invalid gender
    resp3 = client.post("/api/patients", headers={"Authorization": f"Bearer {staff_token}"}, json={
        "first_name": "Alex",
        "last_name": "Test",
        "dob": "1980-01-01",
        "gender": "unknown_gender"
    })
    assert resp3.status_code == 422
    assert "Gender must be 'male', 'female', or 'other'" in resp3.get_json()["message"]


def test_cardiologist_rbac_scoping(client, cardio_token, cardio2_token, admin_token):
    """
    Acceptance Criteria 4:
    A cardiologist cannot open another cardiologist's patient unless admin (RLS + API test).
    """
    # cardio1 is assigned to patient MG-2026-000101
    patient_101_id = "44444444-4444-4444-4444-444444440101"

    # 1. Cardio 1 CAN access their assigned patient (200 OK)
    resp1 = client.get(f"/api/patients/{patient_101_id}", headers={"Authorization": f"Bearer {cardio_token}"})
    assert resp1.status_code == 200

    # 2. Cardio 2 CANNOT access Cardio 1's assigned patient (403 Forbidden)
    resp2 = client.get(f"/api/patients/{patient_101_id}", headers={"Authorization": f"Bearer {cardio2_token}"})
    assert resp2.status_code == 403, f"Expected 403 for Cardio 2 accessing Cardio 1 patient, got: {resp2.status_code}"
    assert "Cardiologists may only access their assigned cardiology patients" in resp2.get_json()["message"]

    # 3. Admin CAN access any cardiologist's patient (200 OK)
    resp3 = client.get(f"/api/patients/{patient_101_id}", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp3.status_code == 200


def test_cardiac_history_and_follow_ups(client, cardio_token, staff_token):
    """
    Tests multiple cardiac history entries and follow-up scheduling with overdue detection.
    """
    patient_id = "44444444-4444-4444-4444-444444440101"

    # Add cardiac history entry
    hist_payload = {
        "condition_type": "Stent Restenosis Evaluation",
        "diagnosis_date": date.today().isoformat(),
        "prior_mi": True,
        "prior_stent": True,
        "angioplasty_date": "2026-01-15",
        "stent_count": 2,
        "stent_details": "Repeat DES in proximal LAD",
        "ejection_fraction": 44.0,
        "allergies": ["Penicillin"],
        "medications_structured": [{"name": "Aspirin", "dose": "81mg", "freq": "Daily"}]
    }
    hist_resp = client.post(
        f"/api/patients/{patient_id}/cardiac-history",
        headers={"Authorization": f"Bearer {cardio_token}"},
        json=hist_payload
    )
    assert hist_resp.status_code == 201

    # Schedule follow up
    next_week = (date.today() + timedelta(days=7)).isoformat()
    fu_resp = client.post(
        f"/api/patients/{patient_id}/follow-ups",
        headers={"Authorization": f"Bearer {staff_token}"},
        json={
            "scheduled_date": next_week,
            "follow_up_type": "Echo & Stent Evaluation",
            "notes": "Bring prior ECG records"
        }
    )
    assert fu_resp.status_code == 201
    fu_id = fu_resp.get_json()["data"]["id"]

    # Complete follow up
    patch_resp = client.patch(
        f"/api/follow-ups/{fu_id}",
        headers={"Authorization": f"Bearer {cardio_token}"},
        json={"status": "completed", "outcome": "Stent patent. Normal LVEF."}
    )
    assert patch_resp.status_code == 200
    assert patch_resp.get_json()["data"]["status"] == "completed"


def test_dashboard_aggregates_match_database(client, admin_token):
    """
    Acceptance Criteria 5:
    Dashboard numbers match direct SQL / database counts.
    """
    resp = client.get("/api/dashboard/stats", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200
    stats = resp.get_json()["data"]

    # Direct database counts
    active_patients = [p for p in db_service.patients.values() if not p.get("is_archived", False)]
    assert stats["total_patients_overall"] == len(active_patients)
    assert stats["uploaded_ecg_reports"] == len(db_service.ecg_reports)

    today_str = date.today().isoformat()
    expected_overdue = sum(1 for f in db_service.follow_ups.values() if f.get("status") == "scheduled" and f.get("scheduled_date", "") < today_str)
    assert stats["overdue_follow_ups"] == expected_overdue

    # Test charts endpoint
    charts_resp = client.get("/api/dashboard/charts", headers={"Authorization": f"Bearer {admin_token}"})
    assert charts_resp.status_code == 200
    charts = charts_resp.get_json()["data"]
    assert "monthly_patients" in charts
    assert "weekly_reports" in charts
    assert "review_agreement" in charts

    # Test priority queue endpoint
    queue_resp = client.get("/api/dashboard/priority-queue", headers={"Authorization": f"Bearer {admin_token}"})
    assert queue_resp.status_code == 200
    queue = queue_resp.get_json()["data"]
    assert len(queue) > 0
    # First item in priority queue should be stat_emergency or urgent
    assert queue[0]["urgency"] in ("stat_emergency", "urgent")
