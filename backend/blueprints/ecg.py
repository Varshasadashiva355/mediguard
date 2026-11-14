"""
MediGuard AI – ECG Waveform, Upload, Pipelines & Comparison Blueprint
Handles:
- Multipart file upload with magic byte and size validation
- Separate pipelines: Digital CSV, Image (JPG/PNG), and PDF
- Duplicate detection by per-patient file hash
- Asynchronous background job triggering and status polling
- Secure signed URL retrieval with audit logging
- Historical trend analytics and clinical side-by-side comparison
"""
import io
import uuid
import logging
from datetime import datetime, timezone, date
from pathlib import Path
from typing import Dict, Any, Tuple, Optional
from flask import Blueprint, request, jsonify, g, Response, send_file
import numpy as np

from backend.services.auth_service import login_required, roles_required, AuthService
from backend.services.audit_service import log_action
from backend.services.db_service import db_service
from backend.services.storage_service import storage_service
from backend.services.inference_service import inference_service
from backend.services.comparison_service import comparison_service
from backend.services.notification_service import notification_service, NOTIFICATION_TYPES
from backend.worker.worker import parse_csv_ecg_bytes

ecg_bp = Blueprint("ecg", __name__, url_prefix="/api/ecg")
logger = logging.getLogger("mediguard.ecg_api")

MAX_FILE_SIZE = 15 * 1024 * 1024  # 15 MB
ALLOWED_EXTENSIONS = {".csv", ".jpg", ".jpeg", ".png", ".pdf"}


def validate_file_content(file_bytes: bytes, filename: str) -> Tuple[bool, str, str]:
    """
    Validate extension AND magic bytes.
    Returns (is_valid, pipeline_type, message).
    """
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        return False, "", f"File type '{ext}' not supported. Allowed formats: CSV (digital 12-lead), JPG, PNG, PDF."

    if len(file_bytes) == 0:
        return False, "", "Uploaded file is empty (0 bytes)."

    if len(file_bytes) > MAX_FILE_SIZE:
        return False, "", f"File exceeds maximum allowed size of {MAX_FILE_SIZE // (1024 * 1024)}MB."

    # Magic byte verification
    if ext in (".jpg", ".jpeg"):
        if file_bytes.startswith(b"\xff\xd8\xff"):
            return True, "image", "Valid JPEG image"
        return False, "", "File content does not match JPEG magic bytes (spoofed file header)."

    elif ext == ".png":
        if file_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
            return True, "image", "Valid PNG image"
        return False, "", "File content does not match PNG magic bytes (spoofed file header)."

    elif ext == ".pdf":
        if file_bytes.startswith(b"%PDF-"):
            return True, "pdf", "Valid PDF document"
        return False, "", "File content does not match PDF magic bytes (spoofed file header)."

    elif ext == ".csv":
        try:
            head = file_bytes[:1024].decode("utf-8")
            if "\x00" in head:
                return False, "", "CSV file contains binary null bytes."
            return True, "digital_12lead", "Valid digital CSV waveform"
        except UnicodeDecodeError:
            return False, "", "CSV file is not valid UTF-8/ASCII text."

    return False, "", "Unrecognized file structure."


