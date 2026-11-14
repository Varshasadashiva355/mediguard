"""
MediGuard AI – Database Inspection & Management CLI
Usage:
    python -m backend.db.cli                # Show database summary & record counts
    python -m backend.db.cli patients       # List all patients and cardiac histories
    python -m backend.db.cli users          # List all users & roles
    python -m backend.db.cli reports        # List ECG reports & statuses
    python -m backend.db.cli seed           # Re-run synthetic database seeder
"""
import sys
from backend.services.db_service import db_service
from backend.db.seed import seed_all


def show_summary():
    print("=" * 65)
    print("  MediGuard AI - Cardiology Database Inspection")
    print("=" * 65)
    print(f"  Storage Mode:        {'PostgreSQL / Supabase' if not db_service.is_offline else 'In-Memory Demo Repository'}")
    print(f"  Total Patients:      {len(db_service.patients)}")
    print(f"  Total ECG Reports:   {len(db_service.ecg_reports)}")
    print(f"  Total Doctor Reviews:{len(db_service.doctor_reviews)}")
    print(f"  Total Follow-ups:    {len(db_service.follow_ups)}")
    print(f"  Total Users/Staff:   {len(db_service.users)}")
    print(f"  Total Audit Logs:    {len(db_service.audit_logs)}")
    print(f"  Background Jobs:     {len(db_service.jobs)}")
    print("=" * 65)


def show_patients(limit=30):
    show_summary()
    print("\nPATIENT REGISTRY & CLINICAL PROFILES:")
    print("-" * 90)
    print(f"{'Code':<10} {'Name':<22} {'Room':<14} {'Urgency':<15} {'Stents':<8} {'EF %':<6} {'Condition'}")
    print("-" * 90)
    for p_id, p in list(db_service.patients.items())[:limit]:
        name = f"{p.get('first_name', '')} {p.get('last_name', '')}"
        histories = db_service.get_patient_cardiac_history(p_id)
        latest_hist = histories[0] if histories else {}
        cond = latest_hist.get("condition_type", "Cardiology Monitoring")
        stents = latest_hist.get("stent_count", 0)
        ef = f"{latest_hist.get('ejection_fraction', '--')}%" if latest_hist.get('ejection_fraction') else "--"
        print(f"{p.get('patient_code', ''):<10} {name:<22} {p.get('room_bed', 'CCU'):<14} {p.get('urgency', 'routine'):<15} {stents:<8} {ef:<6} {cond}")
    print("-" * 90)


def show_users():
    show_summary()
    print("\nREGISTERED CLINICAL USERS & ACCOUNTS:")
    print("-" * 75)
    print(f"{'Full Name':<32} {'Role':<14} {'Email'}")
    print("-" * 75)
    for u in db_service.users.values():
        print(f"{u.get('full_name', ''):<32} {u.get('role', ''):<14} {u.get('email', '')}")
    print("-" * 75)


def show_reports():
    show_summary()
    print("\nECG WAVEFORM & REPORT INGESTIONS:")
    print("-" * 80)
    print(f"{'Report ID':<14} {'Patient Code':<14} {'Status':<16} {'Pipeline':<12} {'Urgency'}")
    print("-" * 80)
    for r in db_service.ecg_reports.values():
        p = db_service.get_patient_by_id(r.get("patient_id"))
        p_code = p.get("patient_code", "MG-N/A") if p else "N/A"
        pipeline = r.get("metadata", {}).get("pipeline", "digital")
        print(f"{r.get('id', ''):<14} {p_code:<14} {r.get('status', 'uploaded'):<16} {pipeline:<12} {r.get('urgency', 'routine')}")
    print("-" * 80)


def main():
    if len(db_service.users) == 0 or len(db_service.patients) == 0:
        seed_all()

    arg = sys.argv[1].lower() if len(sys.argv) > 1 else "summary"
    if arg in ("summary", "status"):
        show_summary()
        print("\nTip: Run 'python -m backend.db.cli patients' to inspect patient records.")
    elif arg in ("patients", "patient"):
        show_patients()
    elif arg in ("users", "user"):
        show_users()
    elif arg in ("reports", "report"):
        show_reports()
    elif arg in ("seed", "reset"):
        db_service.reset_all_data()
        seed_all()
        print("Database re-seeded successfully.")
        show_summary()
    else:
        print(f"Unknown command: '{arg}'. Options: summary, patients, users, reports, seed")


if __name__ == "__main__":
    main()
