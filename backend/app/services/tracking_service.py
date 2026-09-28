import logging
import re
from dataclasses import dataclass
from urllib.parse import urlparse
from uuid import UUID

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.events import publish_user_event
from app.core.exceptions import NotFoundError
from app.core.security import generate_tracking_token
from app.models.campaign import Campaign, CampaignEmail
from app.models.enums import AssetKind, EventType, SignalClassification, SuppressionReason
from app.models.tracking import (
    AssetDeliveryToken,
    CampaignAsset,
    EmailEvent,
    SuppressionEntry,
    TrackedLink,
    TrackingRequest,
    UnsubscribeEvent,
)
from app.services.classification_service import (
    ClassificationResult,
    RequestContext,
    classify_request,
    hash_ip,
    network_prefix,
)

logger = logging.getLogger(__name__)

TRANSPARENT_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)

ASSET_PLACEHOLDER_RE = re.compile(
    r'(?<!["\'])\{\{\s*(asset_(?:img|link)_([a-zA-Z0-9]+))\s*\}\}(?!["\'])'
)
ASSET_HREF_PLACEHOLDER_RE = re.compile(
    r"""href=["']\{\{\s*(asset_(?:img|link)_([a-zA-Z0-9]+))\s*\}\}["']"""
)
ASSET_SRC_PLACEHOLDER_RE = re.compile(
    r"""src=["']\{\{\s*(asset_(?:img|link)_([a-zA-Z0-9]+))\s*\}\}["']"""
)


@dataclass
class ClientSignal:
    client_ip: str | None
    user_agent: str | None
    referrer: str | None
    method: str
    range_header: str | None
    forwarded_for: str | None
    via_header: str | None


def is_safe_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def extract_client_signal(request: Request) -> ClientSignal:
    forwarded = request.headers.get("x-forwarded-for")
    client_ip = None
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()
    elif request.client:
        client_ip = request.client.host
    return ClientSignal(
        client_ip=client_ip,
        user_agent=(request.headers.get("user-agent") or "")[:500] or None,
        referrer=(request.headers.get("referer") or "")[:500] or None,
        method=request.method.upper(),
        range_header=(request.headers.get("range") or "")[:120] or None,
        forwarded_for=forwarded,
        via_header=request.headers.get("via"),
    )


def inject_tracking(
    html: str,
    api_public_url: str,
    email: CampaignEmail,
    assets: list[CampaignAsset] | None = None,
    asset_tokens: dict[UUID, str] | None = None,
    track_engagement: bool = True,
) -> tuple[str, list[TrackedLink]]:
    links: list[TrackedLink] = []
    assets = assets or []
    asset_tokens = asset_tokens or {}
    assets_by_key = {asset.placeholder_key: asset for asset in assets}

    def replace_href(match):
        href = match.group(1)
        if not is_safe_url(href):
            return match.group(0)
        token = generate_tracking_token()
        links.append(TrackedLink(email_id=email.id, token=token, destination_url=href))
        tracked = f"{api_public_url}/t/c/{token}"
        return f'href="{tracked}"'

    rewritten = html
    if track_engagement:
        rewritten = re.sub(r"""href=["']([^"']+)["']""", replace_href, html)

    # Replace asset placeholders with recipient-specific tracked URLs
    def replace_asset_src(match):
        key = match.group(1)
        asset = assets_by_key.get(key)
        if asset is None:
            return match.group(0)
        token = asset_tokens.get(asset.id)
        if not token:
            return match.group(0)
        url = f"{api_public_url}/t/a/{token}"
        return f'src="{url}"'

    def replace_asset_href(match):
        key = match.group(1)
        asset = assets_by_key.get(key)
        if asset is None:
            return match.group(0)
        token = asset_tokens.get(asset.id)
        if not token:
            return match.group(0)
        url = f"{api_public_url}/t/a/{token}?download=1"
        click_token = generate_tracking_token()
        links.append(
            TrackedLink(
                email_id=email.id,
                token=click_token,
                destination_url=url,
                asset_id=asset.id,
            )
        )
        return f'href="{api_public_url}/t/c/{click_token}"'

    rewritten = ASSET_SRC_PLACEHOLDER_RE.sub(replace_asset_src, rewritten)
    rewritten = ASSET_HREF_PLACEHOLDER_RE.sub(replace_asset_href, rewritten)

    # Bare placeholders -> links
    def replace_bare(match):
        key = match.group(1)
        asset = assets_by_key.get(key)
        if asset is None:
            return match.group(0)
        token = asset_tokens.get(asset.id)
        if not token:
            return match.group(0)
        url = f"{api_public_url}/t/a/{token}"
        if asset.kind == AssetKind.IMAGE.value and key.startswith("asset_img_"):
            return f'<img src="{url}" alt="{asset.original_filename}" style="max-width:100%;height:auto;" />'
        download_url = f"{url}?download=1"
        click_token = generate_tracking_token()
        links.append(
            TrackedLink(
                email_id=email.id,
                token=click_token,
                destination_url=download_url,
                asset_id=asset.id,
            )
        )
        label = asset.original_filename
        return f'<a href="{api_public_url}/t/c/{click_token}">{label}</a>'

    rewritten = ASSET_PLACEHOLDER_RE.sub(replace_bare, rewritten)

    view_url = f"{api_public_url}/t/v/{email.tracking_token}"
    pixel = (
        f'<img src="{api_public_url}/t/o/{email.tracking_token}.png" width="1" height="1" '
        f'alt="" style="display:block;width:1px;height:1px;border:0;" />'
    )
    unsubscribe = f"{api_public_url}/unsubscribe/{email.tracking_token}"
    rewritten = rewritten.replace("{{unsubscribe_url}}", unsubscribe)
    rewritten = rewritten.replace("{{view_url}}", view_url)
    extras = ""
    if "{{unsubscribe_url}}" not in html:
        extras += (
            f'<p style="font-size:12px;color:#7c828a">'
            f'<a href="{unsubscribe}">Unsubscribe</a></p>'
        )
    if track_engagement:
        extras += pixel
    body_close = re.search(r"</body\s*>", rewritten, flags=re.IGNORECASE)
    if body_close:
        rewritten = (
            rewritten[: body_close.start()]
            + extras
            + rewritten[body_close.start() :]
        )
    else:
        rewritten += extras
    return rewritten, links


