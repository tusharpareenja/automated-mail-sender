from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import ORMModel


class CampaignCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    template_id: UUID
    lead_ids: list[UUID] = Field(default_factory=list)
    group_ids: list[UUID] = Field(default_factory=list)
    countries: list[str] = Field(default_factory=list)
    study_opportunities: list[str] = Field(default_factory=list)
    role_verified_only: bool = False
    work_email_only: bool = False
    max_recipients: int = Field(default=150, ge=1, le=200)
    smtp_account_ids: list[UUID] = Field(min_length=1)
    ai_enabled: bool = True
    ai_instructions: str | None = None
    hourly_limit: int = Field(default=40, ge=1, le=100000)
    daily_limit: int = Field(default=300, ge=1, le=1000000)
    delay_seconds: int = Field(default=8, ge=0, le=3600)
    scheduled_at: datetime | None = None

    @model_validator(mode="after")
    def require_audience(self):
        if not self.lead_ids and not self.group_ids:
            raise ValueError("Select at least one lead group")
        return self


class CampaignUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    template_id: UUID | None = None
    lead_ids: list[UUID] | None = None
    group_ids: list[UUID] | None = None
    smtp_account_ids: list[UUID] | None = None
    ai_enabled: bool | None = None
    ai_instructions: str | None = None
    hourly_limit: int | None = Field(default=None, ge=1, le=100000)
    daily_limit: int | None = Field(default=None, ge=1, le=1000000)
    delay_seconds: int | None = Field(default=None, ge=0, le=3600)
    scheduled_at: datetime | None = None


class CampaignTestEmail(BaseModel):
    to_email: str
    lead_id: UUID | None = None


class CampaignOut(ORMModel):
    id: UUID
    name: str
    template_id: UUID | None
    status: str
    ai_enabled: bool
    ai_instructions: str | None
    hourly_limit: int
    daily_limit: int
    delay_seconds: int
    scheduled_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    total_count: int
    queued_count: int
    sent_count: int
    failed_count: int
    bounced_count: int
    open_count: int
    click_count: int
    unsubscribe_count: int
    failure_reason: str | None
    created_at: datetime
    updated_at: datetime


class TrackedLinkOut(BaseModel):
    destination_url: str
    click_count: int
    clicked: bool
    asset_id: UUID | None = None


class TrackingRequestOut(BaseModel):
    id: UUID
    request_type: str
    classification: str
    confidence: float
    classification_reasons: list[str]
    seconds_after_send: float | None
    user_agent: str | None
    created_at: datetime
    asset_id: UUID | None = None
    filename: str | None = None


class AssetActivityOut(BaseModel):
    asset_id: UUID
    filename: str
    kind: str
    access_count: int
    download_count: int
    image_loads: int = 0
    pdf_accesses: int = 0
    downloads: int = 0


class CampaignEmailOut(ORMModel):
    id: UUID
    campaign_id: UUID
    lead_id: UUID
    recipient_email: str
    status: str
    subject: str
    error_message: str | None
    sent_at: datetime | None
    created_at: datetime
    opened: bool = False
    opened_at: datetime | None = None
    latest_open_at: datetime | None = None
    open_classification: str = "none"
    open_request_count: int = 0
    open_confidence: float | None = None
    open_reasons: list[str] = []
    clicked: bool = False
    click_count: int = 0
    links: list[TrackedLinkOut] = []
    assets: list[AssetActivityOut] = []
    requests: list[TrackingRequestOut] = []


class CampaignPreviewOut(BaseModel):
    lead_id: UUID
    email: str
    subject: str
    html_body: str
    text_body: str
    personalization: dict


class TimelineEventOut(BaseModel):
    id: UUID
    email_id: UUID
    recipient_email: str | None = None
    event_type: str
    classification: str | None = None
    confidence: float | None = None
    classification_reasons: list[str] = []
    created_at: datetime
    metadata_json: dict = {}
    filename: str | None = None


class AnalyticsOut(BaseModel):
    campaign: CampaignOut
    sent: int
    queued: int
    failed: int
    bounced: int
    tracked_opens: int
    open_requests: int
    automated_opens: int
    uncertain_opens: int
    possible_human_opens: int
    clicks: int
    image_loads: int
    pdf_accesses: int
    downloads: int
    unsubscribes: int
    open_rate: float
    click_rate: float
    assets: list[AssetActivityOut] = []
    timeline: list[TimelineEventOut] = []


class DashboardOut(ORMModel):
    active_campaigns: int
    total_leads: int
    emails_sent: int
    tracked_opens: int
    clicks: int
    failures: int
    bounce_signals: int
    recent_campaigns: list[CampaignOut]


class EventOut(ORMModel):
    id: UUID
    campaign_id: UUID
    email_id: UUID
    event_type: str
    created_at: datetime
    metadata_json: dict
    classification: str | None = None
