"""
MediGuard AI – Auth Blueprint
Endpoints:
  POST /api/auth/login
  GET  /api/auth/me
  POST /api/auth/logout
"""
from flask import Blueprint, request, jsonify, g, current_app

from backend.services.auth_service import (
    AuthService,
    login_required,
    check_login_rate_limit,
    record_login_attempt
)
from backend.services.audit_service import log_action

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


@auth_bp.route("/login", methods=["POST"])
def login():
    """Authenticate clinical user and return JWT access token."""
    ip = request.remote_addr or "127.0.0.1"
    user_agent = request.headers.get("User-Agent", "Unknown")

    # Rate limiting check
    max_attempts = current_app.config.get("LOGIN_RATE_LIMIT_MAX", 10)
    window_secs = current_app.config.get("LOGIN_RATE_LIMIT_WINDOW_SECS", 60)
    if not check_login_rate_limit(ip, max_attempts=max_attempts, window_secs=window_secs):
        log_action(
            user=None,
            action="LOGIN_RATE_LIMITED",
            entity_type="AUTH",
            entity_id=ip,
            ip=ip,
            user_agent=user_agent,
            metadata={"attempts_exceeded": max_attempts}
        )
        return jsonify({
            "error": "Too Many Requests",
            "message": f"Too many failed login attempts. Please wait {window_secs} seconds before trying again.",
            "status_code": 429
        }), 429

    data = request.get_json(silent=True)
    if not data or not isinstance(data, dict):
        return jsonify({
            "error": "Bad Request",
            "message": "Invalid JSON body provided",
            "status_code": 400
        }), 400

    email = data.get("email", "").strip()
    password = data.get("password", "")

    if not email or not password:
        return jsonify({
            "error": "Bad Request",
            "message": "Both email and password are required fields",
            "status_code": 400
        }), 400

    # Record attempt for rate limiter
    record_login_attempt(ip)

    auth_result = AuthService.authenticate(
        email=email,
        password=password,
        ip=ip,
        user_agent=user_agent
    )

    if not auth_result.get("success"):
        return jsonify({
            "error": "Unauthorized",
            "message": auth_result.get("error", "Invalid credentials"),
            "status_code": 401
        }), 401

    return jsonify({
        "status": "success",
        "data": auth_result
    }), 200


@auth_bp.route("/me", methods=["GET"])
@login_required
def get_me():
    """Return profile and permissions for currently authenticated user."""
    user = g.current_user
    return jsonify({
        "status": "success",
        "data": {
            "id": user["id"],
            "email": user["email"],
            "full_name": user["full_name"],
            "role": user["role"],
            "department": user.get("department", "Cardiology"),
            "phone": user.get("phone", ""),
            "is_active": user.get("is_active", True),
            "permissions": {
                "can_write_doctor_reviews": user["role"] in ("cardiologist", "admin"),
                "can_manage_users": user["role"] == "admin",
                "can_upload_ecg": user["role"] in ("staff", "admin"),
                "can_manage_patients": user["role"] in ("staff", "admin"),
                "is_admin": user["role"] == "admin",
                "is_cardiologist": user["role"] == "cardiologist",
                "is_staff": user["role"] == "staff"
            }
        }
    }), 200


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    """Sign out the current user session and write audit log."""
    user = g.current_user
    ip = request.remote_addr or "127.0.0.1"
    user_agent = request.headers.get("User-Agent", "Unknown")

    log_action(
        user=user,
        action="LOGOUT",
        entity_type="AUTH",
        entity_id=str(user["id"]),
        ip=ip,
        user_agent=user_agent,
        metadata={"email": user.get("email")}
    )

    return jsonify({
        "status": "success",
        "message": "User successfully logged out."
    }), 200
