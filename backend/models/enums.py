"""
MediGuard AI – Enums and Data Models
Defines system enumerations, role types, and validation structures.
"""
from enum import Enum

class UserRole(str, Enum):
    ADMIN = "admin"
    STAFF = "staff"
    CARDIOLOGIST = "cardiologist"

    @classmethod
    def all_roles(cls):
        return [cls.ADMIN.value, cls.STAFF.value, cls.CARDIOLOGIST.value]


class FileType(str, Enum):
    DIGITAL_12LEAD = "digital_12lead"
    IMAGE = "image"
    PDF = "pdf"
    DICOM_ECG = "dicom_ecg"


class ReportUrgency(str, Enum):
    ROUTINE = "routine"
    URGENT = "urgent"
    STAT_EMERGENCY = "stat_emergency"


class ReportStatus(str, Enum):
    PENDING = "pending"
    ANALYZED = "analyzed"
    REVIEWED = "reviewed"
    FLAGGED_URGENT = "flagged_urgent"


class AgreementWithModel(str, Enum):
    AGREED = "agreed"
    PARTIALLY_AGREED = "partially_agreed"
    DISAGREED = "disagreed"
    INCONCLUSIVE = "inconclusive"
    NOT_APPLICABLE = "not_applicable"


class NotificationSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


class FollowUpStatus(str, Enum):
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    MISSED = "missed"


class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
