"""
MediGuard AI – Patients & Cardiac History Blueprint
Handles complete patient registration, longitudinal history, follow-up scheduling,
role-based scoping (Cardiologist assigned scoping), and soft-delete archiving.
"""
from datetime import date, datetime
import re
from typing import Tuple, Optional
from flask import Blueprint, request, jsonify, g

from backend.models.enums import UserRole, ReportUrgency
from backend.services.auth_service import login_required, roles_required
from backend.services.db_service import db_service
from backend.services.audit_service import log_action

patients_bp = Blueprint("patients", __name__, url_prefix="/api")

PHONE_REGEX = re.compile(r"^[\+]?[(]?[0-9]{3}[)]?[-\s\.]?[0-9]{3}[-\s\.]?[0-9]{4,6}$")


def validate_patient_payload(data: dict, is_create: bool = True) -> Tuple[bool, Optional[str]]:
    """Validate patient demographics, dates, and contact formats."""
    today = date.today()

    if is_create:
        required = ["first_name", "last_name", "dob", "gender"]
        missing = [f for f in required if not data.get(f)]
        if missing:
            return False, f"Missing required fields: {', '.join(missing)}"

    # Validate Gender
    if "gender" in data:
        g_val = str(data["gender"]).strip().lower()
        if g_val not in ("male", "female", "other"):
            return False, "Gender must be 'male', 'female', or 'other'."

    # Validate DOB
    if "dob" in data and data["dob"]:
        try:
            dob_date = date.fromisoformat(str(data["dob"]).split("T")[0])
            if dob_date > today:
                return False, "Date of birth cannot be in the future."
            if dob_date.year < 1900:
                return False, "Invalid date of birth."
        except ValueError:
            return False, "Invalid DOB format. Expected YYYY-MM-DD."

    # Validate Angioplasty Date if present
    if "angioplasty_date" in data and data["angioplasty_date"]:
        try:
            angio_date = date.fromisoformat(str(data["angioplasty_date"]).split("T")[0])
            if angio_date > today:
                return False, "Angioplasty / procedure date cannot be in the future."
        except ValueError:
            return False, "Invalid angioplasty date format. Expected YYYY-MM-DD."

    # Validate Phone format if provided
    if "contact_phone" in data and data["contact_phone"]:
        phone = str(data["contact_phone"]).strip()
        if len(phone) < 7 or len(phone) > 20:
            return False, "Contact phone number must be between 7 and 20 digits."

    # Validate Urgency if provided
    if "urgency" in data and data["urgency"]:
        if data["urgency"] not in ("routine", "urgent", "stat_emergency"):
            return False, "Urgency must be 'routine', 'urgent', or 'stat_emergency'."

    return True, None


# ------------------------------------------------------------------------------
# 1. Patients CRUD & Listing
# ------------------------------------------------------------------------------

@patients_bp.route("/patients", methods=["GET"])
@login_required
def list_patients():
    """
    List patients with search, filters (cardiologist, diagnosis, urgency),
    pagination, sorting, and role-based visibility.
    """
    user = g.current_user
    search = request.args.get("search")
    urgency = request.args.get("urgency")
    diagnosis = request.args.get("diagnosis")
    cardiologist_id = request.args.get("cardiologist_id")
    include_archived = request.args.get("include_archived", "false").lower() in ("true", "1")
    sort_by = request.args.get("sort_by", "created_at")
    sort_dir = request.args.get("sort_dir", "desc")
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 50))

    # RBAC Scoping: Cardiologists can only see their assigned patients unless Admin
    if user["role"] == UserRole.CARDIOLOGIST.value:
        cardiologist_id = user["id"]

    records, total_count = db_service.list_patients(
        search=search,
        cardiologist_id=cardiologist_id,
        urgency=urgency,
        diagnosis=diagnosis,
        include_archived=include_archived,
        sort_by=sort_by,
        sort_dir=sort_dir,
        page=page,
        per_page=per_page
    )

    # Attach primary cardiologist name and cardiac history summary
    for p in records:
        cardio = db_service.get_user_by_id(p.get("primary_cardiologist_id"))
        p["primary_cardiologist_name"] = cardio["full_name"] if cardio else "Unassigned"
        histories = db_service.get_patient_cardiac_history(p["id"])
        p["latest_diagnosis"] = histories[0]["condition_type"] if histories else "Under Initial Observation"
        p["stent_summary"] = histories[0]["stent_details"] if (histories and histories[0].get("stent_details")) else "No Stents Recorded"

    log_action(
        user=user,
        action="PATIENT_LIST_VIEWED",
        entity_type="PATIENTS",
        ip=request.remote_addr,
        user_agent=request.headers.get("User-Agent"),
        metadata={"count": len(records), "total": total_count, "page": page}
    )

    return jsonify({
        "status": "success",
        "data": records,
        "pagination": {
            "total": total_count,
            "page": page,
            "per_page": per_page,
            "total_pages": (total_count + per_page - 1) // per_page if total_count else 1
        }
    }), 200


