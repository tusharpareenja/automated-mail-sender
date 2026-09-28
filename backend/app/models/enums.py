import enum


class CampaignStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


class EmailStatus(str, enum.Enum):
    QUEUED = "QUEUED"
    GENERATING = "GENERATING"
    READY = "READY"
    SENDING = "SENDING"
    SENT = "SENT"
    FAILED = "FAILED"
    BOUNCED = "BOUNCED"
    SKIPPED = "SKIPPED"


class EventType(str, enum.Enum):
    SENT = "SENT"
    FAILED = "FAILED"
    OPENED = "OPENED"
    CLICKED = "CLICKED"
    BOUNCED = "BOUNCED"
    UNSUBSCRIBED = "UNSUBSCRIBED"
    COMPLAINED = "COMPLAINED"
    OPEN_REQUEST = "OPEN_REQUEST"
    IMAGE_LOADED = "IMAGE_LOADED"
    PDF_ACCESSED = "PDF_ACCESSED"
    DOWNLOAD_REQUESTED = "DOWNLOAD_REQUESTED"


class SignalClassification(str, enum.Enum):
    AUTOMATED = "automated"
    PROXY_OR_UNCERTAIN = "proxy_or_uncertain"
    POSSIBLE_HUMAN = "possible_human"


class AssetKind(str, enum.Enum):
    IMAGE = "image"
    PDF = "pdf"
    OTHER = "other"


class SMTPHealth(str, enum.Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNHEALTHY = "UNHEALTHY"


class ImportStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class SuppressionReason(str, enum.Enum):
    UNSUBSCRIBE = "UNSUBSCRIBE"
    BOUNCE = "BOUNCE"
    COMPLAINT = "COMPLAINT"
    MANUAL = "MANUAL"
    INVALID = "INVALID"
