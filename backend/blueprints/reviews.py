"""
MediGuard AI – Doctor Reviews & Prioritized Review Workspace Blueprint
Protected clinical decision support endpoints strictly restricted to cardiologists and admin.
Demonstrates:
- Structured cardiological interpretation (rhythm, ST/T findings, conduction, overall impression)
- Transparent rule-based review prioritization queue (urgent / prompt / routine)
- Append-only review history and edit audit trail
- Draft saving and retrieval
- Seamless follow-up visit scheduling directly upon review signing
"""
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify, g

from backend.models.enums import UserRole, AgreementWithModel
from backend.services.auth_service import roles_required
from backend.services.db_service import db_service
from backend.services.audit_service import log_action
from backend.services.priority_engine import priority_engine
from backend.services.notification_service import notification_service, NOTIFICATION_TYPES

reviews_bp = Blueprint("reviews", __name__, url_prefix="/api/reviews")


@reviews_bp.route("", methods=["GET"])
@roles_required(UserRole.CARDIOLOGIST.value, UserRole.ADMIN.value)
def list_reviews():
    """List all clinical doctor reviews (Cardiologist or Admin only)."""
    reviews = db_service.list_doctor_reviews()
    return jsonify({
        "status": "success",
        "count": len(reviews),
        "data": reviews
    }), 200


@reviews_bp.route("/queue", methods=["GET"])
@roles_required(UserRole.CARDIOLOGIST.value, UserRole.ADMIN.value)
def get_prioritised_review_queue():
    """
    Get unreviewed ECG reports prioritised transparently by the priority_engine.
    Sorted: urgent -> prompt -> routine.
    Each item includes reasons, supporting ML notes, and patient cardiac context.
    """
    unreviewed = [r for r in db_service.ecg_reports.values() if r.get("status") in ("pending", "analyzed", "analysed", "completed", "not_compatible_ml")]
    prioritised_items = []

    for rep in unreviewed:
        pt_id = rep.get("patient_id")
        patient = db_service.get_patient(pt_id) or {}
        analysis = db_service.get_ecg_analysis(rep["id"]) or {}
        histories = db_service.get_patient_cardiac_history(pt_id)
        latest_hist = histories[0] if histories else {}

        # Calculate days since angioplasty
        days_since_pci = None
        pci_date_str = latest_hist.get("diagnosis_date")
        if pci_date_str:
            try:
                pci_dt = datetime.fromisoformat(str(pci_date_str).replace("Z", "+00:00"))
                days_since_pci = (datetime.now(timezone.utc) - pci_dt).days
            except Exception:
                pass

        # Check overdue follow-up
        follow_ups = db_service.list_follow_ups(patient_id=pt_id, overdue_only=True)
        is_overdue = len(follow_ups) > 0

        patient_ctx = {
            "clinician_urgency": rep.get("urgency") or patient.get("urgency", "routine"),
            "symptoms": [patient.get("urgency")] if patient.get("urgency") == "stat_emergency" else [],
            "days_since_angioplasty": days_since_pci,
            "stent_count": latest_hist.get("stent_count", 0),
            "is_overdue_followup": is_overdue,
            "overdue_days": 5 if is_overdue else 0,
            "previous_findings": [latest_hist.get("condition_type", "")] if latest_hist.get("condition_type") else []
        }

        ecg_ctx = {
            "model_scores": {
                "NORM": analysis.get("norm_score", 0.0),
                "MI": analysis.get("mi_score", 0.0),
                "STTC": analysis.get("sttc_score", 0.0),
                "CD": analysis.get("cd_score", 0.0),
                "HYP": analysis.get("hyp_score", 0.0),
            } if analysis else {},
            "signal_quality": analysis.get("signal_quality", "high")
        }

        # Run transparent priority engine
        p_res = priority_engine.evaluate_priority(patient_ctx, ecg_ctx)

        prioritised_items.append({
            "report_id": rep["id"],
            "patient_id": pt_id,
            "patient_code": patient.get("patient_code", "UNKNOWN"),
            "patient_name": f"{patient.get('first_name', '')} {patient.get('last_name', '')}",
            "room_bed": patient.get("room_bed", "CCU"),
            "report_date": rep.get("recording_time") or rep.get("created_at"),
            "file_type": rep.get("file_type", "digital_12lead"),
            "status": rep.get("status"),
            "priority": p_res.priority,
            "priority_reasons": p_res.reasons,
            "ml_supporting_notes": p_res.ml_supporting_notes,
            "rule_disclaimer": p_res.rule_disclaimer,
            "stent_count": latest_hist.get("stent_count", 0),
            "condition_type": latest_hist.get("condition_type", "Cardiology Monitoring")
        })

    # Sort items: urgent first (0), prompt second (1), routine last (2)
    order_map = {"urgent": 0, "prompt": 1, "routine": 2}
    prioritised_items.sort(key=lambda x: (order_map.get(x["priority"], 9), str(x["report_date"])))

    return jsonify({
        "status": "success",
        "count": len(prioritised_items),
        "data": prioritised_items
    }), 200


