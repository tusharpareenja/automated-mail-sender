import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_sync_session_factory
from app.core.exceptions import ProviderError
from app.core.security import generate_tracking_token
from app.models.campaign import Campaign, CampaignEmail, CampaignSMTP
from app.models.enums import AssetKind, CampaignStatus, EmailStatus, EventType, SMTPHealth
from app.models.lead import Lead, LeadGroup, LeadGroupMember
from app.models.smtp import SMTPAccount, SMTPUsage
from app.models.tracking import CampaignAsset, EmailEvent, TrackedLink
from app.services.openai_service import generate_personalization_sync
from app.services.smtp_service import send_via_smtp
from app.models.user import User
from app.services.template_service import apply_sender_context, lead_context, render_template, wrap_outbound_email
from app.core.events import publish_user_event
from app.core.runtime import get_public_url, untrusted_tracking_host
from app.services.tracking_service import inject_tracking, is_suppressed_sync
from app.services.asset_service import (
    assets_for_placeholders_sync,
    embed_preview_asset_urls,
    mint_delivery_tokens_sync,
    strip_pdf_placeholders,
)
from app.services.asset_storage import load_asset_bytes
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def _session() -> Session:
    return get_sync_session_factory()()


def _hour_bucket(now: datetime) -> datetime:
    return now.replace(minute=0, second=0, microsecond=0)


def _day_bucket(now: datetime) -> datetime:
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def _usage(session: Session, account_id, bucket_type: str, start: datetime) -> SMTPUsage:
    row = session.scalar(
        select(SMTPUsage).where(
            SMTPUsage.smtp_account_id == account_id,
            SMTPUsage.bucket_type == bucket_type,
            SMTPUsage.bucket_start == start,
        )
    )
    if row is None:
        row = SMTPUsage(
            smtp_account_id=account_id,
            bucket_type=bucket_type,
            bucket_start=start,
            send_count=0,
        )
        session.add(row)
        session.flush()
    return row


def _pick_account(session: Session, campaign: Campaign, now: datetime) -> SMTPAccount | None:
    links = session.scalars(
        select(CampaignSMTP).where(CampaignSMTP.campaign_id == campaign.id)
    ).all()
    candidates = []
    for link in links:
        account = session.get(SMTPAccount, link.smtp_account_id)
        if (
            account is None
            or not account.is_active
            or account.health_status == SMTPHealth.UNHEALTHY.value
        ):
            continue
        hour = _usage(session, account.id, "hour", _hour_bucket(now))
        day = _usage(session, account.id, "day", _day_bucket(now))
        if hour.send_count >= account.hourly_limit or day.send_count >= account.daily_limit:
            continue
        candidates.append((account, hour.send_count + day.send_count))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[1])
    return candidates[0][0]


def _campaign_within_limits(session: Session, campaign: Campaign, now: datetime) -> bool:
    hour_count = (
        session.scalar(
            select(func.count()).select_from(CampaignEmail).where(
                CampaignEmail.campaign_id == campaign.id,
                CampaignEmail.status == EmailStatus.SENT.value,
                CampaignEmail.sent_at >= _hour_bucket(now),
            )
        )
        or 0
    )
    day_count = (
        session.scalar(
            select(func.count()).select_from(CampaignEmail).where(
                CampaignEmail.campaign_id == campaign.id,
                CampaignEmail.status == EmailStatus.SENT.value,
                CampaignEmail.sent_at >= _day_bucket(now),
            )
        )
        or 0
    )
    return hour_count < campaign.hourly_limit and day_count < campaign.daily_limit


_OPEN_STATUSES = (
    EmailStatus.QUEUED.value,
    EmailStatus.READY.value,
    EmailStatus.GENERATING.value,
    EmailStatus.SENDING.value,
)


def _unique_group_name(session: Session, user_id, name: str) -> str:
    base = name.strip()[:200] or "Campaign"
    candidate = base
    number = 2
    while session.scalar(
        select(LeadGroup.id).where(LeadGroup.user_id == user_id, LeadGroup.name == candidate)
    ):
        suffix = f" ({number})"
        candidate = f"{base[: 200 - len(suffix)]}{suffix}"
        number += 1
    return candidate