@patients_bp.route("/patients", methods=["POST"])
@roles_required(UserRole.STAFF.value, UserRole.ADMIN.value)
def create_patient():
    """Register a new synthetic cardiac patient (Staff & Admin only)."""
    user = g.current_user
    data = request.get_json(silent=True)
    if not data or not isinstance(data, dict):
        return jsonify({
            "error": "Bad Request",
            "message": "Invalid JSON body provided",
            "status_code": 400
        }), 400

    valid, err_msg = validate_patient_payload(data, is_create=True)
    if not valid:
        return jsonify({
            "error": "Validation Error",
            "message": err_msg,
            "status_code": 422
        }), 422

    patient = db_service.add_patient(data)

    log_action(
        user=user,
        action="PATIENT_CREATED",
        entity_type="PATIENT",
        entity_id=patient["id"],
        ip=request.remote_addr,
        user_agent=request.headers.get("User-Agent"),
        metadata={"patient_code": patient["patient_code"]}
    )

    return jsonify({
        "status": "success",
        "message": f"Patient {patient['patient_code']} registered successfully.",
        "data": patient
    }), 201


@patients_bp.route("/patients/<patient_id>", methods=["GET"])
@login_required
def get_patient(patient_id):
    """
    Get full patient profile with cardiac history, follow-ups, and reports.
    Cardiologists are strictly restricted to assigned patients (403 Forbidden).
    """
    user = g.current_user
    patient = db_service.get_patient_by_id(patient_id)

    if not patient:
        return jsonify({
            "error": "Not Found",
            "message": f"Patient record with ID '{patient_id}' not found.",
            "status_code": 404
        }), 404

    # RBAC Scoping check
    if user["role"] == UserRole.CARDIOLOGIST.value:
        assigned_id = str(patient.get("primary_cardiologist_id") or "")
        if assigned_id and assigned_id != str(user["id"]):
            log_action(
                user=user,
                action="PATIENT_ACCESS_DENIED",
                entity_type="PATIENT",
                entity_id=patient_id,
                ip=request.remote_addr,
                user_agent=request.headers.get("User-Agent"),
                metadata={"reason": "Cardiologist not assigned to this patient"}
            )
            return jsonify({
                "error": "Forbidden",
                "message": "Access denied. Cardiologists may only access their assigned cardiology patients.",
                "status_code": 403
            }), 403

    # Audit log read of patient record
    log_action(
        user=user,
        action="PATIENT_READ",
        entity_type="PATIENT",
        entity_id=patient_id,
        ip=request.remote_addr,
        user_agent=request.headers.get("User-Agent"),
        metadata={"patient_code": patient["patient_code"]}
    )

    # Attach related records
    cardio_history = db_service.get_patient_cardiac_history(patient_id)
    follow_ups = db_service.list_follow_ups(patient_id=patient_id)
    ecg_reports = db_service.list_ecg_reports(patient_id=patient_id)
    assigned_doc = db_service.get_user_by_id(patient.get("primary_cardiologist_id"))

    response_data = dict(patient)
    response_data["primary_cardiologist"] = assigned_doc
    response_data["cardiac_history"] = cardio_history
    response_data["follow_ups"] = follow_ups
    response_data["ecg_reports"] = ecg_reports

    return jsonify({
        "status": "success",
        "data": response_data
    }), 200