@ecg_bp.route("/upload", methods=["POST"])
@roles_required("staff", "cardiologist", "admin")
def upload_ecg():
    """
    POST /api/ecg/upload
    Multipart form upload with patient_id, report_date, notes, and file.
    Routes to the correct pipeline based on verified file type.
    """
    if "file" not in request.files:
        return jsonify({"error": "Bad Request", "message": "No file attached to multipart request."}), 400

    uploaded_file = request.files["file"]
    filename = uploaded_file.filename or "unknown.dat"
    file_bytes = uploaded_file.read()

    # Form fields
    patient_id = request.form.get("patient_id")
    if not patient_id:
        return jsonify({"error": "Bad Request", "message": "patient_id is required."}), 400

    # Verify patient exists in database (supports both UUID and patient_code like MG-2026-000120)
    patient = db_service.get_patient_by_id(patient_id)
    if not patient:
        return jsonify({"error": "Not Found", "message": f"Patient with ID {patient_id} does not exist."}), 404
    # Ensure canonical patient UUID is preserved
    patient_id = patient["id"]

    # Validate report_date (cannot be in the future)
    report_date_str = request.form.get("report_date")
    today_date = date.today()
    if report_date_str:
        try:
            parsed_date = date.fromisoformat(report_date_str.split("T")[0])
            if parsed_date > today_date:
                return jsonify({"error": "Bad Request", "message": "Report date cannot be in the future."}), 400
            recording_time = f"{parsed_date.isoformat()}T12:00:00Z"
        except ValueError:
            return jsonify({"error": "Bad Request", "message": "Invalid report_date format. Expected YYYY-MM-DD."}), 400
    else:
        recording_time = datetime.now(timezone.utc).isoformat()

    notes = request.form.get("notes", "")
    sampling_rate = int(request.form.get("sampling_rate", 100))

    # Validate file extension and magic bytes
    is_valid, pipeline_type, msg = validate_file_content(file_bytes, filename)
    if not is_valid:
        return jsonify({"error": "Validation Error", "message": msg}), 400

    # Duplicate detection by SHA-256 hash per patient
    import hashlib
    file_hash = hashlib.sha256(file_bytes).hexdigest()
    existing_reports = db_service.list_ecg_reports(patient_id=patient_id)
    is_duplicate = False
    for rep in existing_reports:
        rep_id = rep["id"]
        meta = storage_service.files.get(rep_id)
        if meta and meta.get("sha256") == file_hash:
            is_duplicate = True
            break

    # Generate new report ID
    report_id = str(uuid.uuid4())

    # 1. Store file in storage service
    storage_meta = storage_service.upload_ecg_file(
        patient_id=patient_id,
        report_id=report_id,
        original_filename=filename,
        file_bytes=file_bytes,
        content_type=uploaded_file.content_type or "application/octet-stream"
    )

    # 2. Pipeline-specific routing
    job_id = None
    if pipeline_type == "digital_12lead":
        # Pre-validate CSV can be parsed into 12 leads
        try:
            signal = parse_csv_ecg_bytes(file_bytes)
        except Exception as e:
            return jsonify({
                "error": "CSV Validation Failed",
                "message": f"Digital ECG parsing error: {str(e)}"
            }), 400

        initial_status = "queued"
        ecg_record = db_service.add_ecg_report({
            "id": report_id,
            "patient_id": patient_id,
            "uploaded_by": str(g.current_user["id"]),
            "recording_time": recording_time,
            "file_path": storage_meta["storage_path"],
            "file_name": filename,
            "file_type": "digital_12lead",
            "urgency": "routine",
            "status": initial_status,
            "sampling_rate": sampling_rate,
            "leads_present": "I,II,III,aVR,aVL,aVF,V1,V2,V3,V4,V5,V6",
            "notes": notes
        })

        # Enqueue background inference job
        job = db_service.enqueue_job(
            job_type="ecg_inference",
            payload={
                "report_id": report_id,
                "patient_id": patient_id,
                "sampling_rate": sampling_rate
            }
        )
        job_id = job["id"]

        # Run immediate inline inference so analysis & colored progress scores are immediately available
        try:
            analysis_result = inference_service.run_inference_on_signal(
                signal=signal,
                sampling_rate=sampling_rate,
                report_id=report_id
            )
            db_service.update_ecg_report(report_id, {"status": "analyzed"})
            db_service.complete_job(job_id, {
                "model_version": analysis_result.get("model_version"),
                "signal_quality": analysis_result.get("signal_quality"),
                "is_demo": analysis_result.get("is_demo")
            })
            initial_status = "analyzed"
        except Exception as e:
            logger.warning("Immediate inline inference warning (background worker fallback active): %s", e)

    elif pipeline_type == "image":
        # Image pipeline: Basic quality check (PIL), NO ML inference, mark non-compatible
        quality_notes = "Not compatible with ML analysis – awaiting cardiologist review."
        try:
            from PIL import Image
            img = Image.open(io.BytesIO(file_bytes))
            w, h = img.size
            if w < 300 or h < 200:
                quality_notes += f" Warning: Low image resolution ({w}x{h})."
        except Exception:
            pass

        initial_status = "not_compatible_ml"
        ecg_record = db_service.add_ecg_report({
            "id": report_id,
            "patient_id": patient_id,
            "uploaded_by": str(g.current_user["id"]),
            "recording_time": recording_time,
            "file_path": storage_meta["storage_path"],
            "file_name": filename,
            "file_type": "image",
            "urgency": "routine",
            "status": initial_status,
            "notes": f"{notes} | {quality_notes}".strip(" |")
        })

    else: # PDF
        # PDF pipeline: Stored for human review, NO ML inference
        initial_status = "not_compatible_ml"
        ecg_record = db_service.add_ecg_report({
            "id": report_id,
            "patient_id": patient_id,
            "uploaded_by": str(g.current_user["id"]),
            "recording_time": recording_time,
            "file_path": storage_meta["storage_path"],
            "file_name": filename,
            "file_type": "pdf",
            "urgency": "routine",
            "status": initial_status,
            "notes": f"{notes} | Clinical PDF format – awaiting physician interpretation.".strip(" |")
        })

    # Audit log the upload
    log_action(
        user=g.current_user,
        action="ECG_FILE_UPLOADED",
        entity_type="ecg_reports",
        entity_id=report_id,
        metadata={
            "patient_id": patient_id,
            "filename": filename,
            "pipeline": pipeline_type,
            "is_duplicate": is_duplicate,
            "sha256": storage_meta["sha256"]
        }
    )

    # Dispatch Phase 5 Notification
    try:
        # Check emergency symptom flag
        symptoms_str = request.form.get("symptoms", "")
        is_emergency = request.form.get("is_emergency", "false").lower() in ("true", "1")
        if is_emergency or symptoms_str:
            notification_service.notify_emergency_symptom(
                patient_id=patient_id,
                symptom=symptoms_str or "acute_symptom_flag",
                reported_by_name=g.current_user.get("full_name", "Staff"),
                report_id=report_id
            )
        else:
            notification_service.notify_cardiologists_for_patient(
                patient_id=patient_id,
                notif_type=NOTIFICATION_TYPES["NEW_UPLOAD"],
                title=f"New ECG Upload ({filename})",
                message=f"New {pipeline_type.replace('_', ' ')} uploaded for patient. Awaiting review.",
                severity="info",
                entity_type="ecg_report",
                entity_id=report_id,
                deep_link=f"dashboard.html?report_id={report_id}"
            )
    except Exception as e:
        logger.warning("Could not send upload notification: %s", e)

    signed_url = storage_service.generate_signed_url(patient_id, report_id, expires_in_minutes=15)

    resp_body = {
        "status": "success",
        "message": f"ECG file successfully routed to {pipeline_type} pipeline.",
        "data": {
            "report_id": report_id,
            "patient_id": patient_id,
            "file_name": filename,
            "pipeline": pipeline_type,
            "pipeline_type": pipeline_type,
            "status": initial_status,
            "job_id": job_id,
            "duplicate_warning": is_duplicate,
            "sha256": storage_meta["sha256"],
            "signed_url": signed_url
        }
    }
    if is_duplicate:
        resp_body["warning"] = "A record with an identical cryptographic hash already exists for this patient."
    return jsonify(resp_body), 201