def _outcome_group(session: Session, campaign: Campaign, purpose: str, suffix: str) -> LeadGroup:
    attr = "sent_group_id" if purpose == "sent" else "failed_group_id"
    group_id = getattr(campaign, attr)
    group = session.get(LeadGroup, group_id) if group_id else None
    if group is None:
        group = LeadGroup(
            user_id=campaign.user_id,
            name=_unique_group_name(session, campaign.user_id, f"{campaign.name} — {suffix}"),
            purpose=purpose,
        )
        session.add(group)
        session.flush()
        setattr(campaign, attr, group.id)
    return group


def _add_group_members(session: Session, group: LeadGroup, lead_ids: list) -> None:
    if not lead_ids:
        return
    existing = set(
        session.scalars(
            select(LeadGroupMember.lead_id).where(
                LeadGroupMember.group_id == group.id,
                LeadGroupMember.lead_id.in_(lead_ids),
            )
        ).all()
    )
    for lead_id in lead_ids:
        if lead_id in existing:
            continue
        session.add(LeadGroupMember(group_id=group.id, lead_id=lead_id))
        existing.add(lead_id)


def sync_outcome_groups(session: Session, campaign: Campaign) -> None:
    sent_ids = list(
        session.scalars(
            select(CampaignEmail.lead_id).where(
                CampaignEmail.campaign_id == campaign.id,
                CampaignEmail.status == EmailStatus.SENT.value,
            )
        ).all()
    )
    failed_ids = list(
        session.scalars(
            select(CampaignEmail.lead_id).where(
                CampaignEmail.campaign_id == campaign.id,
                CampaignEmail.status == EmailStatus.FAILED.value,
            )
        ).all()
    )
    if sent_ids:
        _add_group_members(session, _outcome_group(session, campaign, "sent", "Sent"), sent_ids)
    if failed_ids:
        _add_group_members(session, _outcome_group(session, campaign, "failed", "Failed"), failed_ids)


def _reclaim_stuck(session: Session, campaign: Campaign, now: datetime) -> None:
    stale_before = now - timedelta(minutes=15)
    stuck = session.scalars(
        select(CampaignEmail).where(
            CampaignEmail.campaign_id == campaign.id,
            CampaignEmail.status.in_([EmailStatus.SENDING.value, EmailStatus.GENERATING.value]),
            CampaignEmail.claimed_at.is_not(None),
            CampaignEmail.claimed_at < stale_before,
        )
    ).all()
    for email in stuck:
        email.attempt_count = (email.attempt_count or 0) + 1
        email.claimed_at = None
        email.claim_owner = None
        if email.attempt_count >= 5:
            email.status = EmailStatus.FAILED.value
            email.error_code = "stuck"
            email.error_message = "Stopped after repeated attempts"
        else:
            email.status = EmailStatus.QUEUED.value


def _template_pdfs(
    session: Session, settings, campaign: Campaign
) -> tuple[list[tuple[str, str, bytes]], list[str]]:
    if campaign.template_id is None:
        return [], []
    assets = session.scalars(
        select(CampaignAsset).where(
            CampaignAsset.user_id == campaign.user_id,
            CampaignAsset.template_id == campaign.template_id,
            CampaignAsset.kind == AssetKind.PDF.value,
        )
    ).all()
    files = []
    keys = []
    for asset in assets:
        data, _hint = load_asset_bytes(settings, campaign.user_id, asset.stored_filename)
        files.append((asset.original_filename, asset.content_type or "application/pdf", data))
        keys.append(asset.placeholder_key)
    return files, keys


def _mark_failed(email_id: str, code: str, message: str) -> None:
    session = _session()
    try:
        email = session.get(CampaignEmail, uuid.UUID(email_id))
        if email is None or email.status == EmailStatus.SENT.value:
            return
        email.status = EmailStatus.FAILED.value
        email.error_code = code[:80]
        email.error_message = message[:500]
        email.attempt_count = (email.attempt_count or 0) + 1
        campaign = session.get(Campaign, email.campaign_id)
        lead = session.get(Lead, email.lead_id)
        session.commit()
        if campaign is not None:
            publish_user_event(
                campaign.user_id,
                {
                    "type": "EMAIL_FAILED",
                    "campaign_id": str(campaign.id),
                    "email_id": str(email.id),
                    "recipient_email": lead.email if lead else None,
                },
            )
    except Exception:
        session.rollback()
    finally:
        session.close()