@patients_bp.route("/patients/<patient_id>", methods=["PUT"])
@login_required
def update_patient(patient_id):
    """Update patient demographics or clinical details."""
    user = g.current_user
    patient = db_service.get_patient_by_id(patient_id)

    if not patient:
        return jsonify({
            "error": "Not Found",
            "message": f"Patient with ID '{patient_id}' not found.",
            "status_code": 404
        }), 404

    # RBAC check for cardiologists
    if user["role"] == UserRole.CARDIOLOGIST.value:
        assigned_id = str(patient.get("primary_cardiologist_id") or "")
        if assigned_id and assigned_id != str(user["id"]):
            return jsonify({
                "error": "Forbidden",
                "message": "Access denied. You cannot modify records for patients not assigned to you.",
                "status_code": 403
            }), 403

    data = request.get_json(silent=True) or {}
    valid, err_msg = validate_patient_payload(data, is_create=False)
    if not valid:
        return jsonify({
            "error": "Validation Error",
            "message": err_msg,
            "status_code": 422
        }), 422

    updated = db_service.update_patient(patient_id, data)

    log_action(
        user=user,
        action="PATIENT_UPDATED",
        entity_type="PATIENT",
        entity_id=patient_id,
        ip=request.remote_addr,
        user_agent=request.headers.get("User-Agent"),
        metadata={"fields_updated": list(data.keys())}
    )

    return jsonify({
        "status": "success",
        "message": "Patient demographics updated successfully.",
        "data": updated
    }), 200


@patients_bp.route("/patients/<patient_id>", methods=["DELETE"])
@roles_required(UserRole.STAFF.value, UserRole.ADMIN.value)
def archive_patient(patient_id):
    """Soft-delete / archive a patient record (Staff & Admin only)."""
    user = g.current_user
    patient = db_service.get_patient_by_id(patient_id)
    if not patient:
        return jsonify({"error": "Not Found", "message": "Patient not found", "status_code": 404}), 404

    archived = db_service.archive_patient(patient_id)

    log_action(
        user=user,
        action="PATIENT_ARCHIVED",
        entity_type="PATIENT",
        entity_id=patient_id,
        ip=request.remote_addr,
        user_agent=request.headers.get("User-Agent"),
        metadata={"patient_code": patient["patient_code"]}
    )

    return jsonify({
        "status": "success",
        "message": f"Patient {patient['patient_code']} successfully archived.",
        "data": archived
    }), 200


# ------------------------------------------------------------------------------
# 2. Cardiac History Endpoints
# ------------------------------------------------------------------------------

@patients_bp.route("/patients/<patient_id>/cardiac-history", methods=["GET"])
@login_required
def get_cardiac_history(patient_id):
    """List longitudinal cardiac events, stents, and medication history."""
    patient = db_service.get_patient_by_id(patient_id)
    if not patient:
        return jsonify({"error": "Not Found", "message": "Patient not found", "status_code": 404}), 404

    history = db_service.get_patient_cardiac_history(patient_id)
    return jsonify({
        "status": "success",
        "count": len(history),
        "data": history
    }), 200


@patients_bp.route("/patients/<patient_id>/cardiac-history", methods=["POST"])
@login_required
def add_cardiac_history_entry(patient_id):
    """Add a new cardiac history entry (stent, MI, medication updates)."""
    user = g.current_user
    patient = db_service.get_patient_by_id(patient_id)
    if not patient:
        return jsonify({"error": "Not Found", "message": "Patient not found", "status_code": 404}), 404

    # Cardiologist scoping check
    if user["role"] == UserRole.CARDIOLOGIST.value:
        assigned_id = str(patient.get("primary_cardiologist_id") or "")
        if assigned_id and assigned_id != str(user["id"]):
            return jsonify({"error": "Forbidden", "message": "Access denied for unassigned patient.", "status_code": 403}), 403

    data = request.get_json(silent=True) or {}
    condition_type = data.get("condition_type", "").strip()
    if not condition_type:
        return jsonify({"error": "Validation Error", "message": "condition_type is required", "status_code": 422}), 422

    # Date validation: angioplasty date cannot be in the future
    if "angioplasty_date" in data and data["angioplasty_date"]:
        try:
            a_date = date.fromisoformat(str(data["angioplasty_date"]).split("T")[0])
            if a_date > date.today():
                return jsonify({"error": "Validation Error", "message": "Angioplasty date cannot be in the future.", "status_code": 422}), 422
        except ValueError:
            return jsonify({"error": "Validation Error", "message": "Invalid angioplasty date format.", "status_code": 422}), 422

    data["patient_id"] = patient_id
    entry = db_service.add_cardiac_history(data)

    log_action(
        user=user,
        action="CARDIAC_HISTORY_ADDED",
        entity_type="CARDIAC_HISTORY",
        entity_id=entry["id"],
        ip=request.remote_addr,
        user_agent=request.headers.get("User-Agent"),
        metadata={"patient_code": patient["patient_code"], "condition": condition_type}
    )

    return jsonify({
        "status": "success",
        "message": "Cardiac history record added successfully.",
        "data": entry
    }), 201