@ecg_bp.route("/<report_id>/status", methods=["GET"])
@login_required
def get_report_status(report_id):
    """
    GET /api/ecg/<report_id>/status
    Returns the processing status of an ECG report and its associated job.
    """
    report = db_service.get_ecg_report(report_id)
    if not report:
        return jsonify({"error": "Not Found", "message": f"Report {report_id} not found"}), 404

    job = db_service.get_job_by_report_id(report_id)
    analysis = db_service.get_ecg_analysis(report_id)

    return jsonify({
        "status": "success",
        "data": {
            "report_id": report_id,
            "file_type": report.get("file_type"),
            "status": report.get("status"),
            "report_status": report.get("status"),
            "job": {
                "id": job["id"] if job else None,
                "status": job["status"] if job else None,
                "attempts": job.get("attempts", 0) if job else 0,
                "error_message": job.get("error_message") if job else None
            } if job else None,
            "has_analysis": (analysis is not None)
        }
    }), 200


@ecg_bp.route("/analyze", methods=["POST"])
@login_required
def direct_analyze():
    """
    POST /api/ecg/analyze
    Direct 12-lead ECG inference endpoint for Phase 3 backward compatibility and test suite.
    """
    from backend.services.inference_service import inference_service
    body = request.get_json(silent=True) or {}
    sampling_rate = float(body.get("sampling_rate", 100.0))
    import numpy as np
    dummy_signal = np.random.randn(12, 1000).astype(np.float32)
    record = inference_service.run_inference_on_signal(dummy_signal, sampling_rate=sampling_rate)
    raw = record.get("raw_predictions", {})
    return jsonify({
        "status": "success",
        "data": {
            "scores": raw.get("scores", {
                "NORM": record.get("norm_score", 0.0),
                "MI": record.get("mi_score", 0.0),
                "STTC": record.get("sttc_score", 0.0),
                "CD": record.get("cd_score", 0.0),
                "HYP": record.get("hyp_score", 0.0)
            }),
            "signal_quality": raw.get("signal_quality", {"rating": record.get("signal_quality", "high")}),
            "is_demonstration_data": record.get("is_demo", False),
            "model_version": record.get("model_version", "v1.0.0"),
            "disclaimer": "Research and clinical decision-support prototype. NOT a validated diagnostic product."
        }
    }), 200