@reviews_bp.route("/draft", methods=["POST"])
@roles_required(UserRole.CARDIOLOGIST.value, UserRole.ADMIN.value)
def save_draft():
    """Save an in-progress review draft."""
    user = g.current_user
    data = request.get_json(silent=True) or {}
    report_id = data.get("report_id")

    if not report_id:
        return jsonify({"error": "Bad Request", "message": "report_id is required", "status_code": 400}), 400

    draft = db_service.save_review_draft(report_id, user["id"], data)
    return jsonify({
        "status": "success",
        "message": "Review draft saved successfully.",
        "data": draft
    }), 200


@reviews_bp.route("/draft/<report_id>", methods=["GET"])
@roles_required(UserRole.CARDIOLOGIST.value, UserRole.ADMIN.value)
def get_draft(report_id):
    """Retrieve an active draft for a specific report."""
    user = g.current_user
    draft = db_service.get_review_draft(report_id, user["id"])
    return jsonify({
        "status": "success",
        "has_draft": draft is not None,
        "data": draft.get("data") if draft else None
    }), 200


@reviews_bp.route("/report/<report_id>/history", methods=["GET"])
@roles_required(UserRole.CARDIOLOGIST.value, UserRole.ADMIN.value)
def get_review_history(report_id):
    """Retrieve append-only review history for a report."""
    history = db_service.get_review_history(report_id)
    return jsonify({
        "status": "success",
        "report_id": report_id,
        "count": len(history),
        "data": history
    }), 200


@reviews_bp.route("", methods=["POST"])
@roles_required(UserRole.CARDIOLOGIST.value, UserRole.ADMIN.value)
def create_review():
    """
    Submit and sign a formal doctor review for an ECG report.
    Doctors own 100% of the diagnostic decision.
    """
    user = g.current_user
    data = request.get_json(silent=True) or {}

    report_id = data.get("report_id")
    clinical_findings = data.get("clinical_findings", "").strip()
    diagnosis = data.get("diagnosis", "").strip()
    recommendation = data.get("recommendation", "").strip()
    agreement_with_model = data.get("agreement_with_model", "not_applicable").strip()
    is_urgent_escalation = bool(data.get("is_urgent_escalation", False))

    # Structured interpretation fields
    rhythm = data.get("rhythm", "Normal Sinus Rhythm").strip()
    st_t_findings = data.get("st_t_findings", "Normal").strip()
    conduction = data.get("conduction", "Normal AV Conduction").strip()
    overall_impression = data.get("overall_impression", "").strip() or diagnosis
    urgency_assignment = data.get("urgency_assignment", "routine").strip()

    if not report_id or not clinical_findings or not diagnosis or not recommendation:
        return jsonify({
            "error": "Bad Request",
            "message": "Missing required clinical review fields: report_id, clinical_findings, diagnosis, recommendation",
            "status_code": 400
        }), 400

    valid_agreements = [a.value for a in AgreementWithModel]
    if agreement_with_model not in valid_agreements:
        agreement_with_model = "not_applicable"

    review_record = db_service.add_doctor_review({
        "report_id": report_id,
        "cardiologist_id": user["id"],
        "clinical_findings": clinical_findings,
        "diagnosis": diagnosis,
        "recommendation": recommendation,
        "agreement_with_model": agreement_with_model,
        "is_urgent_escalation": is_urgent_escalation,
        "rhythm": rhythm,
        "st_t_findings": st_t_findings,
        "conduction": conduction,
        "overall_impression": overall_impression,
        "urgency_assignment": urgency_assignment
    })

    # Optional: Schedule follow-up visit directly from review workspace
    follow_up_record = None
    if data.get("schedule_follow_up") and data.get("follow_up_date"):
        rep = db_service.get_ecg_report(report_id)
        if rep:
            follow_up_record = db_service.add_follow_up({
                "patient_id": rep["patient_id"],
                "doctor_id": user["id"],
                "scheduled_date": data["follow_up_date"],
                "follow_up_type": data.get("follow_up_type", "Post-Stent Clinical Review"),
                "notes": f"Scheduled during ECG review: {recommendation}",
                "status": "scheduled"
            })

    log_action(
        user=user,
        action="DOCTOR_REVIEW_SUBMITTED",
        entity_type="DOCTOR_REVIEW",
        entity_id=review_record["id"],
        ip=request.remote_addr,
        user_agent=request.headers.get("User-Agent"),
        metadata={
            "report_id": report_id,
            "agreement": agreement_with_model,
            "is_urgent": is_urgent_escalation,
            "version": review_record.get("version", 1),
            "follow_up_scheduled": follow_up_record is not None
        }
    )

    return jsonify({
        "status": "success",
        "message": "Clinical review signed and registered successfully.",
        "data": review_record,
        "follow_up": follow_up_record
    }), 201
