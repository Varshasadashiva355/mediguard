"""
MediGuard AI – Notifications Blueprint
Provides REST endpoints for in-app clinical alerts, marking read,
emergency notification triggers, and user preferences.
"""
from flask import Blueprint, request, jsonify, g
from backend.services.auth_service import login_required
from backend.services.notification_service import notification_service
from backend.services.db_service import db_service
from backend.services.audit_service import log_action

notifications_bp = Blueprint("notifications", __name__, url_prefix="/api/notifications")


@notifications_bp.route("", methods=["GET"])
@login_required
def get_user_notifications():
    """Retrieve notifications for the authenticated clinician."""
    user = g.current_user
    user_id = user["id"]
    unread_only = request.args.get("unread_only", "false").lower() in ("true", "1")
    limit = int(request.args.get("limit", 50))

    notifs = db_service.list_notifications(user_id, unread_only=unread_only, limit=limit)
    unread_count = db_service.get_unread_notification_count(user_id)

    return jsonify({
        "status": "success",
        "unread_count": unread_count,
        "total_returned": len(notifs),
        "data": notifs
    }), 200


@notifications_bp.route("/<notif_id>/read", methods=["PATCH"])
@login_required
def mark_read(notif_id):
    """Mark a specific notification as read."""
    user = g.current_user
    updated = db_service.mark_notification_read(notif_id, user["id"])
    if not updated:
        return jsonify({
            "error": "Not Found",
            "message": "Notification not found or unauthorized.",
            "status_code": 404
        }), 404

    return jsonify({
        "status": "success",
        "message": "Notification marked as read.",
        "data": updated
    }), 200


@notifications_bp.route("/mark-all-read", methods=["POST"])
@login_required
def mark_all_read():
    """Mark all notifications as read for current clinician."""
    user = g.current_user
    count = db_service.mark_all_notifications_read(user["id"])
    return jsonify({
        "status": "success",
        "message": f"{count} notifications marked as read.",
        "count": count
    }), 200


@notifications_bp.route("/emergency", methods=["POST"])
@login_required
def trigger_emergency_alert():
    """
    Emergency Symptom Escalation Endpoint (Rule 9 Protocol).
    Staff or doctor flags severe acute symptoms (chest pain, syncope, shock).
    Bypasses ML inference and immediately notifies all cardiologists.
    """
    user = g.current_user
    data = request.get_json(silent=True) or {}
    patient_id = data.get("patient_id")
    symptom = data.get("symptom", "acute_chest_pain")

    if not patient_id:
        return jsonify({
            "error": "Bad Request",
            "message": "patient_id is required to trigger an emergency alert.",
            "status_code": 400
        }), 400

    patient = db_service.get_patient(patient_id)
    if not patient:
        return jsonify({
            "error": "Not Found",
            "message": f"Patient with ID {patient_id} does not exist.",
            "status_code": 404
        }), 404

    # Update patient urgency to stat_emergency
    db_service.update_patient(patient_id, {"urgency": "stat_emergency"})

    # Send emergency notifications immediately
    dispatched = notification_service.notify_emergency_symptom(
        patient_id=patient_id,
        symptom=symptom,
        reported_by_name=user.get("full_name", user.get("email", "Staff"))
    )

    log_action(
        user=user,
        action="EMERGENCY_PROTOCOL_TRIGGERED",
        entity_type="PATIENT",
        entity_id=patient_id,
        ip=request.remote_addr,
        metadata={"symptom": symptom, "dispatched_count": len(dispatched)}
    )

    return jsonify({
        "status": "success",
        "message": "Emergency protocol dispatched. Cardiologists notified immediately.",
        "dispatched_count": len(dispatched),
        "protocol": {
            "rule": "Rule 9: Critical findings must never wait on AI inference.",
            "code_blue_ext": "2222",
            "cath_lab_ext": "4400"
        }
    }), 201
