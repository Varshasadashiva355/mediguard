"""
MediGuard AI – Phase 4 ECG Upload, Storage, Worker & Comparison Test Suite
Validates:
- Storage service paths (<patient_id>/<report_id>/original.<ext>), SHA-256, signed URLs, and expiration
- File validation (magic bytes, size, empty files, future dates, patient existence)
- Separate pipelines: Digital CSV routes to worker; JPG/PDF never receive model scores
- Background job processing, retry logic, and dead-worker resilience
- Historical comparison and explicit non-comparability rationales
"""
import io
import time
from datetime import date, timedelta
import pytest

from tests.fixtures_ecg import (
    generate_synthetic_ecg_csv_bytes,
    generate_synthetic_image_bytes,
    generate_synthetic_pdf_bytes
)
from backend.services.db_service import db_service
from backend.services.storage_service import storage_service
from backend.services.comparison_service import comparison_service
from backend.worker.worker import BackgroundWorker, process_single_job


@pytest.fixture
def test_patient(app):
    with app.app_context():
        patients = list(db_service.patients.values())
        return patients[0]


def test_storage_service_upload_and_signed_url():
    """Verify private bucket path, SHA-256 calculation, and signed URL token expiration."""
    pid = "test-patient-001"
    rid = "test-report-001"
    data = b"MOCK_ECG_RAW_DATA_12LEAD"
    meta = storage_service.upload_ecg_file(pid, rid, "record.dat", data)

    assert meta["storage_path"] == f"{pid}/{rid}/original.dat"
    assert "sha256" in meta
    assert meta["size_bytes"] == len(data)

    # Valid signed URL
    signed_url = storage_service.generate_signed_url(pid, rid, expires_in_minutes=10)
    assert f"/api/ecg/{rid}/file?token=" in signed_url

    # Parse token and expires
    parts = signed_url.split("?")[-1].split("&")
    token = [p.split("=")[1] for p in parts if p.startswith("token=")][0]
    expires = [p.split("=")[1] for p in parts if p.startswith("expires=")][0]

    assert storage_service.verify_signed_token(rid, token, int(expires)) is True

    # Expired token must be rejected
    past_timestamp = int(time.time()) - 100
    assert storage_service.verify_signed_token(rid, token, past_timestamp) is False


def test_upload_digital_csv_pipeline_enqueues_job(client, staff_token, test_patient):
    """Digital 12-lead CSV routes to digital pipeline and enqueues a background job."""
    pid = test_patient["id"]
    csv_bytes = generate_synthetic_ecg_csv_bytes(samples=500)

    data = {
        "patient_id": pid,
        "report_date": "2026-11-10",
        "notes": "Post-angioplasty baseline digital CSV",
        "file": (io.BytesIO(csv_bytes), "patient_lead12.csv")
    }

    resp = client.post(
        "/api/ecg/upload",
        headers={"Authorization": f"Bearer {staff_token}"},
        data=data,
        content_type="multipart/form-data"
    )
    assert resp.status_code == 201
    res = resp.get_json()["data"]
    assert res["pipeline_type"] == "digital_12lead"
    assert res["status"] == "queued"
    assert res["job_id"] is not None

    # Verify background job exists in queue
    job = db_service.get_job(res["job_id"])
    assert job is not None
    assert job["status"] == "pending"


def test_upload_image_pipeline_marks_non_ml_compatible(client, staff_token, test_patient):
    """ECG Image (JPG/PNG) is stored for physician review and never receives ML scores."""
    pid = test_patient["id"]
    jpg_bytes = generate_synthetic_image_bytes(format_type="JPEG")

    data = {
        "patient_id": pid,
        "report_date": "2026-11-11",
        "notes": "Scanned rhythm strip image",
        "file": (io.BytesIO(jpg_bytes), "rhythm_strip.jpg")
    }

    resp = client.post(
        "/api/ecg/upload",
        headers={"Authorization": f"Bearer {staff_token}"},
        data=data,
        content_type="multipart/form-data"
    )
    assert resp.status_code == 201
    res = resp.get_json()["data"]
    assert res["pipeline_type"] == "image"
    assert res["status"] == "not_compatible_ml"
    assert res["job_id"] is None

    # Verify analysis returns not_applicable and NO model scores exist
    rid = res["report_id"]
    ana_resp = client.get(f"/api/ecg/{rid}/analysis", headers={"Authorization": f"Bearer {staff_token}"})
    assert ana_resp.status_code == 200
    ana_body = ana_resp.get_json()
    assert ana_body["status"] == "not_applicable"
    assert "scores" not in ana_body.get("data", {})


