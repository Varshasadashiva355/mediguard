"""
MediGuard AI – Hospital Dashboard Blueprint
Provides dynamic SQL/database aggregates for hospital metric cards,
patient priority queue widget, recent uploads, and Chart.js datasets.
NON-NEGOTIABLE RULE: Dashboard stats must come from real database aggregates, not mock numbers.
"""
from flask import Blueprint, jsonify, g

from backend.services.auth_service import login_required
from backend.services.db_service import db_service
from backend.services.audit_service import log_action

dashboard_bp = Blueprint("dashboard", __name__, url_prefix="/api/dashboard")


@dashboard_bp.route("/stats", methods=["GET"])
@login_required
def get_stats():
    """
    Returns live SQL/database aggregates for dashboard metric cards:
    - Total cardiac patients
    - Uploaded ECG reports
    - Pending doctor reviews
    - Reports flagged for clinical attention
    - Upcoming and overdue follow-ups
    """
    user = g.current_user
    stats = db_service.get_dashboard_stats(user=user)

    log_action(
        user=user,
        action="DASHBOARD_STATS_VIEWED",
        entity_type="DASHBOARD",
        metadata=stats
    )

    return jsonify({
        "status": "success",
        "data": stats
    }), 200


@dashboard_bp.route("/priority-queue", methods=["GET"])
@login_required
def get_priority_queue():
    """
    Patient priority queue widget ranked by clinician-assigned urgency
    (stat_emergency -> urgent -> routine).
    """
    user = g.current_user
    queue = db_service.get_priority_queue(user=user, limit=10)

    # Attach primary cardiologist name and latest condition
    for p in queue:
        cardio = db_service.get_user_by_id(p.get("primary_cardiologist_id"))
        p["primary_cardiologist_name"] = cardio["full_name"] if cardio else "On-Call CCU Team"
        histories = db_service.get_patient_cardiac_history(p["id"])
        p["latest_diagnosis"] = histories[0]["condition_type"] if histories else "Telemetry Monitoring"

    return jsonify({
        "status": "success",
        "count": len(queue),
        "data": queue
    }), 200


@dashboard_bp.route("/charts", methods=["GET"])
@login_required
def get_charts():
    """
    Time-series datasets for Chart.js:
    - New patients per month
    - Reports uploaded per week
    - Doctor review agreement distribution
    """
    charts_data = db_service.get_dashboard_charts()
    return jsonify({
        "status": "success",
        "data": charts_data
    }), 200


@dashboard_bp.route("/recent-uploads", methods=["GET"])
@login_required
def get_recent_uploads():
    """Recent ECG waveform uploads with urgency and status."""
    user = g.current_user
    reports = db_service.list_ecg_reports()

    # Sort by created_at desc
    reports_sorted = sorted(reports, key=lambda r: str(r.get("created_at", "")), reverse=True)[:10]

    for r in reports_sorted:
        p = db_service.get_patient_by_id(r.get("patient_id"))
        if p:
            r["patient_code"] = p.get("patient_code", "Unknown")
            r["patient_name"] = f"{p.get('first_name', '')} {p.get('last_name', '')}"
            r["room_bed"] = p.get("room_bed", "CCU")

        analysis = db_service.get_ecg_analysis(r.get("id"))
        if not analysis and r.get("file_type") == "digital_12lead":
            try:
                from backend.worker.worker import parse_csv_ecg_bytes
                from backend.services.storage_service import storage_service
                from backend.services.inference_service import inference_service
                file_tuple = storage_service.get_file_bytes(r.get("id"))
                if file_tuple:
                    file_bytes, _, _ = file_tuple
                    signal = parse_csv_ecg_bytes(file_bytes)
                    inference_service.run_inference_on_signal(
                        signal=signal,
                        sampling_rate=float(r.get("sampling_rate", 100.0)),
                        report_id=r.get("id")
                    )
                    db_service.update_ecg_report(r.get("id"), {"status": "analyzed"})
                    analysis = db_service.get_ecg_analysis(r.get("id"))
            except Exception:
                pass

        if analysis:
            r["scores"] = {
                "NORM": float(analysis.get("norm_score", 0.0)),
                "MI": float(analysis.get("mi_score", 0.0)),
                "STTC": float(analysis.get("sttc_score", 0.0)),
                "CD": float(analysis.get("cd_score", 0.0)),
                "HYP": float(analysis.get("hyp_score", 0.0))
            }
            r["model_version"] = analysis.get("model_version", "v1.0.0-ptbxl")
        elif r.get("preliminary_model_scores"):
            r["scores"] = r.get("preliminary_model_scores")

    return jsonify({
        "status": "success",
        "count": len(reports_sorted),
        "data": reports_sorted
    }), 200
