"""
MediGuard AI – Audit Blueprint
Admin-only endpoint for querying regulatory and clinical access audit trails.
"""
from flask import Blueprint, request, jsonify

from backend.models.enums import UserRole
from backend.services.auth_service import roles_required
from backend.services.audit_service import audit_service

audit_bp = Blueprint("audit", __name__, url_prefix="/api/audit")


@audit_bp.route("/logs", methods=["GET"])
@roles_required(UserRole.ADMIN.value)
def list_logs():
    """Retrieve audit trail entries. Strictly restricted to Admin."""
    action = request.args.get("action")
    entity_type = request.args.get("entity_type")
    user_id = request.args.get("user_id")
    limit = int(request.args.get("limit", 100))

    logs = audit_service.get_logs(action=action, entity_type=entity_type, user_id=user_id, limit=limit)
    return jsonify({
        "status": "success",
        "count": len(logs),
        "data": logs
    }), 200
