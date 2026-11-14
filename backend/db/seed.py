"""
MediGuard AI – Synthetic Data Seeder (Phase 2 Enhanced)
Populates synthetic clinical staff, 30 diverse synthetic cardiac patients,
stent histories, structured medications, ECG reports, and follow-ups.
STRICT RULE 5 COMPLIANCE: All generated records are strictly synthetic demo data.
Supports '--reset' command-line flag.
"""
import sys
import uuid
import logging
import secrets
import string
from pathlib import Path
from datetime import datetime, timezone, date, timedelta

from backend.services.db_service import db_service
from backend.models.enums import UserRole, ReportUrgency, ReportStatus, AgreementWithModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mediguard.seed")

CARDIO_1_ID = "33333333-3333-3333-3333-333333333331" # Dr. Alexander Hayes (Interventional)
CARDIO_2_ID = "33333333-3333-3333-3333-333333333332" # Dr. Priya Patel (Electrophysiology)

SYNTHETIC_USERS = [
    {
        "id": "11111111-1111-1111-1111-111111111111",
        "email": "admin@mediguard.local",
        "password": "AdminPass123!",
        "full_name": "Dr. Sarah Chen, MD (SYNTHETIC ADMIN)",
        "role": UserRole.ADMIN.value,
        "department": "Cardiology & Clinical Informatics",
        "phone": "+1-555-0100"
    },
    {
        "id": "22222222-2222-2222-2222-222222222221",
        "email": "staff1@mediguard.local",
        "password": "StaffPass123!",
        "full_name": "RN Robert Davis (SYNTHETIC STAFF)",
        "role": UserRole.STAFF.value,
        "department": "Cardiac Care Unit (CCU)",
        "phone": "+1-555-0201"
    },
    {
        "id": "22222222-2222-2222-2222-222222222222",
        "email": "staff2@mediguard.local",
        "password": "StaffPass123!",
        "full_name": "RN Maria Santos (SYNTHETIC STAFF)",
        "role": UserRole.STAFF.value,
        "department": "Telemetry Monitoring Ward",
        "phone": "+1-555-0202"
    },
    {
        "id": CARDIO_1_ID,
        "email": "cardio1@mediguard.local",
        "password": "CardioPass123!",
        "full_name": "Dr. Alexander Hayes, FACC (SYNTHETIC CARDIOLOGIST)",
        "role": UserRole.CARDIOLOGIST.value,
        "department": "Interventional Cardiology & Cath Lab",
        "phone": "+1-555-0301"
    },
    {
        "id": CARDIO_2_ID,
        "email": "cardio2@mediguard.local",
        "password": "CardioPass123!",
        "full_name": "Dr. Priya Patel, FESC (SYNTHETIC CARDIOLOGIST)",
        "role": UserRole.CARDIOLOGIST.value,
        "department": "Electrophysiology & Arrhythmia Service",
        "phone": "+1-555-0302"
    }
]