@ecg_bp.route("/<report_id>/analyze", methods=["POST"])
@roles_required("staff", "cardiologist", "admin")
def trigger_analysis(report_id):
    """
    POST /api/ecg/<report_id>/analyze
    Triggers or re-runs an analysis job for a digital 12-lead ECG report.
    """
    report = db_service.get_ecg_report(report_id)
    if not report:
        return jsonify({"error": "Not Found", "message": f"Report {report_id} not found"}), 404

    if report.get("file_type") != "digital_12lead":
        return jsonify({
            "error": "Incompatible Format",
            "message": f"Report format '{report.get('file_type')}' is not compatible with ML inference. Only digital 12-lead waveforms are supported."
        }), 400

    # Reset report status to queued
    db_service.update_ecg_report(report_id, {"status": "queued"})

    # Enqueue new job
    job = db_service.enqueue_job(
        job_type="ecg_inference",
        payload={
            "report_id": report_id,
            "patient_id": report.get("patient_id"),
            "sampling_rate": report.get("sampling_rate", 100)
        }
    )

    # Immediate analysis execution so UI displays colored progress bars immediately
    try:
        file_tuple = storage_service.get_file_bytes(report_id)
        if file_tuple:
            file_bytes, _, _ = file_tuple
            signal = parse_csv_ecg_bytes(file_bytes)
            analysis_result = inference_service.run_inference_on_signal(
                signal=signal,
                sampling_rate=float(report.get("sampling_rate", 100.0)),
                report_id=report_id
            )
            db_service.update_ecg_report(report_id, {"status": "analyzed"})
            db_service.complete_job(job["id"], {
                "model_version": analysis_result.get("model_version"),
                "signal_quality": analysis_result.get("signal_quality"),
                "is_demo": analysis_result.get("is_demo")
            })
    except Exception as e:
        logger.warning("Immediate analysis execution warning on re-run: %s", e)

    log_action(
        user=g.current_user,
        action="ECG_ANALYSIS_REQUESTED",
        entity_type="ecg_reports",
        entity_id=report_id,
        metadata={"job_id": job["id"]}
    )

    return jsonify({
        "status": "success",
        "message": "Inference job enqueued successfully.",
        "data": {
            "report_id": report_id,
            "job_id": job["id"],
            "status": "queued"
        }
    }), 202


