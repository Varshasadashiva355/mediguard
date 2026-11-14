"""
MediGuard AI – Audit Service
Provides immutable audit logging across all clinical and administrative actions.
Requirement: log_action(user, action, entity_type, entity_id, ip, metadata=None)
"""
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Union

logger = logging.getLogger("mediguard.audit")

class AuditService:
    def __init__(self, db_service=None):
        self._db_service = db_service
        # In-memory storage for offline demo and test validation
        self._memory_logs = []

    def set_db_service(self, db_service):
        self._db_service = db_service

    def log_action(
        self,
        user: Optional[Union[Dict[str, Any], str]],
        action: str,
        entity_type: str,
        entity_id: Optional[str] = None,
        ip: Optional[str] = None,
        user_agent: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Record an immutable audit log entry.

        :param user: Dict representing current user or user ID string or None for anonymous actions (e.g. failed login)
        :param action: Action performed (e.g. 'LOGIN_SUCCESS', 'LOGIN_FAILURE', 'VIEW_PATIENT', 'SUBMIT_REVIEW')
        :param entity_type: Type of entity affected (e.g. 'USER', 'PATIENT', 'ECG_REPORT', 'DOCTOR_REVIEW')
        :param entity_id: Identifier of the affected entity
        :param ip: Client IP address
        :param user_agent: Client User-Agent string
        :param metadata: Additional contextual details (e.g. failure reason, parameters changed)
        :return: Created audit log record
        """
        user_id = None
        user_role = None

        if isinstance(user, dict):
            user_id = str(user.get("id")) if user.get("id") else None
            user_role = user.get("role")
        elif isinstance(user, str):
            user_id = user

        now_iso = datetime.now(timezone.utc).isoformat()
        log_entry = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "user_role": user_role,
            "action": action,
            "entity_type": entity_type,
            "entity_id": str(entity_id) if entity_id is not None else None,
            "ip_address": ip or "127.0.0.1",
            "user_agent": user_agent or "MediGuard Client",
            "metadata": metadata or {},
            "created_at": now_iso
        }

        # 1. Log structured to stdout/logger
        logger.info(
            "AUDIT LOG | action=%s entity=%s:%s user=%s role=%s ip=%s",
            action, entity_type, entity_id, user_id, user_role, ip
        )

        # 2. Store in memory for instant retrieval and tests
        self._memory_logs.append(log_entry)

        # 3. Store to Supabase DB if database service is configured and not in offline mode
        if self._db_service and hasattr(self._db_service, "insert_audit_log"):
            try:
                self._db_service.insert_audit_log(log_entry)
            except Exception as e:
                logger.error("Failed to write audit log to database: %s", str(e))

        return log_entry

    def get_logs(
        self,
        action: Optional[str] = None,
        entity_type: Optional[str] = None,
        user_id: Optional[str] = None,
        limit: int = 100
    ):
        """Retrieve audit logs with optional filtering."""
        if self._db_service and hasattr(self._db_service, "get_audit_logs"):
            try:
                db_logs = self._db_service.get_audit_logs(action=action, entity_type=entity_type, user_id=user_id, limit=limit)
                if db_logs:
                    return db_logs
            except Exception as e:
                logger.warning("Could not fetch audit logs from db: %s. Falling back to memory.", str(e))

        # Filter from memory
        results = list(reversed(self._memory_logs))
        if action:
            results = [log for log in results if log.get("action") == action]
        if entity_type:
            results = [log for log in results if log.get("entity_type") == entity_type]
        if user_id:
            results = [log for log in results if str(log.get("user_id")) == str(user_id)]
        return results[:limit]


# Global instance
audit_service = AuditService()

def log_action(user, action, entity_type, entity_id=None, ip=None, user_agent=None, metadata=None):
    """Module-level convenience helper."""
    return audit_service.log_action(
        user=user,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        ip=ip,
        user_agent=user_agent,
        metadata=metadata
    )
