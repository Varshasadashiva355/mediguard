"""
Tests for MediGuard AI – Notification System
Validates:
- Creation, retrieval, and unread counts
- Deduplication and cooldown window suppression
- CRITICAL SAFETY RULE: emergency_flag is NEVER suppressed
- Daily overdue follow-up check triggers notifications
"""
import pytest
from datetime import datetime, timezone, timedelta
from backend.services.notification_service import notification_service, NOTIFICATION_TYPES, SEVERITY_LEVELS
from backend.services.db_service import db_service


@pytest.fixture(autouse=True)
def setup_teardown():
    db_service.reset_all_data()
    notification_service._last_sent_timestamps.clear()
    
    # Add test user
    db_service.add_user({
        "id": "11111111-1111-1111-1111-111111111111",
        "email": "cardio@mediguard.local",
        "full_name": "Dr. Test Cardio",
        "role": "cardiologist"
    })
    yield
    db_service.reset_all_data()


def test_notification_creation_and_unread_count():
    """Verify notification delivery and unread count tracking."""
    recipient = "11111111-1111-1111-1111-111111111111"
    notif = notification_service.send_notification(
        recipient_id=recipient,
        notif_type=NOTIFICATION_TYPES["NEW_UPLOAD"],
        title="New ECG Upload",
        message="Patient 12-lead ECG uploaded.",
        severity=SEVERITY_LEVELS["INFO"],
        entity_id="report-123"
    )
    assert notif is not None
    assert notif["is_read"] is False
    assert db_service.get_unread_notification_count(recipient) == 1

    # Mark as read
    updated = db_service.mark_notification_read(notif["id"], recipient)
    assert updated["is_read"] is True
    assert db_service.get_unread_notification_count(recipient) == 0


def test_notification_deduplication_cooldown():
    """Verify duplicate non-critical notifications within cooldown window are suppressed."""
    recipient = "11111111-1111-1111-1111-111111111111"
    
    # First notification should succeed
    n1 = notification_service.send_notification(
        recipient_id=recipient,
        notif_type=NOTIFICATION_TYPES["NEW_UPLOAD"],
        title="Upload 1",
        message="Waveform received",
        entity_id="rep-duplicate"
    )
    assert n1 is not None

    # Immediate second identical notification should be suppressed by cooldown
    n2 = notification_service.send_notification(
        recipient_id=recipient,
        notif_type=NOTIFICATION_TYPES["NEW_UPLOAD"],
        title="Upload 2",
        message="Waveform received again",
        entity_id="rep-duplicate"
    )
    assert n2 is None, "Duplicate non-critical notification was not suppressed by cooldown!"


def test_emergency_flag_never_suppressed():
    """
    CRITICAL SAFETY ACCEPTANCE CHECK:
    emergency_flag notifications must NEVER be suppressed by deduplication or cooldown!
    """
    recipient = "11111111-1111-1111-1111-111111111111"
    
    # Send emergency notification 1
    e1 = notification_service.send_notification(
        recipient_id=recipient,
        notif_type=NOTIFICATION_TYPES["EMERGENCY_FLAG"],
        title="Emergency Protocol Active",
        message="Acute chest pain reported",
        severity=SEVERITY_LEVELS["CRITICAL"],
        entity_id="emergency-patient-1"
    )
    assert e1 is not None

    # Immediate emergency notification 2 with same key MUST NOT be suppressed
    e2 = notification_service.send_notification(
        recipient_id=recipient,
        notif_type=NOTIFICATION_TYPES["EMERGENCY_FLAG"],
        title="Emergency Protocol Active Again",
        message="Syncope episode",
        severity=SEVERITY_LEVELS["CRITICAL"],
        entity_id="emergency-patient-1"
    )
    assert e2 is not None, "Violation of Rule 9: Emergency notification was suppressed by cooldown!"


def test_daily_overdue_followup_alerts():
    """Verify automated follow-up check detects overdue visits and alerts doctors."""
    doctor_id = "11111111-1111-1111-1111-111111111111"
    pt = db_service.add_patient({
        "first_name": "John",
        "last_name": "Overdue",
        "dob": "1970-01-01",
        "gender": "male",
        "patient_code": "MG-OVERDUE",
        "assigned_doctor_id": doctor_id
    })
    
    # Add an overdue follow up (yesterday)
    yesterday = (datetime.now(timezone.utc) - timedelta(days=2)).date().isoformat()
    db_service.add_follow_up({
        "patient_id": pt["id"],
        "doctor_id": doctor_id,
        "scheduled_date": yesterday,
        "status": "scheduled"
    })

    generated_count = notification_service.check_daily_overdue_followups()
    assert generated_count >= 1

    notifs = db_service.list_notifications(doctor_id)
    assert any(n["type"] == NOTIFICATION_TYPES["FOLLOW_UP_DUE"] for n in notifs)