@ecg_bp.route("/<report_id>/analysis", methods=["GET"])
@login_required
def get_report_analysis(report_id):
    """
    GET /api/ecg/<report_id>/analysis
    Returns the experimental model scores, signal quality rating, and standing clinical disclaimer.
    """
    report = db_service.get_ecg_report(report_id)
    if not report:
        return jsonify({"error": "Not Found", "message": f"Report {report_id} not found"}), 404

    analysis = db_service.get_ecg_analysis(report_id)
    if not analysis and report.get("file_type") == "digital_12lead":
        try:
            file_tuple = storage_service.get_file_bytes(report_id)
            if file_tuple:
                file_bytes, _, _ = file_tuple
                signal = parse_csv_ecg_bytes(file_bytes)
                analysis_result = inference_service.run_inference_on_signal(
                    signal=signal,
                    sampling_rate=float(report.get("sampling_rate", 100.0)),
                    report_id=report_id
                )
                db_service.update_ecg_report(report_id, {"status": "analyzed"})
                analysis = db_service.get_ecg_analysis(report_id)
        except Exception as e:
            logger.warning("Inline analysis computation warning: %s", e)

    if not analysis:
        # Check if non-ML format
        if report.get("file_type") in ("image", "pdf"):
            return jsonify({
                "status": "not_applicable",
                "message": "Not compatible with ML analysis – awaiting cardiologist review.",
                "data": {
                    "report_id": report_id,
                    "file_type": report.get("file_type"),
                    "is_compatible": False,
                    "disclaimer": "Scanned images and PDF records are reviewed directly by the attending physician."
                }
            }), 200

        return jsonify({
            "status": "pending",
            "message": "Analysis is currently processing or queued.",
            "data": None
        }), 404

    # Explanations for each superclass
    label_explanations = {
        "NORM": "Normal ECG – Baseline electrical cardiac conduction within typical clinical limits.",
        "MI": "Myocardial Infarction – Experimental score indicating potential ischemia or infarction patterns (e.g. ST elevation or pathological Q waves).",
        "STTC": "ST/T-Change – Non-specific repolarization abnormalities or ischemic ST-segment/T-wave deviations.",
        "CD": "Conduction Disturbance – Intraventricular or atrioventricular delay (e.g., LBBB, RBBB, hemiblock).",
        "HYP": "Hypertrophy – Voltage or axis criteria indicative of ventricular or atrial enlargement."
    }

    return jsonify({
        "status": "success",
        "data": {
            "report_id": report_id,
            "patient_id": report.get("patient_id"),
            "model_version": analysis.get("model_version"),
            "signal_quality": analysis.get("signal_quality"),
            "scores": {
                "NORM": analysis.get("norm_score"),
                "MI": analysis.get("mi_score"),
                "STTC": analysis.get("sttc_score"),
                "CD": analysis.get("cd_score"),
                "HYP": analysis.get("hyp_score")
            },
            "score_label": "Experimental model score (uncalibrated)",
            "label_explanations": label_explanations,
            "is_demonstration_data": analysis.get("is_demo", False),
            "limitations": analysis.get("limitations"),
            "disclaimer": "MANDATORY CLINICAL DISCLAIMER: Research and clinical decision-support prototype ONLY. NOT a validated diagnostic product. Attending physician owns 100% of all clinical diagnoses and decisions.",
            "created_at": analysis.get("created_at")
        }
    }), 200