@celery_app.task(name="app.workers.email_tasks.dispatch_running_campaigns")
def dispatch_running_campaigns() -> int:
    session = _session()
    dispatched = 0
    try:
        campaigns = session.scalars(
            select(Campaign).where(Campaign.status == CampaignStatus.RUNNING.value)
        ).all()
        now = datetime.now(timezone.utc)
        for campaign in campaigns:
            _reclaim_stuck(session, campaign, now)
            open_count = (
                session.scalar(
                    select(func.count()).select_from(CampaignEmail).where(
                        CampaignEmail.campaign_id == campaign.id,
                        CampaignEmail.status.in_(_OPEN_STATUSES),
                    )
                )
                or 0
            )
            sync_outcome_groups(session, campaign)
            if open_count == 0:
                campaign.status = CampaignStatus.COMPLETED.value
                campaign.completed_at = now
                logger.info(
                    "campaign_completed",
                    extra={"event": "campaign_completed", "campaign_id": str(campaign.id)},
                )
                publish_user_event(
                    campaign.user_id,
                    {
                        "type": "CAMPAIGN_COMPLETED",
                        "campaign_id": str(campaign.id),
                        "status": CampaignStatus.COMPLETED.value,
                    },
                )
                continue
            remaining = session.scalars(
                select(CampaignEmail.id).where(
                    CampaignEmail.campaign_id == campaign.id,
                    CampaignEmail.status.in_(
                        [EmailStatus.QUEUED.value, EmailStatus.READY.value, EmailStatus.GENERATING.value]
                    ),
                ).limit(25)
            ).all()
            for email_id in remaining:
                send_campaign_email.delay(str(email_id))
                dispatched += 1
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
    return dispatched


