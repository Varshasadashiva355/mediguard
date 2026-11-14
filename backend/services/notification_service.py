"""
MediGuard AI – Notification Service
Handles in-app clinical alerts, deduplication with cooldown windows,
digest aggregation for low-priority notifications, and background scheduling.

NON-NEGOTIABLE SAFETY CONSTRAINTS:
1. 'emergency_flag' notifications are NEVER suppressed or delayed (bypasses deduplication/cooldown).
2. Emergency notifications dispatch immediately independent of any ML processing.
3. Deduplication via unique key: hash(type + entity_id + recipient_id) within cooldown window.
"""
import uuid
import logging
from datetime import datetime, timezone, timedelta, date
from typing import Dict, Any, List, Optional
from apscheduler.schedulers.background import BackgroundScheduler

from backend.services.db_service import db_service

logger = logging.getLogger("mediguard.notifications")

NOTIFICATION_TYPES = {
    "NEW_UPLOAD": "new_upload",
    "ANALYSIS_COMPLETE": "analysis_complete",
    "CONCERNING_FINDING": "concerning_finding_review",
    "FOLLOW_UP_DUE": "follow_up_due",
    "EMERGENCY_FLAG": "emergency_flag",
}

SEVERITY_LEVELS = {
    "INFO": "info",
    "WARNING": "warning",
    "CRITICAL": "critical",
}

DEFAULT_COOLDOWN_SECONDS = 300  # 5 minutes


