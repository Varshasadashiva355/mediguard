from pathlib import Path
import sys

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from backend.app import create_app
from backend.services.db_service import db_service
from backend.services.auth_service import AuthService
from backend.db.seed import seed_all
import io

app = create_app()
with app.app_context():
    if len(db_service.patients) == 0:
        seed_all()
    client = app.test_client()

    # Get staff token
    staff = db_service.get_user_by_email("staff1@mediguard.local")
    token = AuthService.generate_token(staff)

    # Test upload with patient_code 'MG-2026-000120'
    sample_csv = (BASE_DIR / "samples" / "ecg" / "sample_12lead_acute_stemi.csv").read_bytes()
    resp = client.post(
        "/api/ecg/upload",
        headers={"Authorization": f"Bearer {token}"},
        data={
            "patient_id": "MG-2026-000120",
            "report_date": "2026-11-13",
            "notes": "Testing upload with patient code MG-2026-000120",
            "file": (io.BytesIO(sample_csv), "sample_12lead_acute_stemi.csv")
        },
        content_type="multipart/form-data"
    )
    print("Upload with patient_code MG-2026-000120:", resp.status_code, resp.get_json())
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}"
    print("SUCCESS: Patient code MG-2026-000120 resolved and ingested cleanly!")