# ------------------------------------------------------------------------------
# 3. Follow-Ups Endpoints
# ------------------------------------------------------------------------------

@patients_bp.route("/patients/<patient_id>/follow-ups", methods=["GET"])
@login_required
def get_patient_follow_ups(patient_id):
    """Retrieve all follow-ups for a specific patient."""
    follow_ups = db_service.list_follow_ups(patient_id=patient_id)
    return jsonify({
        "status": "success",
        "count": len(follow_ups),
        "data": follow_ups
    }), 200


@patients_bp.route("/patients/<patient_id>/follow-ups", methods=["POST"])
@login_required
def create_patient_follow_up(patient_id):
    """Schedule a post-procedure or routine cardiac follow-up."""
    user = g.current_user
    patient = db_service.get_patient_by_id(patient_id)
    if not patient:
        return jsonify({"error": "Not Found", "message": "Patient not found", "status_code": 404}), 404

    data = request.get_json(silent=True) or {}
    scheduled_date_str = data.get("scheduled_date", "").strip()
    if not scheduled_date_str:
        return jsonify({"error": "Validation Error", "message": "scheduled_date is required", "status_code": 422}), 422

    try:
        date.fromisoformat(scheduled_date_str.split("T")[0])
    except ValueError:
        return jsonify({"error": "Validation Error", "message": "Invalid scheduled_date format. Expected YYYY-MM-DD.", "status_code": 422}), 422

    data["patient_id"] = patient_id
    data["doctor_id"] = data.get("doctor_id") or patient.get("primary_cardiologist_id") or user["id"]
    follow_up = db_service.add_follow_up(data)

    log_action(
        user=user,
        action="FOLLOW_UP_SCHEDULED",
        entity_type="FOLLOW_UP",
        entity_id=follow_up["id"],
        ip=request.remote_addr,
        user_agent=request.headers.get("User-Agent"),
        metadata={"scheduled_date": scheduled_date_str, "patient_code": patient["patient_code"]}
    )

    return jsonify({
        "status": "success",
        "message": "Follow-up successfully scheduled.",
        "data": follow_up
    }), 201


@patients_bp.route("/follow-ups", methods=["GET"])
@login_required
def list_all_follow_ups():
    """List follow-ups across patients with overdue detection."""
    doctor_id = request.args.get("doctor_id")
    status = request.args.get("status")
    overdue_only = request.args.get("overdue", "false").lower() in ("true", "1")

    follow_ups = db_service.list_follow_ups(doctor_id=doctor_id, status=status, overdue_only=overdue_only)

    # Attach patient info
    for f in follow_ups:
        p = db_service.get_patient_by_id(f.get("patient_id"))
        if p:
            f["patient_code"] = p["patient_code"]
            f["patient_name"] = f"{p['first_name']} {p['last_name']}"
            f["patient_room"] = p.get("room_bed", "")

    return jsonify({
        "status": "success",
        "count": len(follow_ups),
        "data": follow_ups
    }), 200


@patients_bp.route("/follow-ups/<follow_up_id>", methods=["PATCH"])
@login_required
def update_follow_up_status(follow_up_id):
    """Mark follow-up completed, cancelled, or update notes."""
    user = g.current_user
    data = request.get_json(silent=True) or {}
    status = data.get("status")
    if status and status not in ("scheduled", "completed", "cancelled", "missed"):
        return jsonify({"error": "Validation Error", "message": "Invalid follow-up status", "status_code": 422}), 422

    updated = db_service.update_follow_up(follow_up_id, data)
    if not updated:
        return jsonify({"error": "Not Found", "message": "Follow-up not found", "status_code": 404}), 404

    log_action(
        user=user,
        action="FOLLOW_UP_UPDATED",
        entity_type="FOLLOW_UP",
        entity_id=follow_up_id,
        ip=request.remote_addr,
        user_agent=request.headers.get("User-Agent"),
        metadata={"new_status": updated.get("status")}
    )

    return jsonify({
        "status": "success",
        "message": f"Follow-up marked as {updated.get('status')}.",
        "data": updated
    }), 200
