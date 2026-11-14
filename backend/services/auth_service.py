"""
MediGuard AI – Authentication & Authorization Service
Handles Supabase Auth verification, JWT issuance/validation, role checks, and rate-limiting.
"""
import time
import logging
from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import Optional, Dict, Any, List

import jwt
from flask import request, jsonify, g, current_app

from backend.models.enums import UserRole
from backend.services.db_service import db_service
from backend.services.audit_service import log_action

logger = logging.getLogger("mediguard.auth")

# In-memory sliding window rate-limiter for login attempts
_login_rate_limit_cache: Dict[str, List[float]] = {}


def check_login_rate_limit(ip: str, max_attempts: int = 10, window_secs: int = 60) -> bool:
    """
    Check if IP has exceeded login attempt threshold within window.
    Returns True if allowed, False if rate-limited.
    """
    now = time.time()
    attempts = _login_rate_limit_cache.get(ip, [])
    # Keep attempts within the active sliding window
    attempts = [t for t in attempts if now - t < window_secs]
    _login_rate_limit_cache[ip] = attempts

    if len(attempts) >= max_attempts:
        return False
    return True


def record_login_attempt(ip: str):
    """Record an attempt timestamp for an IP."""
    now = time.time()
    if ip not in _login_rate_limit_cache:
        _login_rate_limit_cache[ip] = []
    _login_rate_limit_cache[ip].append(now)


def clear_login_attempts(ip: str):
    """Clear recorded attempts on successful authentication."""
    if ip in _login_rate_limit_cache:
        _login_rate_limit_cache.pop(ip, None)


class AuthService:
    @staticmethod
    def generate_token(user: Dict[str, Any], expires_hours: int = 12) -> str:
        """Issue signed JWT containing user identity and role."""
        secret = current_app.config.get("JWT_SECRET_KEY", "mediguard-jwt-secret-dev-key-784391208943")
        algorithm = current_app.config.get("JWT_ALGORITHM", "HS256")
        now = datetime.now(timezone.utc)
        payload = {
            "sub": str(user["id"]),
            "email": user["email"],
            "role": user["role"],
            "full_name": user.get("full_name", ""),
            "department": user.get("department", "Cardiology"),
            "iat": now,
            "exp": now + timedelta(hours=expires_hours),
            "iss": "mediguard-ai"
        }
        return jwt.encode(payload, secret, algorithm=algorithm)

    @staticmethod
    def verify_token(token: str) -> Optional[Dict[str, Any]]:
        """
        Decode and verify JWT.
        First tries internal JWT secret, then falls back to Supabase JWT secret if configured.
        """
        secret = current_app.config.get("JWT_SECRET_KEY", "mediguard-jwt-secret-dev-key-784391208943")
        supabase_jwt_secret = current_app.config.get("SUPABASE_JWT_SECRET", "")
        algorithm = current_app.config.get("JWT_ALGORITHM", "HS256")

        # 1. Attempt decode with application secret
        try:
            payload = jwt.decode(token, secret, algorithms=[algorithm])
            return payload
        except jwt.ExpiredSignatureError:
            logger.warning("Token expired")
            return None
        except jwt.InvalidTokenError:
            pass

        # 2. Attempt decode with Supabase JWT secret if available
        if supabase_jwt_secret:
            try:
                payload = jwt.decode(token, supabase_jwt_secret, algorithms=["HS256"], audience="authenticated")
                return payload
            except Exception as e:
                logger.debug("Supabase JWT verify failed: %s", str(e))

        return None

    @classmethod
    def authenticate(cls, email: str, password: str, ip: str, user_agent: str) -> Dict[str, Any]:
        """
        Authenticate user credentials, log audit trail, issue JWT.
        """
        clean_email = email.lower().strip()
        user = db_service.verify_credentials(clean_email, password)

        if not user:
            # Audit log failed login
            log_action(
                user=None,
                action="LOGIN_FAILURE",
                entity_type="AUTH",
                entity_id=clean_email,
                ip=ip,
                user_agent=user_agent,
                metadata={"reason": "Invalid credentials or inactive account"}
            )
            return {"success": False, "error": "Invalid email or password"}

        # Audit log successful login
        log_action(
            user=user,
            action="LOGIN_SUCCESS",
            entity_type="AUTH",
            entity_id=str(user["id"]),
            ip=ip,
            user_agent=user_agent,
            metadata={"role": user.get("role"), "department": user.get("department")}
        )

        clear_login_attempts(ip)
        token = cls.generate_token(user)
        return {
            "success": True,
            "access_token": token,
            "token_type": "Bearer",
            "expires_in": 12 * 3600,
            "user": {
                "id": user["id"],
                "email": user["email"],
                "full_name": user["full_name"],
                "role": user["role"],
                "department": user.get("department", "Cardiology"),
                "phone": user.get("phone", "")
            }
        }


def get_token_from_header() -> Optional[str]:
    """Extract Bearer token from Authorization request header."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:].strip()
    return None


def login_required(f):
    """Decorator ensuring that request has a valid, unexpired token."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = get_token_from_header()
        if not token:
            return jsonify({
                "error": "Unauthorized",
                "message": "Authorization header with Bearer token is missing",
                "status_code": 401
            }), 401

        payload = AuthService.verify_token(token)
        if not payload:
            return jsonify({
                "error": "Unauthorized",
                "message": "Invalid, malformed or expired authentication token",
                "status_code": 401
            }), 401

        user_id = payload.get("sub")
        user = db_service.get_user_by_id(user_id)
        if not user or not user.get("is_active", True):
            return jsonify({
                "error": "Unauthorized",
                "message": "User account is suspended, deactivated, or not found",
                "status_code": 401
            }), 401

        # Store authenticated user context in Flask `g`
        g.current_user = user
        g.token_payload = payload
        return f(*args, **kwargs)
    return decorated_function


def roles_required(*allowed_roles):
    """
    Decorator restricting endpoint access to specified clinical roles.
    Example: @roles_required('cardiologist', 'admin')
    """
    def decorator(f):
        @wraps(f)
        @login_required
        def decorated_function(*args, **kwargs):
            current_role = g.current_user.get("role")
            if current_role not in allowed_roles:
                # Log unauthorized RBAC access attempt
                log_action(
                    user=g.current_user,
                    action="RBAC_ACCESS_DENIED",
                    entity_type="ENDPOINT",
                    entity_id=request.path,
                    ip=request.remote_addr,
                    user_agent=request.headers.get("User-Agent"),
                    metadata={"user_role": current_role, "required_roles": list(allowed_roles)}
                )
                return jsonify({
                    "error": "Forbidden",
                    "message": f"Access denied. Role '{current_role}' is not authorized. Allowed: {list(allowed_roles)}",
                    "status_code": 403
                }), 403
            return f(*args, **kwargs)
        return decorated_function
    return decorator
