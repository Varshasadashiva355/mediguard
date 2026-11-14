"""
MediGuard AI – Flask Application Factory
Intelligent Cardiac Monitoring. Smarter Clinical Decisions.
"""
import os
from pathlib import Path
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

from backend.config import Config
from backend.services.db_service import db_service
from backend.services.audit_service import audit_service


def create_app(config_class=Config):
    """Factory function for creating and configuring the Flask application."""
    frontend_dir = Path(__file__).resolve().parent.parent / "frontend"

    app = Flask(
        __name__,
        static_folder=str(frontend_dir),
        static_url_path=""
    )
    app.config.from_object(config_class)

    # Initialize DB & audit services
    db_service.config = app.config
    if not app.config.get("OFFLINE_DEMO_MODE", True):
        db_service._init_supabase(app.config)
    audit_service.set_db_service(db_service)

    # 1. CORS Configuration
    CORS(
        app,
        resources={r"/*": {"origins": "*"}},
        allow_headers=["Content-Type", "Authorization", "X-Requested-With"],
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
    )

    # 2. Security Headers Middleware
    @app.after_request
    def set_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data: https:; "
            "connect-src 'self' http://localhost:* http://127.0.0.1:* https://*.supabase.co;"
        )
        return response

    # 3. Register Blueprints
    from backend.blueprints.auth import auth_bp
    from backend.blueprints.reviews import reviews_bp
    from backend.blueprints.audit import audit_bp
    from backend.blueprints.patients import patients_bp
    from backend.blueprints.dashboard import dashboard_bp
    from backend.blueprints.ecg import ecg_bp
    from backend.blueprints.notifications import notifications_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(reviews_bp)
    app.register_blueprint(audit_bp)
    app.register_blueprint(patients_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(ecg_bp)
    app.register_blueprint(notifications_bp)

    # Initialize Notification Scheduler
    from backend.services.notification_service import notification_service
    notification_service.start_scheduler()

    # 4. Standard Health Check Endpoint
    @app.route("/health", methods=["GET"])
    @app.route("/api/health", methods=["GET"])
    def health_check():
        db_status = "connected" if not db_service.is_offline else "offline_in_memory"
        show_details = request.args.get("details", "false").lower() in ("true", "1")
        
        response_data = {
            "status": "healthy",
            "database": {
                "status": db_status,
                "users_count": len(db_service.users),
                "patients_count": len(db_service.patients),
                "ecg_reports_count": len(db_service.ecg_reports),
                "doctor_reviews_count": len(db_service.doctor_reviews),
                "follow_ups_count": len(db_service.follow_ups)
            },
            "service": "MediGuard AI Cardiology Decision Support",
            "offline_mode": app.config.get("OFFLINE_DEMO_MODE", True),
            "disclaimer": "Research and clinical decision-support prototype. NOT a validated diagnostic product."
        }
        
        if show_details:
            response_data["users"] = [
                {"email": u.get("email"), "full_name": u.get("full_name"), "role": u.get("role")}
                for u in db_service.users.values()
            ]
            response_data["sample_patients"] = [
                {
                    "patient_code": p.get("patient_code"),
                    "name": f"{p.get('first_name')} {p.get('last_name')}",
                    "room_bed": p.get("room_bed"),
                    "urgency": p.get("urgency")
                }
                for p in list(db_service.patients.values())[:10]
            ]
            
        return jsonify(response_data), 200

    # 5. Static Web UI Routes
    @app.route("/")
    def index():
        return send_from_directory(str(frontend_dir), "index.html")

    @app.route("/<path:path>")
    def static_proxy(path):
        file_path = frontend_dir / path
        if file_path.exists():
            return send_from_directory(str(frontend_dir), path)
        return send_from_directory(str(frontend_dir), "index.html")

    # 6. Centralized JSON Error Handlers
    @app.errorhandler(400)
    def handle_bad_request(e):
        return jsonify({
            "error": "Bad Request",
            "message": str(e.description) if hasattr(e, "description") else "Bad request syntax or invalid parameters",
            "status_code": 400
        }), 400

    @app.errorhandler(401)
    def handle_unauthorized(e):
        return jsonify({
            "error": "Unauthorized",
            "message": str(e.description) if hasattr(e, "description") else "Authentication credentials required",
            "status_code": 401
        }), 401

    @app.errorhandler(403)
    def handle_forbidden(e):
        return jsonify({
            "error": "Forbidden",
            "message": str(e.description) if hasattr(e, "description") else "You do not have permission to access this resource",
            "status_code": 403
        }), 403

    @app.errorhandler(404)
    def handle_not_found(e):
        return jsonify({
            "error": "Not Found",
            "message": "The requested API resource or endpoint was not found",
            "status_code": 404
        }), 404

    @app.errorhandler(405)
    def handle_method_not_allowed(e):
        return jsonify({
            "error": "Method Not Allowed",
            "message": f"Method {request.method} is not supported on this endpoint",
            "status_code": 405
        }), 405

    @app.errorhandler(429)
    def handle_too_many_requests(e):
        return jsonify({
            "error": "Too Many Requests",
            "message": "Rate limit exceeded. Please back off before retrying.",
            "status_code": 429
        }), 429

    @app.errorhandler(500)
    def handle_internal_server_error(e):
        return jsonify({
            "error": "Internal Server Error",
            "message": "An unexpected server error occurred. Clinical audit log entry dispatched.",
            "status_code": 500
        }), 500

    return app


if __name__ == "__main__":
    app = create_app()
    # Import seed data on startup if database is empty
    from backend.db.seed import seed_all
    seed_all()
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