def _normalize_token(token: str) -> str:
    return token.removesuffix(".png").strip()


async def _prior_request_stats(
    db: AsyncSession, email_id: UUID
) -> tuple[int, set[str], set[str]]:
    rows = list(
        (
            await db.scalars(
                select(TrackingRequest).where(TrackingRequest.email_id == email_id)
            )
        ).all()
    )
    ip_hashes = {row.ip_hash for row in rows if row.ip_hash}
    user_agents = {row.user_agent for row in rows if row.user_agent}
    return len(rows), ip_hashes, user_agents


def _classify(
    settings: Settings,
    signal: ClientSignal,
    email: CampaignEmail,
    prior_count: int,
    prior_ips: set[str],
    prior_uas: set[str],
) -> tuple[ClassificationResult, str | None, str | None]:
    ip_digest = hash_ip(signal.client_ip, settings.ip_hash_secret)
    prefix = network_prefix(signal.client_ip)
    result = classify_request(
        RequestContext(
            client_ip=signal.client_ip,
            user_agent=signal.user_agent,
            referrer=signal.referrer,
            method=signal.method,
            range_header=signal.range_header,
            forwarded_for=signal.forwarded_for,
            via_header=signal.via_header,
            sent_at=email.sent_at,
            prior_request_count=prior_count,
            prior_ip_hashes=prior_ips,
            prior_user_agents=prior_uas,
            current_ip_hash=ip_digest,
            automated_window_seconds=float(settings.open_automated_window_seconds),
        )
    )
    return result, ip_digest, prefix


async def _persist_request(
    db: AsyncSession,
    *,
    email: CampaignEmail,
    campaign: Campaign,
    request_type: str,
    classification: ClassificationResult,
    ip_digest: str | None,
    prefix: str | None,
    signal: ClientSignal,
    asset_id: UUID | None = None,
    tracked_link_id: UUID | None = None,
    metadata: dict | None = None,
) -> TrackingRequest:
    row = TrackingRequest(
        email_id=email.id,
        campaign_id=campaign.id,
        user_id=campaign.user_id,
        request_type=request_type,
        classification=classification.classification,
        confidence=classification.confidence,
        classification_reasons=classification.reasons,
        ip_hash=ip_digest,
        network_prefix=prefix,
        user_agent=signal.user_agent,
        referrer=signal.referrer,
        request_method=signal.method,
        range_header=signal.range_header,
        seconds_after_send=classification.seconds_after_send,
        asset_id=asset_id,
        tracked_link_id=tracked_link_id,
        metadata_json=metadata or {},
    )
    db.add(row)
    return row