# 30 Synthetic Cardiac Patient Profiles (Varied Angioplasty / Stents / MI)
RAW_PATIENT_SPECS = [
    ("James", "Harrison", "1962-04-12", "male", "A+", CARDIO_1_ID, "CCU Bed 4", "urgent", "Acute Anterior STEMI", True, True, False, "2024-03-12", 1, "Everolimus DES 3.0x18mm", "Proximal LAD", 42.0),
    ("Eleanor", "Vance", "1968-09-24", "female", "O+", CARDIO_1_ID, "Telemetry Bed 12", "routine", "Post-PCI Stent Follow-Up", False, True, False, "2025-06-20", 2, "Zotarolimus DES 3.5x22mm", "Mid RCA", 55.0),
    ("Marcus", "Sterling", "1955-01-30", "male", "B+", CARDIO_2_ID, "Cardio ICU 2", "stat_emergency", "Acute Inferior STEMI with AV Block", True, True, False, "2026-11-12", 2, "Drug-Eluting Stents in RCA & PDA", "Distal RCA / PDA", 36.0),
    ("Beatrice", "Campbell", "1960-08-15", "female", "AB+", CARDIO_1_ID, "CCU Bed 2", "urgent", "NSTEMI with Multi-vessel Disease", True, False, False, None, 0, "No Stents (Awaiting Cath)", "Native Vessels", 45.0),
    ("Arthur", "Pendleton", "1952-11-04", "male", "O-", CARDIO_2_ID, "Step-Down 104", "routine", "Ischemic Cardiomyopathy (Post-CABG)", True, True, True, "2023-08-10", 3, "Saphenous Vein Graft Stents", "SVG to OM1", 32.0),
    ("Clara", "Oswald", "1974-03-19", "female", "A-", CARDIO_1_ID, "Telemetry Bed 8", "routine", "Unstable Angina, Single-Vessel CAD", False, True, False, "2025-01-15", 1, "Synergy DES 2.75x16mm", "Mid LAD", 58.0),
    ("Walter", "Bishop", "1949-06-27", "male", "B-", CARDIO_1_ID, "Cardio ICU 1", "stat_emergency", "Subacute In-Stent Restenosis", True, True, False, "2024-11-05", 2, "Drug-Coated Balloon & DES", "Proximal LAD Restenosis", 38.0),
    ("Diana", "Prince", "1980-12-01", "female", "O+", CARDIO_2_ID, "CCU Bed 6", "urgent", "Ventricular Tachycardia post-MI", True, True, False, "2025-09-18", 1, "Resolute Onyx 3.0x18mm", "LCx", 40.0),
    ("Victor", "Stone", "1972-07-22", "male", "A+", CARDIO_1_ID, "Step-Down 108", "routine", "Post-Angioplasty Routine Recovery", False, True, False, "2026-05-10", 1, "Xience Alpine DES 3.0x15mm", "Diagonal 1", 60.0),
    ("Martha", "Kent", "1958-02-14", "female", "B+", CARDIO_2_ID, "Telemetry Bed 5", "routine", "Atrial Fibrillation with Prior MI", True, False, False, None, 0, "Medical Management", "Native Vessels", 50.0),
    ("Bruce", "Wayne", "1965-05-29", "male", "O+", CARDIO_1_ID, "CCU Bed 1", "urgent", "Non-ST Elevation MI, LAD Culprit", True, True, False, "2026-10-02", 2, "Xience Sierra DES 3.5x28mm", "Proximal & Mid LAD", 48.0),
    ("Selina", "Kyle", "1976-10-11", "female", "A+", CARDIO_2_ID, "Step-Down 102", "routine", "Coronary Vasospastic Angina", False, False, False, None, 0, "No Stents Placed", "Native RCA", 62.0),
    ("Harvey", "Dent", "1963-09-08", "male", "AB-", CARDIO_1_ID, "Cardio ICU 3", "stat_emergency", "Acute Anterolateral STEMI", True, True, False, "2026-11-13", 2, "Promus Premier DES 3.0x24mm", "LAD / OM Bifurcation", 34.0),
    ("Pamela", "Isley", "1970-04-03", "female", "B+", CARDIO_2_ID, "Telemetry Bed 14", "routine", "Chronic Stable Angina post-Stent", False, True, False, "2024-04-18", 1, "Resolute Onyx 2.5x14mm", "Distal LCx", 54.0),
    ("Jonathan", "Crane", "1959-12-19", "male", "O-", CARDIO_1_ID, "CCU Bed 5", "urgent", "Recurrent Angina Post-Angioplasty", True, True, False, "2025-03-22", 1, "Biolimus DES 3.0x18mm", "Mid RCA", 46.0),
    ("Harleen", "Quinzel", "1982-07-20", "female", "A+", CARDIO_2_ID, "Telemetry Bed 9", "routine", "Post-PCI DES Follow-Up", False, True, False, "2026-08-01", 1, "Xience Skypoint 3.0x15mm", "Mid LAD", 56.0),
    ("Oswald", "Cobblepot", "1954-08-05", "male", "B-", CARDIO_1_ID, "CCU Bed 7", "urgent", "HFrEF secondary to Ischemic MI", True, True, False, "2023-12-14", 3, "Triple DES in LAD & RCA", "LAD / RCA / LCx", 28.0),
    ("Edward", "Nygma", "1967-01-25", "male", "O+", CARDIO_2_ID, "Step-Down 105", "routine", "Prior Inferior MI with Stents", True, True, False, "2025-07-09", 1, "Ultimaster DES 3.5x18mm", "Right Coronary Artery", 52.0),
    ("Barbara", "Gordon", "1978-11-16", "female", "A+", CARDIO_1_ID, "Telemetry Bed 2", "routine", "Post-Angioplasty Stent Surveillance", False, True, False, "2026-02-14", 1, "Orsiro Hybrid DES 2.75x18mm", "Diagonal Branch", 62.0),
    ("Dick", "Grayson", "1984-03-20", "male", "O+", CARDIO_2_ID, "Step-Down 101", "routine", "Athletic Heart with Ischemic Episode", False, True, False, "2026-09-04", 1, "Resolute Onyx 3.5x18mm", "Proximal LAD", 64.0),
    ("Jason", "Todd", "1986-06-12", "male", "B+", CARDIO_1_ID, "CCU Bed 3", "urgent", "Spontaneous Coronary Artery Dissection (SCAD)", False, True, False, "2026-11-01", 1, "Bioresorbable Scaffold", "Mid LAD", 50.0),
    ("Timothy", "Drake", "1988-09-09", "male", "A-", CARDIO_2_ID, "Telemetry Bed 4", "routine", "Suspected Coronary Microvascular Disease", False, False, False, None, 0, "No Stents", "Microvascular", 60.0),
    ("Stephanie", "Brown", "1985-05-02", "female", "O+", CARDIO_1_ID, "Telemetry Bed 11", "routine", "Post-Angioplasty Dual Antiplatelet Review", False, True, False, "2026-04-18", 1, "Synergy Megatron DES 4.0x20mm", "Ostial RCA", 58.0),
    ("Cassandra", "Cain", "1989-01-26", "female", "AB+", CARDIO_2_ID, "Step-Down 107", "routine", "Elective PCI Follow-Up", False, True, False, "2026-07-11", 1, "Xience Sierra 3.0x18mm", "Mid LCx", 65.0),
    ("Alfred", "Pennyworth", "1946-04-08", "male", "O+", CARDIO_1_ID, "CCU Bed 8", "urgent", "Severe Multi-vessel CAD post-MI", True, True, True, "2022-09-15", 4, "Quadruple DES and LIMA-LAD Graft", "LAD / RCA / LCx / LIMA", 35.0),
    ("Lucius", "Fox", "1951-10-31", "male", "A+", CARDIO_2_ID, "Step-Down 103", "routine", "Stable Angioplasty Surveillance", False, True, False, "2024-08-20", 2, "Xience Alpine DES in LAD & D1", "LAD Bifurcation", 52.0),
    ("Rachel", "Dawes", "1973-11-20", "female", "O-", CARDIO_1_ID, "Telemetry Bed 7", "routine", "Post-Infarction Rehabilitation", True, True, False, "2025-11-30", 1, "Resolute Onyx 3.0x15mm", "Mid RCA", 48.0),
    ("James", "Gordon", "1953-01-05", "male", "B+", CARDIO_1_ID, "Cardio ICU 4", "stat_emergency", "Acute Posterior STEMI with Shock", True, True, False, "2026-11-12", 2, "Emergency DES in Culprit LCx / OM", "LCx / OM2", 30.0),
    ("Vicki", "Vale", "1975-06-18", "female", "A+", CARDIO_2_ID, "Telemetry Bed 15", "routine", "Post-Stent Dual Antiplatelet Check", False, True, False, "2026-06-25", 1, "Promus Elite DES 3.0x16mm", "Mid LAD", 57.0),
    ("Thomas", "Elliot", "1961-08-28", "male", "AB+", CARDIO_1_ID, "Step-Down 109", "routine", "Prior MI with Stent Evaluation", True, True, False, "2024-10-12", 2, "Biotronik Orsiro DES in RCA", "Mid & Distal RCA", 44.0),
]