class NotificationService:
    def __init__(self, cooldown_seconds: int = DEFAULT_COOLDOWN_SECONDS):
        self.cooldown_seconds = cooldown_seconds
        # In-memory tracking for deduplication: dedupe_key -> last_sent_datetime
        self._last_sent_timestamps: Dict[str, datetime] = {}
        # Low-priority digest buffer: recipient_id -> list of digest items
        self._digest_buffer: Dict[str, List[Dict[str, Any]]] = {}
        self.scheduler: Optional[BackgroundScheduler] = None

    def start_scheduler(self):
        """Start the background scheduler for recurring clinical alerts."""
        if self.scheduler is None:
            self.scheduler = BackgroundScheduler(daemon=True)
            # Run check every 6 hours or once daily
            self.scheduler.add_job(
                self.check_daily_overdue_followups,
                "interval",
                hours=12,
                id="daily_followup_check",
                replace_existing=True
            )
            try:
                self.scheduler.start()
                logger.info("Notification APScheduler started for daily follow-up checks.")
            except Exception as e:
                logger.warning(f"Could not start APScheduler: {e}")

    def stop_scheduler(self):
        if self.scheduler and self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    def _generate_dedupe_key(self, notif_type: str, entity_id: str, recipient_id: str) -> str:
        return f"{notif_type}:{str(entity_id)}:{str(recipient_id)}"

    def send_notification(
        self,
        recipient_id: str,
        notif_type: str,
        title: str,
        message: str,
        severity: str = "info",
        entity_type: str = "ecg_report",
        entity_id: str = "",
        deep_link: str = "",
        force_bypass_cooldown: bool = False
    ) -> Optional[Dict[str, Any]]:
        """
        Send a clinical notification with safety rules and deduplication.
        """
        now = datetime.now(timezone.utc)
        dedupe_key = self._generate_dedupe_key(notif_type, entity_id, recipient_id)

        # SAFETY RULE: emergency_flag is NEVER suppressed!
        is_emergency = (notif_type == NOTIFICATION_TYPES["EMERGENCY_FLAG"] or severity == SEVERITY_LEVELS["CRITICAL"])

        if not is_emergency and not force_bypass_cooldown:
            # Check user preference
            prefs = db_service.user_notification_prefs.get(str(recipient_id), {})
            if prefs.get(notif_type) is False:
                logger.info(f"Notification {notif_type} skipped per user preference for {recipient_id}")
                return None

            # Deduplication cooldown check
            last_sent = self._last_sent_timestamps.get(dedupe_key)
            if last_sent and (now - last_sent).total_seconds() < self.cooldown_seconds:
                logger.info(f"Duplicate notification suppressed by cooldown: {dedupe_key}")
                return None

        # Update last sent timestamp
        self._last_sent_timestamps[dedupe_key] = now

        record = {
            "id": str(uuid.uuid4()),
            "recipient_id": str(recipient_id),
            "type": notif_type,
            "title": title,
            "message": message,
            "severity": severity,
            "entity_type": entity_type,
            "entity_id": str(entity_id),
            "deep_link": deep_link,
            "is_read": False,
            "dedupe_key": dedupe_key,
            "created_at": now.isoformat()
        }

        created = db_service.add_notification(record)
        logger.info(f"Dispatched notification [{notif_type} | {severity}] to user {recipient_id}: {title}")
        return created

    def notify_cardiologists_for_patient(
        self,
        patient_id: str,
        notif_type: str,
        title: str,
        message: str,
        severity: str = "info",
        entity_type: str = "ecg_report",
        entity_id: str = "",
        deep_link: str = ""
    ) -> List[Dict[str, Any]]:
        """
        Notify assigned cardiologist or all cardiologists if unassigned.
        """
        patient = db_service.get_patient(patient_id)
        dispatched = []

        assigned_doctor = patient.get("assigned_doctor_id") if patient else None
        target_recipients = []

        if assigned_doctor and assigned_doctor in db_service.users:
            target_recipients.append(assigned_doctor)
        else:
            # Target all active cardiologists and admins
            for uid, user in db_service.users.items():
                if user.get("role") in ("cardiologist", "admin"):
                    target_recipients.append(uid)

        for doc_id in target_recipients:
            res = self.send_notification(
                recipient_id=doc_id,
                notif_type=notif_type,
                title=title,
                message=message,
                severity=severity,
                entity_type=entity_type,
                entity_id=entity_id,
                deep_link=deep_link
            )
            if res:
                dispatched.append(res)

        return dispatched

    def notify_emergency_symptom(
        self,
        patient_id: str,
        symptom: str,
        reported_by_name: str = "Clinical Staff",
        report_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        RULE 9: Critical symptom recorded. Immediate alert to cardiologists.
        NEVER waits for ML inference. Bypasses deduplication.
        """
        patient = db_service.get_patient(patient_id)
        pt_code = patient.get("patient_code", "UNKNOWN") if patient else "UNKNOWN"
        pt_name = f"{patient.get('first_name', '')} {patient.get('last_name', '')}" if patient else "Unknown Patient"
        room = patient.get("room_bed", "CCU") if patient else "CCU"

        title = f"EMERGENCY PROTOCOL: {symptom.replace('_', ' ').title()} Flagged ({pt_code})"
        message = (
            f"Staff {reported_by_name} recorded acute cardiac symptoms: '{symptom.replace('_', ' ').title()}' "
            f"for {pt_name} ({pt_code}, {room}). Activate emergency protocol immediately."
        )

        return self.notify_cardiologists_for_patient(
            patient_id=patient_id,
            notif_type=NOTIFICATION_TYPES["EMERGENCY_FLAG"],
            title=title,
            message=message,
            severity=SEVERITY_LEVELS["CRITICAL"],
            entity_type="patient",
            entity_id=patient_id,
            deep_link=f"dashboard.html?patient_id={patient_id}"
        )

    def check_daily_overdue_followups(self) -> int:
        """
        Scheduled check: scans follow-ups table and alerts cardiologists
        for all patients with overdue or due-today post-procedure visits.
        """
        today_str = date.today().isoformat()
        overdue_items = db_service.list_follow_ups(overdue_only=True)
        count = 0

        for f in overdue_items:
            patient_id = f.get("patient_id")
            patient = db_service.get_patient(patient_id) if patient_id else None
            pt_code = patient.get("patient_code", "PATIENT") if patient else "PATIENT"
            
            title = f"Follow-Up Overdue: {pt_code}"
            message = (
                f"Post-stent follow-up scheduled for {f.get('scheduled_date')} is overdue. "
                f"Please review clinical recovery notes and confirm appointment."
            )
            
            doctor_id = f.get("doctor_id")
            if not doctor_id and patient:
                doctor_id = patient.get("assigned_doctor_id")

            recipients = [doctor_id] if (doctor_id and doctor_id in db_service.users) else [
                uid for uid, u in db_service.users.items() if u.get("role") in ("cardiologist", "admin")
            ]

            for rec in recipients:
                created = self.send_notification(
                    recipient_id=rec,
                    notif_type=NOTIFICATION_TYPES["FOLLOW_UP_DUE"],
                    title=title,
                    message=message,
                    severity=SEVERITY_LEVELS["WARNING"],
                    entity_type="follow_up",
                    entity_id=f["id"],
                    deep_link=f"dashboard.html?patient_id={patient_id}"
                )
                if created:
                    count += 1

        return count


notification_service = NotificationService()