async def record_open(
    db: AsyncSession,
    token: str,
    signal: ClientSignal | None = None,
    settings: Settings | None = None,
    source: str = "pixel",
) -> CampaignEmail | None:
    settings = settings or get_settings()
    signal = signal or ClientSignal(None, None, None, "GET", None, None, None)
    token = _normalize_token(token)
    email = await db.scalar(select(CampaignEmail).where(CampaignEmail.tracking_token == token))
    if email is None:
        return None
    campaign = await db.scalar(select(Campaign).where(Campaign.id == email.campaign_id))
    if campaign is None:
        return email

    prior_count, prior_ips, prior_uas = await _prior_request_stats(db, email.id)
    classification, ip_digest, prefix = _classify(
        settings, signal, email, prior_count, prior_ips, prior_uas
    )
    await _persist_request(
        db,
        email=email,
        campaign=campaign,
        request_type="open_pixel" if source == "pixel" else "view_email",
        classification=classification,
        ip_digest=ip_digest,
        prefix=prefix,
        signal=signal,
        metadata={"source": source},
    )

    # Always record OPEN_REQUEST event for timeline
    db.add(
        EmailEvent(
            email_id=email.id,
            campaign_id=campaign.id,
            user_id=campaign.user_id,
            event_type=EventType.OPEN_REQUEST.value,
            metadata_json={"source": source, "signal": True},
            classification=classification.classification,
            confidence=classification.confidence,
            classification_reasons=classification.reasons,
            ip_hash=ip_digest,
            network_prefix=prefix,
            user_agent=signal.user_agent,
            referrer=signal.referrer,
            request_method=signal.method,
            range_header=signal.range_header,
        )
    )

    existing_open = await db.scalar(
        select(EmailEvent.id).where(
            EmailEvent.email_id == email.id,
            EmailEvent.event_type == EventType.OPENED.value,
        )
    )
    is_first_unique = existing_open is None
    if is_first_unique:
        db.add(
            EmailEvent(
                email_id=email.id,
                campaign_id=campaign.id,
                user_id=campaign.user_id,
                event_type=EventType.OPENED.value,
                metadata_json={"signal": True, "source": source},
                classification=classification.classification,
                confidence=classification.confidence,
                classification_reasons=classification.reasons,
                ip_hash=ip_digest,
                network_prefix=prefix,
                user_agent=signal.user_agent,
                referrer=signal.referrer,
                request_method=signal.method,
                range_header=signal.range_header,
            )
        )
        campaign.open_count += 1

    await db.commit()
    logger.info(
        "email_open_request",
        extra={
            "event": "email_open_request",
            "email_id": str(email.id),
            "classification": classification.classification,
            "first_unique": is_first_unique,
        },
    )
    publish_user_event(
        campaign.user_id,
        {
            "type": "EMAIL_OPEN_REQUEST",
            "campaign_id": str(campaign.id),
            "email_id": str(email.id),
            "lead_id": str(email.lead_id),
            "classification": classification.classification,
            "confidence": classification.confidence,
            "reasons": classification.reasons,
            "is_first_unique_open": is_first_unique,
            "source": source,
        },
    )
    if is_first_unique:
        publish_user_event(
            campaign.user_id,
            {
                "type": "EMAIL_OPENED",
                "campaign_id": str(campaign.id),
                "email_id": str(email.id),
                "lead_id": str(email.lead_id),
                "classification": classification.classification,
                "confidence": classification.confidence,
                "reasons": classification.reasons,
            },
        )
    return email


