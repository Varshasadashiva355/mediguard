"""
MediGuard AI – Database Content Inspector CLI
Displays tables, record counts, and formatted clinical data from the MediGuard database.
Usage:
    python scripts/inspect_db.py                  # Shows summary of all tables
    python scripts/inspect_db.py --table users     # Shows all users
    python scripts/inspect_db.py --table patients  # Shows patient registry
    python scripts/inspect_db.py --table ecg       # Shows ECG reports
    python scripts/inspect_db.py --table reviews   # Shows Doctor reviews
"""
import sys
import argparse
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from backend.app import create_app
from backend.services.db_service import db_service
from backend.db.seed import seed_all


def inspect(table_name=None):
    # Initialize app context and seed if empty
    app = create_app()
    with app.app_context():
        if len(db_service.users) == 0:
            seed_all()

        print("\n" + "=" * 80)
        print("  MEDIGUARD AI – DATABASE INSPECTOR")
        print("=" * 80)
        print(f"Mode: {'OFFLINE (In-Memory Store)' if db_service.is_offline else 'LIVE (PostgreSQL/Supabase)'}")
        print("-" * 80)
        print("TABLE SUMMARY:")
        print(f"  • users:            {len(db_service.users)} records")
        print(f"  • patients:         {len(db_service.patients)} records")
        print(f"  • cardiac_history:  {sum(len(h) for h in db_service.cardiac_history.values())} records")
        print(f"  • ecg_reports:      {len(db_service.ecg_reports)} records")
        print(f"  • doctor_reviews:   {len(db_service.doctor_reviews)} records")
        print(f"  • follow_ups:       {len(db_service.follow_ups)} records")
        print(f"  • audit_logs:       {len(db_service.audit_logs)} records")
        print("=" * 80 + "\n")

        if table_name in ("users", "all"):
            print("--- [TABLE: users] ---")
            for u in db_service.users.values():
                print(f"  [{u['role'].upper():<13}] {u['email']:<30} | {u['full_name']}")
            print()

        if table_name in ("patients", "all"):
            print("--- [TABLE: patients] (Sample 10 of 30) ---")
            for p in list(db_service.patients.values())[:10]:
                code = p.get('patient_code', 'N/A')
                name = f"{p.get('first_name')} {p.get('last_name')}"
                urgency = p.get('urgency', 'routine').upper()
                room = p.get('room_bed', 'N/A')
                hist = db_service.get_patient_cardiac_history(p['id'])
                cond = hist[0]['condition_type'] if hist else 'Initial Observation'
                print(f"  {code:<14} | {urgency:<15} | {room:<14} | {name:<25} | {cond}")
            print()

        if table_name in ("ecg", "ecg_reports", "all"):
            print("--- [TABLE: ecg_reports] ---")
            for r in list(db_service.ecg_reports.values())[:10]:
                rep_id = r.get('id')
                status = r.get('status', 'pending')
                urgency = r.get('urgency', 'routine')
                fname = r.get('file_name', '')
                print(f"  Report: {rep_id} | Status: {status:<15} | Urgency: {urgency:<15} | File: {fname}")
            print()

        if table_name in ("reviews", "doctor_reviews", "all"):
            print("--- [TABLE: doctor_reviews] ---")
            for rev in list(db_service.doctor_reviews.values())[:10]:
                rep_id = rev.get('report_id')
                diag = rev.get('diagnosis', '')
                agr = rev.get('agreement_with_model', '')
                print(f"  Report: {rep_id} | Agreement: {agr:<18} | Diagnosis: {diag}")
            print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--table", choices=["users", "patients", "ecg", "reviews", "all"], default=None,
                        help="Specific table to display in detail")
    args = parser.parse_args()
    inspect(args.table)
