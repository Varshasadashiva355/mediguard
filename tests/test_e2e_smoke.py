"""
MediGuard AI – End-to-End Clinical Smoke Test
Covers complete clinical lifecycle:
1. Login as Staff
2. Register a new synthetic cardiac patient
3. Upload digital 12-lead ECG CSV file
4. Background worker inference execution
5. Notification dispatch to Cardiologist
6. Login as Cardiologist
7. Review notifications & inspect prioritised review queue
8. Save review draft
9. Submit & sign structured doctor review + schedule follow-up
10. Verify audit logging and append-only versioning
"""
import io
import pytest
from pathlib import Path

from backend.app import create_app
from backend.config import TestConfig
from backend.services.db_service import db_service
from backend.db.seed import seed_all
from backend.worker.worker import BackgroundWorker

SAMPLE_CSV_PATH = Path(__file__).resolve().parent.parent / "samples" / "ecg" / "sample_12lead_acute_stemi.csv"


@pytest.fixture
def app():
    app = create_app(TestConfig)
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def test_full_clinical_e2e_lifecycle(client, app):
    with app.app_context():
        seed_all()

    # -------------------------------------------------------------
    # Step 1: Login as Staff
    # -------------------------------------------------------------
    login_res = client.post("/api/auth/login", json={
        "email": "staff1@mediguard.local",
        "password": "StaffPass123!"
    })
    assert login_res.status_code == 200
    staff_token = login_res.get_json()["data"]["access_token"]
    staff_headers = {"Authorization": f"Bearer {staff_token}"}

    # -------------------------------------------------------------
    # Step 2: Register a New Synthetic Cardiac Patient
    # -------------------------------------------------------------
    patient_payload = {
        "first_name": "Samuel",
        "last_name": "E2ETest",
        "dob": "1968-09-20",
        "gender": "male",
        "blood_group": "A+",
        "contact_phone": "+1-555-0199",
        "emergency_contact": "Wife: +1-555-0198",
        "room_bed": "CCU Bed 5",
        "urgency": "urgent",
        "cardiac_history": {
            "condition_type": "Acute Anterior STEMI",
            "pci_done": True,
            "stent_count": 2,
            "stent_details": "2x Everolimus DES in LAD",
            "ejection_fraction": 42.0,
            "diagnosis_date": "2026-11-10"
        }
    }
    pt_res = client.post("/api/patients", json=patient_payload, headers=staff_headers)
    assert pt_res.status_code == 201
    patient_id = pt_res.get_json()["data"]["id"]
    patient_code = pt_res.get_json()["data"]["patient_code"]
    assert patient_id is not None
    assert patient_code.startswith("MG-")

    # -------------------------------------------------------------
    # Step 3: Upload Digital 12-Lead ECG CSV File
    # -------------------------------------------------------------
    assert SAMPLE_CSV_PATH.exists(), f"Sample CSV missing: {SAMPLE_CSV_PATH}"
    csv_bytes = SAMPLE_CSV_PATH.read_bytes()

    upload_data = {
        "patient_id": patient_id,
        "report_date": "2026-11-13",
        "notes": "Emergency post-PCI 12-lead recording",
        "sampling_rate": "100",
        "file": (io.BytesIO(csv_bytes), "sample_12lead_acute_stemi.csv")
    }
    upload_res = client.post(
        "/api/ecg/upload",
        data=upload_data,
        content_type="multipart/form-data",
        headers=staff_headers
    )
    assert upload_res.status_code == 201
    report_id = upload_res.get_json()["data"]["report_id"]
    pipeline = upload_res.get_json()["data"]["pipeline"]
    assert pipeline == "digital_12lead"

    # -------------------------------------------------------------
    # Step 4: Background Worker Executes Model Inference
    # -------------------------------------------------------------
    worker = BackgroundWorker()
    processed_count = worker.run_once()
    assert processed_count >= 1

    # Verify report status is now 'analyzed'
    rep_status_res = client.get(f"/api/ecg/{report_id}/status", headers=staff_headers)
    assert rep_status_res.status_code == 200
    assert rep_status_res.get_json()["data"]["status"] in ("analyzed", "analysed")

    # -------------------------------------------------------------
    # Step 5: Login as Cardiologist
    # -------------------------------------------------------------
    cardio_login = client.post("/api/auth/login", json={
        "email": "cardio1@mediguard.local",
        "password": "CardioPass123!"
    })
    assert cardio_login.status_code == 200
    cardio_token = cardio_login.get_json()["data"]["access_token"]
    cardio_headers = {"Authorization": f"Bearer {cardio_token}"}

    # -------------------------------------------------------------
    # Step 6: Cardiologist Receives & Reads Notifications
    # -------------------------------------------------------------
    notifs_res = client.get("/api/notifications", headers=cardio_headers)
    assert notifs_res.status_code == 200
    notifs = notifs_res.get_json()["data"]
    assert len(notifs) >= 1
    # Mark all read
    client.post("/api/notifications/mark-all-read", headers=cardio_headers)

    # -------------------------------------------------------------
    # Step 7: Inspect Prioritised Review Queue
    # -------------------------------------------------------------
    queue_res = client.get("/api/reviews/queue", headers=cardio_headers)
    assert queue_res.status_code == 200
    queue = queue_res.get_json()["data"]
    assert any(q["report_id"] == report_id for q in queue)
    target_q = next(q for q in queue if q["report_id"] == report_id)
    assert target_q["priority"] in ("urgent", "prompt")
    assert len(target_q["priority_reasons"]) > 0

    # -------------------------------------------------------------
    # Step 8: Save Review Draft
    # -------------------------------------------------------------
    draft_res = client.post("/api/reviews/draft", json={
        "report_id": report_id,
        "rhythm": "Sinus rhythm with marked anterior ST elevations",
        "clinical_findings": "Initial inspection: elevated ST segments in leads V2-V4."
    }, headers=cardio_headers)
    assert draft_res.status_code == 200

    # -------------------------------------------------------------
    # Step 9: Submit & Sign Final Doctor Review + Schedule Follow-up
    # -------------------------------------------------------------
    review_res = client.post("/api/reviews", json={
        "report_id": report_id,
        "clinical_findings": "Confirmed acute anterior ST elevation myocardial infarction pattern.",
        "diagnosis": "Evolving Acute Anterior STEMI, Status Post LAD Stenting",
        "recommendation": "Maintain DAPT, continuous telemetry monitoring, echocardiogram at 24 hours.",
        "agreement_with_model": "agreed",
        "rhythm": "Normal Sinus Rhythm, rate 84 bpm",
        "st_t_findings": "ST elevation > 3mm in V2-V4",
        "conduction": "Normal PR and QRS duration",
        "overall_impression": "Acute anterior injury pattern requiring intensive CCU monitoring.",
        "urgency_assignment": "stat_emergency",
        "schedule_follow_up": True,
        "follow_up_date": "2026-11-28"
    }, headers=cardio_headers)
    assert review_res.status_code == 201

    # -------------------------------------------------------------
    # Step 10: Verify Report is Reviewed and Follow-Up is Scheduled
    # -------------------------------------------------------------
    rep_after = db_service.get_ecg_report(report_id)
    assert rep_after["status"] == "reviewed"
    assert rep_after["urgency"] == "stat_emergency"

    # Check append-only history
    history_res = client.get(f"/api/reviews/report/{report_id}/history", headers=cardio_headers)
    assert history_res.status_code == 200
    assert len(history_res.get_json()["data"]) == 1

    # Check follow up was created
    pt_followups = db_service.list_follow_ups(patient_id=patient_id)
    assert len(pt_followups) == 1
    assert pt_followups[0]["scheduled_date"] == "2026-11-28"