async def record_click(
    db: AsyncSession,
    token: str,
    signal: ClientSignal | None = None,
    settings: Settings | None = None,
) -> str:
    settings = settings or get_settings()
    signal = signal or ClientSignal(None, None, None, "GET", None, None, None)
    token = _normalize_token(token)
    link = await db.scalar(select(TrackedLink).where(TrackedLink.token == token))
    if link is None or not is_safe_url(link.destination_url):
        raise NotFoundError("Tracked link not found")
    email = await db.get(CampaignEmail, link.email_id)
    if email is None:
        raise NotFoundError("Email not found")
    campaign = await db.get(Campaign, email.campaign_id)
    if campaign is None:
        raise NotFoundError("Campaign not found")

    # Open signal from click is a stronger engagement cue
    if email.tracking_token:
        await record_open(db, email.tracking_token, signal=signal, settings=settings, source="click")
        link = await db.get(TrackedLink, link.id)
        email = await db.get(CampaignEmail, email.id)
        campaign = await db.get(Campaign, email.campaign_id) if email else None
        if link is None or email is None or campaign is None:
            raise NotFoundError("Email not found")

    prior_count, prior_ips, prior_uas = await _prior_request_stats(db, email.id)
    classification, ip_digest, prefix = _classify(
        settings, signal, email, prior_count, prior_ips, prior_uas
    )
    # Clicks are stronger human evidence
    if classification.classification != SignalClassification.AUTOMATED.value:
        classification = ClassificationResult(
            classification=SignalClassification.POSSIBLE_HUMAN.value,
            confidence=max(classification.confidence, 0.75),
            reasons=[*classification.reasons, "explicit_link_click"],
            seconds_after_send=classification.seconds_after_send,
        )
    else:
        classification.reasons = [*classification.reasons, "explicit_link_click"]

    await _persist_request(
        db,
        email=email,
        campaign=campaign,
        request_type="link_click",
        classification=classification,
        ip_digest=ip_digest,
        prefix=prefix,
        signal=signal,
        asset_id=link.asset_id,
        tracked_link_id=link.id,
        metadata={"destination_url": link.destination_url},
    )

    link.click_count += 1
    db.add(
        EmailEvent(
            email_id=email.id,
            campaign_id=campaign.id,
            user_id=campaign.user_id,
            event_type=EventType.CLICKED.value,
            metadata_json={"link_id": str(link.id), "destination_url": link.destination_url},
            classification=classification.classification,
            confidence=classification.confidence,
            classification_reasons=classification.reasons,
            ip_hash=ip_digest,
            network_prefix=prefix,
            user_agent=signal.user_agent,
            referrer=signal.referrer,
            request_method=signal.method,
            range_header=signal.range_header,
            asset_id=link.asset_id,
            tracked_link_id=link.id,
        )
    )
    campaign.click_count += 1
    await db.commit()
    logger.info("email_clicked", extra={"event": "email_clicked", "email_id": str(email.id)})
    publish_user_event(
        campaign.user_id,
        {
            "type": "LINK_CLICKED",
            "campaign_id": str(campaign.id),
            "email_id": str(email.id),
            "lead_id": str(email.lead_id),
            "destination_url": link.destination_url,
            "link_clicks": link.click_count,
            "classification": classification.classification,
            "asset_id": str(link.asset_id) if link.asset_id else None,
        },
    )
    return link.destination_url


async def record_asset_access(
    db: AsyncSession,
    token: str,
    *,
    download: bool = False,
    signal: ClientSignal | None = None,
    settings: Settings | None = None,
) -> tuple[CampaignAsset, AssetDeliveryToken, CampaignEmail]:
    settings = settings or get_settings()
    signal = signal or ClientSignal(None, None, None, "GET", None, None, None)
    delivery = await db.scalar(
        select(AssetDeliveryToken).where(AssetDeliveryToken.token == token)
    )
    if delivery is None:
        raise NotFoundError("Asset token not found")
    asset = await db.get(CampaignAsset, delivery.asset_id)
    email = await db.get(CampaignEmail, delivery.email_id)
    campaign = await db.get(Campaign, delivery.campaign_id)
    if asset is None or email is None or campaign is None:
        raise NotFoundError("Asset not found")

    prior_count, prior_ips, prior_uas = await _prior_request_stats(db, email.id)
    classification, ip_digest, prefix = _classify(
        settings, signal, email, prior_count, prior_ips, prior_uas
    )

    if download or asset.kind == AssetKind.PDF.value:
        request_type = "download_requested" if download else "pdf_accessed"
        event_type = (
            EventType.DOWNLOAD_REQUESTED.value
            if download
            else EventType.PDF_ACCESSED.value
        )
        ws_type = "ASSET_DOWNLOAD_REQUESTED" if download else "ASSET_PDF_ACCESSED"
    else:
        request_type = "image_loaded"
        event_type = EventType.IMAGE_LOADED.value
        ws_type = "ASSET_IMAGE_LOADED"

    await _persist_request(
        db,
        email=email,
        campaign=campaign,
        request_type=request_type,
        classification=classification,
        ip_digest=ip_digest,
        prefix=prefix,
        signal=signal,
        asset_id=asset.id,
        metadata={
            "filename": asset.original_filename,
            "kind": asset.kind,
            "download": download,
        },
    )

    delivery.access_count += 1
    asset.access_count += 1
    if download:
        delivery.download_count += 1
        asset.download_count += 1

    db.add(
        EmailEvent(
            email_id=email.id,
            campaign_id=campaign.id,
            user_id=campaign.user_id,
            event_type=event_type,
            metadata_json={
                "filename": asset.original_filename,
                "kind": asset.kind,
                "download": download,
            },
            classification=classification.classification,
            confidence=classification.confidence,
            classification_reasons=classification.reasons,
            ip_hash=ip_digest,
            network_prefix=prefix,
            user_agent=signal.user_agent,
            referrer=signal.referrer,
            request_method=signal.method,
            range_header=signal.range_header,
            asset_id=asset.id,
        )
    )
    await db.commit()
    publish_user_event(
        campaign.user_id,
        {
            "type": ws_type,
            "campaign_id": str(campaign.id),
            "email_id": str(email.id),
            "asset_id": str(asset.id),
            "filename": asset.original_filename,
            "kind": asset.kind,
            "classification": classification.classification,
            "download": download,
        },
    )
    return asset, delivery, email