def test_upload_pdf_pipeline_marks_non_ml_compatible(client, staff_token, test_patient):
    """Clinical PDF is stored for physician review and never receives ML scores."""
    pid = test_patient["id"]
    pdf_bytes = generate_synthetic_pdf_bytes()

    data = {
        "patient_id": pid,
        "report_date": "2026-11-12",
        "notes": "Archived hospital telemetry PDF report",
        "file": (io.BytesIO(pdf_bytes), "cardiac_report.pdf")
    }

    resp = client.post(
        "/api/ecg/upload",
        headers={"Authorization": f"Bearer {staff_token}"},
        data=data,
        content_type="multipart/form-data"
    )
    assert resp.status_code == 201
    res = resp.get_json()["data"]
    assert res["pipeline_type"] == "pdf"
    assert res["status"] == "not_compatible_ml"


def test_upload_spoofed_magic_bytes_rejected(client, staff_token, test_patient):
    """Spoofed file (JPEG extension with PNG bytes or text) is rejected with 400."""
    pid = test_patient["id"]
    fake_jpg = b"THIS_IS_NOT_A_JPEG_HEADER"

    data = {
        "patient_id": pid,
        "report_date": "2026-11-12",
        "file": (io.BytesIO(fake_jpg), "spoofed.jpg")
    }

    resp = client.post(
        "/api/ecg/upload",
        headers={"Authorization": f"Bearer {staff_token}"},
        data=data,
        content_type="multipart/form-data"
    )
    assert resp.status_code == 400
    assert "magic bytes" in resp.get_json()["message"]


def test_upload_empty_file_rejected(client, staff_token, test_patient):
    """Empty 0-byte file is rejected with 400."""
    pid = test_patient["id"]
    data = {
        "patient_id": pid,
        "report_date": "2026-11-12",
        "file": (io.BytesIO(b""), "empty.csv")
    }
    resp = client.post(
        "/api/ecg/upload",
        headers={"Authorization": f"Bearer {staff_token}"},
        data=data,
        content_type="multipart/form-data"
    )
    assert resp.status_code == 400
    assert "empty" in resp.get_json()["message"]


def test_upload_future_report_date_rejected(client, staff_token, test_patient):
    """Future report date is rejected with 400."""
    pid = test_patient["id"]
    future_date = (date.today() + timedelta(days=2)).isoformat()
    csv_bytes = generate_synthetic_ecg_csv_bytes(samples=500)

    data = {
        "patient_id": pid,
        "report_date": future_date,
        "file": (io.BytesIO(csv_bytes), "future_ecg.csv")
    }
    resp = client.post(
        "/api/ecg/upload",
        headers={"Authorization": f"Bearer {staff_token}"},
        data=data,
        content_type="multipart/form-data"
    )
    assert resp.status_code == 400
    assert "future" in resp.get_json()["message"]


def test_duplicate_upload_hash_warning(client, staff_token, test_patient):
    """Uploading the exact same file twice for a patient detects duplicate by hash."""
    pid = test_patient["id"]
    csv_bytes = generate_synthetic_ecg_csv_bytes(samples=500)

    data = {
        "patient_id": pid,
        "report_date": "2026-11-01",
        "file": (io.BytesIO(csv_bytes), "baseline.csv")
    }
    resp1 = client.post("/api/ecg/upload", headers={"Authorization": f"Bearer {staff_token}"}, data=data, content_type="multipart/form-data")
    assert resp1.status_code == 201

    # Upload again with same bytes
    data["file"] = (io.BytesIO(csv_bytes), "baseline_copy.csv")
    resp2 = client.post("/api/ecg/upload", headers={"Authorization": f"Bearer {staff_token}"}, data=data, content_type="multipart/form-data")
    assert resp2.status_code == 201
    assert resp2.get_json()["data"]["duplicate_warning"] is True


