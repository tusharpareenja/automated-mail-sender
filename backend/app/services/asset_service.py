"""Authenticated asset upload/list/delete and send-time token minting."""

from __future__ import annotations

import html as html_lib
import re
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import NotFoundError
from app.core.security import generate_tracking_token
from app.models.template import Template
from app.models.tracking import AssetDeliveryToken, CampaignAsset
from app.models.user import User
from app.services.asset_storage import blob_preview_url, delete_asset_file, save_asset_bytes

_ASSET_SRC_RE = re.compile(
    r"""src=["']\{\{\s*(asset_(?:img|link)_[a-zA-Z0-9]+)\s*\}\}["']"""
)
_ASSET_HREF_RE = re.compile(
    r"""href=["']\{\{\s*(asset_(?:img|link)_[a-zA-Z0-9]+)\s*\}\}["']"""
)
_ASSET_BARE_RE = re.compile(
    r'(?<!["\'])\{\{\s*(asset_(?:img|link)_[a-zA-Z0-9]+)\s*\}\}(?!["\'])'
)


async def owned_template(
    db: AsyncSession, user: User, template_id: UUID | None
) -> Template | None:
    if template_id is None:
        return None
    template = await db.scalar(
        select(Template).where(Template.id == template_id, Template.user_id == user.id)
    )
    if template is None:
        raise NotFoundError("Template not found")
    return template


async def list_assets(
    db: AsyncSession, user: User, template_id: UUID | None = None
) -> list[CampaignAsset]:
    query = select(CampaignAsset).where(CampaignAsset.user_id == user.id)
    if template_id is not None:
        query = query.where(CampaignAsset.template_id == template_id)
    rows = list(
        (await db.scalars(query.order_by(CampaignAsset.created_at.desc()))).all()
    )
    return rows


async def upload_asset(
    db: AsyncSession,
    settings: Settings,
    user: User,
    *,
    filename: str,
    data: bytes,
    content_type: str | None,
    template_id: UUID | None = None,
) -> CampaignAsset:
    await owned_template(db, user, template_id)
    saved = save_asset_bytes(settings, user.id, filename, data, content_type)
    asset = CampaignAsset(
        user_id=user.id,
        template_id=template_id,
        original_filename=saved["original_filename"],
        stored_filename=saved["stored_filename"],
        content_type=saved["content_type"],
        kind=saved["kind"],
        size_bytes=saved["size_bytes"],
        checksum_sha256=saved["checksum_sha256"],
        placeholder_key=saved["placeholder_key"],
    )
    db.add(asset)
    await db.flush()
    return asset


async def delete_asset(db: AsyncSession, settings: Settings, user: User, asset_id: UUID) -> None:
    asset = await db.scalar(
        select(CampaignAsset).where(
            CampaignAsset.id == asset_id, CampaignAsset.user_id == user.id
        )
    )
    if asset is None:
        raise NotFoundError("Asset not found")
    delete_asset_file(settings, user.id, asset.stored_filename)
    await db.delete(asset)


async def get_owned_asset(db: AsyncSession, user: User, asset_id: UUID) -> CampaignAsset:
    asset = await db.scalar(
        select(CampaignAsset).where(
            CampaignAsset.id == asset_id, CampaignAsset.user_id == user.id
        )
    )
    if asset is None:
        raise NotFoundError("Asset not found")
    return asset


def mint_delivery_tokens_sync(
    session: Session,
    *,
    email_id: UUID,
    campaign_id: UUID,
    assets: list[CampaignAsset],
) -> dict[UUID, str]:
    """Create or reuse per-recipient delivery tokens for assets referenced in HTML."""
    tokens: dict[UUID, str] = {}
    for asset in assets:
        existing = session.scalar(
            select(AssetDeliveryToken).where(
                AssetDeliveryToken.asset_id == asset.id,
                AssetDeliveryToken.email_id == email_id,
            )
        )
        if existing is None:
            existing = AssetDeliveryToken(
                asset_id=asset.id,
                email_id=email_id,
                campaign_id=campaign_id,
                token=generate_tracking_token(),
            )
            session.add(existing)
            session.flush()
        tokens[asset.id] = existing.token
    return tokens


def embed_preview_asset_urls(settings: Settings, assets: list[CampaignAsset], html: str) -> str:
    """Swap asset placeholders for browser-loadable image URLs. Send-time tracking stays on the real send."""
    urls: dict[str, str] = {}
    for asset in assets:
        url = blob_preview_url(
            settings, asset.user_id, asset.stored_filename, asset.content_type
        )
        if url:
            urls[asset.placeholder_key] = html_lib.escape(url, quote=True)
    if not urls or not html:
        return html

    def src_repl(match: re.Match[str]) -> str:
        url = urls.get(match.group(1))
        return f'src="{url}"' if url else match.group(0)

    def href_repl(match: re.Match[str]) -> str:
        url = urls.get(match.group(1))
        return f'href="{url}"' if url else match.group(0)

    def bare_repl(match: re.Match[str]) -> str:
        url = urls.get(match.group(1))
        if not url:
            return match.group(0)
        if match.group(1).startswith("asset_img_"):
            return f'<img src="{url}" alt="" style="max-width:100%;height:auto;" />'
        return f'<a href="{url}">Download</a>'

    rewritten = _ASSET_SRC_RE.sub(src_repl, html)
    rewritten = _ASSET_HREF_RE.sub(href_repl, rewritten)
    return _ASSET_BARE_RE.sub(bare_repl, rewritten)


def strip_pdf_placeholders(body: str, placeholder_keys: list[str]) -> str:
    """Remove PDF placeholders so the file is only sent as an email attachment."""
    cleaned = body or ""
    for key in placeholder_keys:
        escaped = re.escape(key)
        cleaned = re.sub(
            rf"<p[^>]*>\s*(?:<a\b[^>]*>\s*)?\{{\{{\s*{escaped}\s*\}}\}}\s*(?:</a>\s*)?</p>",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            rf"<a\b[^>]*>\s*\{{\{{\s*{escaped}\s*\}}\}}\s*</a>",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(rf"\{{\{{\s*{escaped}\s*\}}\}}", "", cleaned)
    return cleaned


def assets_for_placeholders_sync(
    session: Session, user_id: UUID, html: str
) -> list[CampaignAsset]:
    import re

    keys = set(re.findall(r"\{\{\s*(asset_(?:img|link)_[a-zA-Z0-9]+)\s*\}\}", html))
    if not keys:
        return []
    rows = list(
        session.scalars(
            select(CampaignAsset).where(
                CampaignAsset.user_id == user_id,
                CampaignAsset.placeholder_key.in_(keys),
            )
        ).all()
    )
    return rows