async def unsubscribe(db: AsyncSession, token: str) -> None:
    email = await db.scalar(select(CampaignEmail).where(CampaignEmail.tracking_token == token))
    if email is None:
        raise NotFoundError("Unsubscribe token is invalid")
    campaign = await db.get(Campaign, email.campaign_id)
    if campaign is None:
        raise NotFoundError()
    lead_email = None
    if hasattr(email, "lead") and email.lead is not None:
        lead_email = email.lead.email
    if lead_email is None:
        from app.models.lead import Lead

        lead_row = await db.get(Lead, email.lead_id)
        lead_email = lead_row.email if lead_row else None
    if not lead_email:
        raise NotFoundError()
    existing = await db.scalar(
        select(SuppressionEntry).where(
            SuppressionEntry.user_id == campaign.user_id,
            SuppressionEntry.email == lead_email,
        )
    )
    if existing is None:
        db.add(
            SuppressionEntry(
                user_id=campaign.user_id,
                email=lead_email,
                reason=SuppressionReason.UNSUBSCRIBE.value,
                source="unsubscribe_link",
            )
        )
        campaign.unsubscribe_count += 1
    db.add(
        UnsubscribeEvent(
            user_id=campaign.user_id,
            email_id=email.id,
            campaign_id=campaign.id,
            email=lead_email,
            token=token,
        )
    )
    db.add(
        EmailEvent(
            email_id=email.id,
            campaign_id=campaign.id,
            user_id=campaign.user_id,
            event_type=EventType.UNSUBSCRIBED.value,
            metadata_json={},
        )
    )
    await db.commit()
    logger.info("unsubscribe_created", extra={"event": "unsubscribe_created"})
    publish_user_event(
        campaign.user_id,
        {
            "type": "EMAIL_UNSUBSCRIBED",
            "campaign_id": str(campaign.id),
            "email_id": str(email.id),
            "recipient_email": lead_email,
        },
    )


def is_suppressed_sync(session: Session, user_id: UUID, email: str) -> bool:
    return (
        session.scalar(
            select(SuppressionEntry.id).where(
                SuppressionEntry.user_id == user_id,
                SuppressionEntry.email == email,
            )
        )
        is not None
    )


def display_classification(
    classification: str | None,
    reasons: list | None = None,
    seconds_after_send: float | None = None,
    *,
    window_seconds: float = 30,
) -> str | None:
    """Label shown in the product: Likely automated only inside the send window."""
    if not classification:
        return classification
    if seconds_after_send is not None:
        if seconds_after_send < window_seconds:
            return SignalClassification.AUTOMATED.value
        return "opened"
    if classification == SignalClassification.AUTOMATED.value and any(
        str(reason).startswith("within_") for reason in (reasons or [])
    ):
        return SignalClassification.AUTOMATED.value
    if classification in {
        SignalClassification.AUTOMATED.value,
        SignalClassification.POSSIBLE_HUMAN.value,
        SignalClassification.PROXY_OR_UNCERTAIN.value,
        "opened",
    }:
        return "opened"
    return classification


def classification_for_label(
    classification: str | None,
    seconds_after_send: float | None,
    *,
    window_seconds: float = 30,
) -> str:
    """Re-label stored requests: only a hit inside the window stays automated."""
    if seconds_after_send is not None and seconds_after_send >= window_seconds:
        return "opened"
    return classification or "opened"


def open_label_from_requests(classifications: list[str]) -> str:
    if not classifications:
        return "none"
    if all(item == SignalClassification.AUTOMATED.value for item in classifications):
        return "likely_automated"
    return "opened"