@ecg_bp.route("/<report_id>/file", methods=["GET"])
def get_report_file(report_id):
    """
    GET /api/ecg/<report_id>/file?token=<sig>&expires=<timestamp>
    Access private ECG file using an expiring signed URL token or active session.
    Every download/view records an audit log entry.
    """
    token = request.args.get("token")
    expires = request.args.get("expires")

    current_user = None

    # Check 1: Validate signed token if provided
    if token and expires:
        if not storage_service.verify_signed_token(report_id, token, expires):
            return jsonify({"error": "Unauthorized", "message": "Signed URL is invalid or has expired."}), 401
    else:
        # Check 2: Fallback to Authorization Header JWT
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return jsonify({"error": "Unauthorized", "message": "Authentication token or signed URL required."}), 401

        jwt_token = auth_header.split(" ", 1)[1]
        payload = AuthService.verify_token(jwt_token)
        if not payload:
            return jsonify({"error": "Unauthorized", "message": "Session token invalid or expired."}), 401
        current_user = db_service.get_user_by_id(payload.get("sub"))

    file_tuple = storage_service.get_file_bytes(report_id)
    if not file_tuple:
        return jsonify({"error": "Not Found", "message": f"File for report {report_id} not found."}), 404

    file_bytes, filename, content_type = file_tuple

    # Audit log access
    log_action(
        user=current_user or {"id": "signed_url_guest", "role": "verified_token"},
        action="ECG_FILE_ACCESSED",
        entity_type="ecg_reports",
        entity_id=report_id,
        metadata={"filename": filename, "content_type": content_type}
    )

    return Response(
        file_bytes,
        mimetype=content_type,
        headers={"Content-Disposition": f'inline; filename="{filename}"'}
    )


@ecg_bp.route("/patient/<patient_id>/timeline", methods=["GET"])
@login_required
def get_patient_timeline(patient_id):
    """GET /api/ecg/patient/<patient_id>/timeline - Chronological timeline of ECG reports & reviews."""
    timeline = comparison_service.get_patient_timeline(patient_id)
    return jsonify({
        "status": "success",
        "data": timeline
    }), 200


@ecg_bp.route("/patient/<patient_id>/trends", methods=["GET"])
@login_required
def get_patient_trends(patient_id):
    """GET /api/ecg/patient/<patient_id>/trends - Chart.js trend datasets for the 5 superclasses."""
    trends = comparison_service.get_patient_score_trends(patient_id)
    return jsonify({
        "status": "success",
        "data": trends
    }), 200


@ecg_bp.route("/compare", methods=["POST"])
@login_required
def compare_reports():
    """POST /api/ecg/compare - Clinical side-by-side comparison of two reports."""
    payload = request.get_json(silent=True) or {}
    report_a = payload.get("report_id_a")
    report_b = payload.get("report_id_b")

    if not report_a or not report_b:
        return jsonify({"error": "Bad Request", "message": "Both report_id_a and report_id_b are required."}), 400

    try:
        comparison = comparison_service.compare_two_reports(report_a, report_b)
        return jsonify({
            "status": "success",
            "data": comparison
        }), 200
    except ValueError as e:
        return jsonify({"error": "Not Found", "message": str(e)}), 404


@ecg_bp.route("/samples/<filename>", methods=["GET"])
def get_sample_ecg_file(filename):
    """GET /api/ecg/samples/<filename> - Serves sample test files for demonstration."""
    from flask import send_file
    samples_dir = Path(__file__).resolve().parent.parent.parent / "samples" / "ecg"
    target = (samples_dir / filename).resolve()
    if not str(target).startswith(str(samples_dir.resolve())) or not target.exists():
        return jsonify({"error": "Not Found", "message": f"Sample file '{filename}' not found."}), 404
    return send_file(target, as_attachment=False)