def seed_all():
    """Seeds synthetic users, 30 patients, cardiac histories, follow-ups, and ECG reports."""
    logger.info("Initializing synthetic seed data...")

    # 1. Seed Users
    for user_info in SYNTHETIC_USERS:
        password = user_info["password"]
        data = {k: v for k, v in user_info.items() if k != "password"}
        db_service.add_user(data, plain_password=password)
        logger.info("Seeded user: %s [%s]", data["email"], data["role"])

    # 2. Seed 30 Patients & Detailed Cardiac History
    today = date.today()
    for idx, spec in enumerate(RAW_PATIENT_SPECS, start=101):
        first_n, last_n, dob, gender, blood, cardio_id, room, urgency, cond, mi, stent, cabg, angio_date, stent_cnt, stent_desc, stent_loc, ef = spec

        p_code = f"MG-2026-{idx:06d}"
        p_id = f"44444444-4444-4444-4444-44444444{idx:04d}"
        
        # Make the 29th and 30th archived to test archive filters
        is_arch = (idx >= 129)

        # Spread admission date
        adm_days_ago = (30 - (idx - 101)) % 14
        adm_date = (datetime.now(timezone.utc) - timedelta(days=adm_days_ago, hours=idx % 8)).isoformat()

        patient_record = db_service.add_patient({
            "id": p_id,
            "patient_code": p_code,
            "first_name": f"{first_n} (Synthetic)",
            "last_name": last_n,
            "dob": dob,
            "gender": gender,
            "blood_group": blood,
            "contact_phone": f"+1-555-4{idx:03d}",
            "emergency_contact": f"Contact for {first_n} (+1-555-9{idx:03d})",
            "primary_cardiologist_id": cardio_id,
            "admission_date": adm_date,
            "room_bed": room,
            "urgency": urgency,
            "is_archived": is_arch
        })

        # Structured Medications
        structured_meds = [
            {"name": "Aspirin", "dose": "81mg", "freq": "Once daily"},
            {"name": "Ticagrelor" if mi else "Clopidogrel", "dose": "90mg" if mi else "75mg", "freq": "BID" if mi else "Daily"},
            {"name": "Atorvastatin", "dose": "80mg", "freq": "Nightly"},
            {"name": "Metoprolol Succinate", "dose": "50mg", "freq": "Once daily"}
        ]
        if ef and ef < 40.0:
            structured_meds.append({"name": "Sacubitril/Valsartan", "dose": "24/26mg", "freq": "BID"})
            structured_meds.append({"name": "Empagliflozin", "dose": "10mg", "freq": "Daily"})

        # Cardiac History Record
        db_service.add_cardiac_history({
            "patient_id": p_id,
            "condition_type": cond,
            "diagnosis_date": angio_date or (today - timedelta(days=60)).isoformat(),
            "prior_mi": mi,
            "prior_stent": stent,
            "prior_cabg": cabg,
            "angioplasty_date": angio_date,
            "stent_count": stent_cnt,
            "stent_type": "Drug-Eluting Stent (DES)" if stent else "None",
            "stent_location": stent_loc,
            "stent_details": stent_desc,
            "ejection_fraction": ef,
            "risk_factors": ["Hypertension", "Dyslipidemia"] + (["Tobacco Smoking History"] if idx % 2 == 0 else ["Type 2 Diabetes"]),
            "comorbidities": ["CKD Stage 2"] if idx % 3 == 0 else ["Peripheral Vascular Disease"] if idx % 5 == 0 else [],
            "allergies": ["Penicillin"] if idx % 4 == 0 else ["Iodinated Contrast"] if idx % 7 == 0 else [],
            "medications": [f"{m['name']} {m['dose']}" for m in structured_meds],
            "medications_structured": structured_meds,
            "doctor_comments": f"Clinical status reviewed by attending cardiologist. Ejection fraction verified at {ef}%. DAPT compliance verified.",
            "notes": f"Synthetic clinical profile {p_code}."
        })

        # 3. Follow-Ups (Mix of upcoming, overdue, and completed)
        # Overdue follow-up for odd index patients
        if idx % 3 == 1:
            db_service.add_follow_up({
                "patient_id": p_id,
                "doctor_id": cardio_id,
                "scheduled_date": (today - timedelta(days=idx % 7 + 1)).isoformat(), # in the past = overdue!
                "follow_up_type": "Post-Stent 30-Day Angiographic Follow-Up",
                "status": "scheduled",
                "notes": "Patient overdue for post-discharge clinical checkup."
            })
        # Upcoming follow-up for even index patients
        if idx % 2 == 0:
            db_service.add_follow_up({
                "patient_id": p_id,
                "doctor_id": cardio_id,
                "scheduled_date": (today + timedelta(days=idx % 14 + 2)).isoformat(), # upcoming
                "follow_up_type": "Routine Echocardiogram & Stent Review",
                "status": "scheduled",
                "notes": "Scheduled 3-month post-PCI outpatient visit."
            })
        # Completed follow-up
        if idx % 4 == 0:
            db_service.add_follow_up({
                "patient_id": p_id,
                "doctor_id": cardio_id,
                "scheduled_date": (today - timedelta(days=20)).isoformat(),
                "follow_up_type": "Immediate Post-Angioplasty CCU Check",
                "status": "completed",
                "completed_at": (datetime.now(timezone.utc) - timedelta(days=20)).isoformat(),
                "outcome": "Access site intact. No hematoma. Hemodynamically stable."
            })

        # 4. Seed ECG Reports (for first 12 patients)
        if idx <= 112:
            rep_id = f"55555555-5555-5555-5555-55555555{idx:04d}"
            rep_urgency = "stat_emergency" if urgency == "stat_emergency" else ("urgent" if idx % 2 == 0 else "routine")
            rep_status = "reviewed" if idx % 3 == 0 else ("flagged_urgent" if rep_urgency != "routine" else "analyzed")
            
            db_service.add_ecg_report({
                "id": rep_id,
                "patient_id": p_id,
                "uploaded_by": "22222222-2222-2222-2222-222222222221", # staff1
                "assigned_cardiologist_id": cardio_id,
                "recording_time": adm_date,
                "file_path": f"ecg_signals/{p_code}_12lead.dat",
                "file_name": f"{p_code}_12lead.dat",
                "file_type": "digital_12lead",
                "urgency": rep_urgency,
                "status": rep_status,
                "sampling_rate": 500,
                "leads_present": "I,II,III,aVR,aVL,aVF,V1,V2,V3,V4,V5,V6",
                "notes": f"Standard digital 12-lead record for {first_n} {last_n}."
            })

            # If reviewed, add signed review
            if rep_status == "reviewed":
                db_service.add_doctor_review({
                    "report_id": rep_id,
                    "cardiologist_id": cardio_id,
                    "clinical_findings": f"Sinus rhythm, pathological Q waves and ST elevation consistent with {cond}.",
                    "diagnosis": cond,
                    "recommendation": "Maintain dual antiplatelet therapy and statin therapy. Monitor telemetry.",
                    "agreement_with_model": "agreed" if idx % 2 == 0 else "partially_agreed",
                    "is_urgent_escalation": (urgency == "stat_emergency")
                })

    # 5. Create Fresh Admin Account with Newly Generated Password
    create_fresh_admin()

    logger.info("Synthetic seed data initialization complete. 30 patients, cardiac histories, follow-ups & ECG reports created.")


