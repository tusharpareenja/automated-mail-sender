from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class TemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    subject: str = Field(min_length=1, max_length=300)
    html_body: str = Field(min_length=1)
    text_body: str | None = None
    ai_instructions: str | None = None


class TemplateUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=160)
    subject: str | None = Field(default=None, max_length=300)
    html_body: str | None = None
    text_body: str | None = None
    ai_instructions: str | None = None


class TemplatePreviewRequest(BaseModel):
    first_name: str = "Alex"
    last_name: str = "Morgan"
    company: str = "Northwind"
    title: str = "Operations Lead"
    industry: str = "Software"
    website: str = "https://example.com"
    email: str = "alex@example.com"
    opener: str = ""
    signoff: str = ""
    custom_fields: dict[str, str] = {}


class TemplateOut(ORMModel):
    id: UUID
    name: str
    subject: str
    html_body: str
    text_body: str
    ai_instructions: str | None
    variables: list[str]
    created_at: datetime
    updated_at: datetime


class AssetOut(ORMModel):
    """Hosted template file returned to the editor."""

    id: UUID
    template_id: UUID | None
    original_filename: str
    content_type: str
    kind: str
    size_bytes: int
    checksum_sha256: str
    placeholder_key: str
    preview_url: str = ""
    inline_placeholder: str
    link_placeholder: str
    access_count: int
    download_count: int
    created_at: datetime
    updated_at: datetime


def asset_to_out(asset, *, preview_url: str = "") -> AssetOut:
    return AssetOut(
        id=asset.id,
        template_id=asset.template_id,
        original_filename=asset.original_filename,
        content_type=asset.content_type,
        kind=asset.kind,
        size_bytes=asset.size_bytes,
        checksum_sha256=asset.checksum_sha256,
        placeholder_key=asset.placeholder_key,
        preview_url=preview_url,
        inline_placeholder=f"{{{{{asset.placeholder_key}}}}}",
        link_placeholder=f'<a href="{{{{{asset.placeholder_key}}}}}">{asset.original_filename}</a>',
        access_count=asset.access_count,
        download_count=asset.download_count,
        created_at=asset.created_at,
        updated_at=asset.updated_at,
    )
