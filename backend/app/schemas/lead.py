from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


STANDARD_FIELDS = (
    "email",
    "first_name",
    "last_name",
    "company",
    "title",
    "industry",
    "website",
)


class LeadOut(ORMModel):
    id: UUID
    email: str
    first_name: str | None
    last_name: str | None
    company: str | None
    title: str | None
    industry: str | None
    website: str | None
    country: str | None = None
    study_opportunity: str | None = None
    role_verified: bool = False
    email_kind: str = ""
    custom_fields: dict
    is_valid: bool
    created_at: datetime


class ImportInspectOut(BaseModel):
    headers: list[str]
    suggested_mapping: dict[str, str]
    preview_rows: list[dict[str, str]]
    row_count: int


class ImportCommitRequest(BaseModel):
    filename: str
    csv_text: str
    column_mapping: dict[str, str] = Field(min_length=1)
    group_name: str | None = Field(default=None, max_length=200)


class ImportOut(ORMModel):
    id: UUID
    filename: str
    status: str
    total_rows: int
    valid_count: int
    invalid_count: int
    duplicate_count: int
    column_mapping: dict
    error_report: list
    error_message: str | None
    created_at: datetime
    group_id: UUID | None = None
    group_name: str | None = None


class LeadGroupOut(BaseModel):
    id: UUID
    name: str
    lead_count: int
    purpose: str = "source"
    created_at: datetime


class LeadFacetsOut(BaseModel):
    countries: list[str]
    study_opportunities: list[str]


class WorkbookImportOut(BaseModel):
    group_id: UUID
    group_name: str
    imported: int
    updated: int
    skipped_no_email: int


class LeadGroupDetail(LeadGroupOut):
    match_count: int = 0
    leads: list[LeadOut]


class LeadGroupRename(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class LeadCreate(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    first_name: str | None = Field(default=None, max_length=120)
    last_name: str | None = Field(default=None, max_length=120)
    company: str | None = Field(default=None, max_length=200)
    title: str | None = Field(default=None, max_length=200)
    industry: str | None = Field(default=None, max_length=160)
    website: str | None = Field(default=None, max_length=400)