def create_fresh_admin(email: str = "fresh_admin@mediguard.local", password: str = None) -> tuple:
    """Create a fresh admin account with a newly generated cryptographically strong password."""
    creds_path = Path(__file__).resolve().parent.parent.parent / "admin_credentials.txt"

    # If password not explicitly given, reuse from admin_credentials.txt if already generated,
    # or generate a brand new secure password.
    if not password and creds_path.exists():
        try:
            for line in creds_path.read_text(encoding="utf-8").splitlines():
                if line.startswith("Password:"):
                    saved_pw = line.split(":", 1)[1].strip()
                    if saved_pw:
                        password = saved_pw
                        break
        except Exception:
            pass

    if not password:
        # Generate 16-character secure password with upper, lower, digits, symbols
        chars = string.ascii_letters + string.digits + "!@#$%^&*"
        password = (
            secrets.choice(string.ascii_uppercase) +
            secrets.choice(string.ascii_lowercase) +
            secrets.choice(string.digits) +
            secrets.choice("!@#$%^&*") +
            "".join(secrets.choice(chars) for _ in range(12))
        )

    admin_id = str(uuid.uuid4())
    admin_user = {
        "id": admin_id,
        "email": email,
        "full_name": "Emergency Recovery Admin (SYNTHETIC ADMIN)",
        "role": UserRole.ADMIN.value,
        "department": "Cardiology & Clinical Informatics",
        "phone": "+1-555-0199"
    }
    db_service.add_user(admin_user, plain_password=password)

    creds_path = Path(__file__).resolve().parent.parent.parent / "admin_credentials.txt"
    with open(creds_path, "w", encoding="utf-8") as f:
        f.write("MediGuard AI - Fresh Admin Credentials\n")
        f.write("=" * 40 + "\n")
        f.write(f"Generated At: {datetime.now(timezone.utc).isoformat()}\n")
        f.write(f"Email:        {email}\n")
        f.write(f"Password:     {password}\n")
        f.write("Role:         admin\n")
        f.write("=" * 40 + "\n")

    logger.info("Fresh admin account created successfully: %s", email)
    return email, password


if __name__ == "__main__":
    if "--reset" in sys.argv:
        logger.info("Executing database reset before seeding...")
        db_service.reset_all_data()

    seed_all()