@celery_app.task(
    name="app.workers.email_tasks.send_campaign_email",
    bind=True,
    autoretry_for=(ProviderError,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 5},
)
def send_campaign_email(self, email_id: str) -> str:
    settings = get_settings()
    session = _session()
    now = datetime.now(timezone.utc)
    try:
        email = session.execute(
            select(CampaignEmail)
            .where(CampaignEmail.id == uuid.UUID(email_id))
            .with_for_update(skip_locked=True)
        ).scalar_one_or_none()
        if email is None:
            return "missing"
        if email.status in {EmailStatus.SENT.value, EmailStatus.SKIPPED.value}:
            return email.status
        if email.status == EmailStatus.SENDING.value and email.claimed_at:
            if email.claimed_at > now - timedelta(minutes=10):
                return "claimed"
        campaign = session.get(Campaign, email.campaign_id)
        if campaign is None or campaign.status != CampaignStatus.RUNNING.value:
            return "not_running"
        if not _campaign_within_limits(session, campaign, now):
            return "limited"

        lead = session.get(Lead, email.lead_id)
        if lead is None or is_suppressed_sync(session, campaign.user_id, lead.email):
            email.status = EmailStatus.SKIPPED.value
            session.commit()
            return "skipped"

        account = _pick_account(session, campaign, now)
        if account is None:
            return "no_smtp"

        email.status = EmailStatus.SENDING.value
        email.claimed_at = now
        email.claim_owner = self.request.id or "worker"
        email.smtp_account_id = account.id
        session.flush()

        snapshot = campaign.template_snapshot or {}
        owner = session.get(User, campaign.user_id)
        context = apply_sender_context(
            lead_context(lead),
            from_name=account.from_name or (owner.full_name if owner else ""),
            company=(owner.company_name if owner else "") or "",
        )
        if campaign.ai_enabled and not email.personalization:
            email.status = EmailStatus.GENERATING.value
            session.flush()
            email.personalization = generate_personalization_sync(
                settings,
                context,
                campaign.ai_instructions,
                subject=snapshot.get("subject", ""),
                html_body=snapshot.get("html_body", ""),
                text_body=snapshot.get("text_body", ""),
            )
        personalization = email.personalization or {}
        context.update(
            {
                key: personalization[key]
                for key in ("opener", "signoff", "company_note")
                if personalization.get(key)
            }
        )
        context = apply_sender_context(
            context,
            from_name=account.from_name or (owner.full_name if owner else ""),
            company=(owner.company_name if owner else "") or "",
        )
        subject = render_template(
            personalization.get("subject") or snapshot.get("subject", ""), context
        )
        html_body = render_template(
            personalization.get("html_body") or snapshot.get("html_body", ""), context
        )
        text_body = render_template(
            personalization.get("text_body") or snapshot.get("text_body", ""), context
        )
        html_body, text_body = wrap_outbound_email(
            html_body,
            text_body,
            from_name=account.from_name or (owner.full_name if owner else ""),
            company=(owner.company_name if owner else "") or "",
            physical_address=(owner.physical_address if owner else "") or "",
        )
        public_url = get_public_url()
        pdf_files, pdf_keys = _template_pdfs(session, settings, campaign)
        html_body = strip_pdf_placeholders(html_body, pdf_keys)
        text_body = strip_pdf_placeholders(text_body, pdf_keys)
        assets = assets_for_placeholders_sync(session, campaign.user_id, html_body)
        track_engagement = not untrusted_tracking_host(public_url)
        if not track_engagement:
            html_body = embed_preview_asset_urls(settings, assets, html_body)
        asset_tokens = mint_delivery_tokens_sync(
            session,
            email_id=email.id,
            campaign_id=campaign.id,
            assets=assets,
        )
        html_body, links = inject_tracking(
            html_body,
            public_url,
            email,
            assets=assets,
            asset_tokens=asset_tokens,
            track_engagement=track_engagement,
        )
        for link in links:
            session.add(link)
        unsubscribe_url = f"{public_url}/unsubscribe/{email.tracking_token}"
        text_body = text_body.replace("{{unsubscribe_url}}", unsubscribe_url)

        sender_domain = (account.from_email or "localhost").split("@")[-1]
        message_id = email.message_id or f"<{email.tracking_token}@{sender_domain}>"
        headers = {
            "List-Unsubscribe": f"<{unsubscribe_url}>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
        }
        send_via_smtp(
            settings,
            account,
            lead.email,
            subject,
            html_body,
            text_body,
            message_id=message_id,
            extra_headers=headers,
            attachments=pdf_files,
        )
        email.subject = subject
        email.html_body = html_body
        email.text_body = text_body
        email.message_id = message_id
        email.status = EmailStatus.SENT.value
        email.sent_at = now
        session.execute(
            update(Campaign)
            .where(Campaign.id == campaign.id)
            .values(
                sent_count=Campaign.sent_count + 1,
                queued_count=func.greatest(Campaign.queued_count - 1, 0),
            )
        )
        hour = _usage(session, account.id, "hour", _hour_bucket(now))
        day = _usage(session, account.id, "day", _day_bucket(now))
        hour.send_count += 1
        day.send_count += 1
        account.consecutive_failures = 0
        account.health_status = SMTPHealth.HEALTHY.value
        session.add(
            EmailEvent(
                email_id=email.id,
                campaign_id=campaign.id,
                user_id=campaign.user_id,
                event_type=EventType.SENT.value,
                metadata_json={},
            )
        )
        session.commit()
        logger.info("email_sent", extra={"event": "email_sent", "email_id": str(email.id)})
        publish_user_event(
            campaign.user_id,
            {
                "type": "EMAIL_SENT",
                "campaign_id": str(campaign.id),
                "email_id": str(email.id),
                "recipient_email": lead.email,
            },
        )
        return "sent"
    except ProviderError as exc:
        session.rollback()
        if self.request.retries >= 5:
            _mark_failed(email_id, "smtp_error", str(exc) or "SMTP provider error")
            logger.info("email_failed", extra={"event": "email_failed", "email_id": email_id})
            return "failed"
        logger.info("email_retry", extra={"event": "email_retry", "email_id": email_id})
        raise
    except Exception as exc:
        session.rollback()
        _mark_failed(email_id, type(exc).__name__, str(exc) or "Send failed")
        logger.info("email_failed", extra={"event": "email_failed", "email_id": email_id})
        return "failed"
    finally:
        session.close()