def test_worker_processes_job_and_updates_analysis(client, staff_token, test_patient):
    """Background worker claims and processes inference job, updating report to analyzed."""
    pid = test_patient["id"]
    csv_bytes = generate_synthetic_ecg_csv_bytes(samples=1000)

    upload_resp = client.post(
        "/api/ecg/upload",
        headers={"Authorization": f"Bearer {staff_token}"},
        data={"patient_id": pid, "report_date": "2026-11-13", "file": (io.BytesIO(csv_bytes), "test_worker.csv")},
        content_type="multipart/form-data"
    )
    assert upload_resp.status_code == 201
    rep_id = upload_resp.get_json()["data"]["report_id"]

    # Run worker for one iteration
    worker = BackgroundWorker()
    processed_count = worker.run_once()
    assert processed_count >= 1

    # Verify report status is now analyzed (or flagged_urgent)
    status_resp = client.get(f"/api/ecg/{rep_id}/status", headers={"Authorization": f"Bearer {staff_token}"})
    assert status_resp.status_code == 200
    status_data = status_resp.get_json()["data"]
    assert status_data["report_status"] in ("analyzed", "flagged_urgent")
    assert status_data["has_analysis"] is True

    # Verify analysis scores
    ana_resp = client.get(f"/api/ecg/{rep_id}/analysis", headers={"Authorization": f"Bearer {staff_token}"})
    assert ana_resp.status_code == 200
    scores = ana_resp.get_json()["data"]["scores"]
    for k in ["NORM", "MI", "STTC", "CD", "HYP"]:
        assert k in scores
        assert 0.0 <= scores[k] <= 1.0


def test_worker_killed_mid_job_resilience(app):
    """If a worker is killed mid-job, the timeout recovery re-claims and completes the job."""
    with app.app_context():
        # Enqueue dummy job
        job = db_service.enqueue_job("test_recovery", {"msg": "mid_job_test"}, max_attempts=3)
        job_id = job["id"]

        # Simulate job claimed by worker 1
        claimed_1 = db_service.claim_next_job("test_recovery")
        assert claimed_1["id"] == job_id
        assert claimed_1["status"] == "processing"
        assert claimed_1["attempts"] == 1

        # Simulate timeout (e.g. 0 second timeout for test)
        time.sleep(0.01)
        claimed_2 = db_service.claim_next_job("test_recovery", timeout_seconds=0)
        assert claimed_2 is not None
        assert claimed_2["id"] == job_id
        assert claimed_2["attempts"] == 2  # Incremented attempt on recovery!


def test_ecg_comparison_refuses_incompatible_pair(client, staff_token, test_patient):
    """Comparison service refuses incompatible pairs (e.g. digital vs image) with explicit reason."""
    pid = test_patient["id"]

    # Upload digital CSV
    csv_bytes = generate_synthetic_ecg_csv_bytes(samples=500)
    r_csv = client.post(
        "/api/ecg/upload",
        headers={"Authorization": f"Bearer {staff_token}"},
        data={"patient_id": pid, "file": (io.BytesIO(csv_bytes), "comp_sig.csv")},
        content_type="multipart/form-data"
    ).get_json()["data"]["report_id"]

    # Upload image
    jpg_bytes = generate_synthetic_image_bytes()
    r_jpg = client.post(
        "/api/ecg/upload",
        headers={"Authorization": f"Bearer {staff_token}"},
        data={"patient_id": pid, "file": (io.BytesIO(jpg_bytes), "comp_img.jpg")},
        content_type="multipart/form-data"
    ).get_json()["data"]["report_id"]

    # Compare them
    comp_resp = client.post(
        "/api/ecg/compare",
        headers={"Authorization": f"Bearer {staff_token}"},
        json={"report_id_a": r_csv, "report_id_b": r_jpg}
    )
    assert comp_resp.status_code == 200
    data = comp_resp.get_json()["data"]
    assert data["is_comparable"] is False
    assert len(data["reasons_not_comparable"]) > 0
    assert "Cross-modal algorithmic comparison" in data["reasons_not_comparable"][0]
