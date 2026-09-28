import asyncio
import logging
import re
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import AppError, NotFoundError
from app.core.security import generate_tracking_token
from app.models.campaign import Campaign, CampaignEmail, CampaignLead, CampaignSMTP
from app.models.enums import CampaignStatus, EmailStatus
from app.models.lead import Lead, LeadGroup, LeadGroupMember
from app.models.smtp import SMTPAccount
from app.models.template import Template
from app.models.tracking import CampaignAsset, SuppressionEntry
from app.models.user import User
from app.schemas.campaign import CampaignCreate, CampaignUpdate
from app.services.asset_service import embed_preview_asset_urls, strip_pdf_placeholders
from app.services.openai_service import generate_personalization
from app.services.template_service import (
    apply_sender_context,
    lead_context,
    render_template,
    wrap_outbound_email,
)

logger = logging.getLogger(__name__)

ALLOWED_TRANSITIONS = {
    CampaignStatus.DRAFT: {CampaignStatus.QUEUED, CampaignStatus.CANCELLED},
    CampaignStatus.QUEUED: {CampaignStatus.RUNNING, CampaignStatus.CANCELLED, CampaignStatus.FAILED},
    CampaignStatus.RUNNING: {
        CampaignStatus.PAUSED,
        CampaignStatus.COMPLETED,
        CampaignStatus.CANCELLED,
        CampaignStatus.FAILED,
    },
    CampaignStatus.PAUSED: {CampaignStatus.RUNNING, CampaignStatus.CANCELLED},
    CampaignStatus.COMPLETED: set(),
    CampaignStatus.CANCELLED: set(),
    CampaignStatus.FAILED: {CampaignStatus.QUEUED},
}


async def get_owned_campaign(db: AsyncSession, user: User, campaign_id: UUID) -> Campaign:
    campaign = await db.scalar(
        select(Campaign).where(Campaign.id == campaign_id, Campaign.user_id == user.id)
    )
    if campaign is None:
        raise NotFoundError("Campaign not found")
    await sync_delivery_counts(db, campaign)
    return campaign


async def sync_delivery_counts(db: AsyncSession, campaign: Campaign) -> None:
    """Match sent/queued/failed cards to the email rows. Concurrent workers used to drop increments."""
    rows = (
        await db.execute(
            select(CampaignEmail.status, func.count())
            .where(CampaignEmail.campaign_id == campaign.id)
            .group_by(CampaignEmail.status)
        )
    ).all()
    counts = {status: int(count) for status, count in rows}
    sent = counts.get(EmailStatus.SENT.value, 0)
    failed = counts.get(EmailStatus.FAILED.value, 0)
    queued = sum(
        counts.get(status, 0)
        for status in (
            EmailStatus.QUEUED.value,
            EmailStatus.GENERATING.value,
            EmailStatus.READY.value,
            EmailStatus.SENDING.value,
        )
    )
    if (
        campaign.sent_count == sent
        and campaign.queued_count == queued
        and campaign.failed_count == failed
    ):
        return
    campaign.sent_count = sent
    campaign.queued_count = queued
    campaign.failed_count = failed
    await db.commit()
    await db.refresh(campaign)


def transition(campaign: Campaign, target: CampaignStatus) -> None:
    current = CampaignStatus(campaign.status)
    if target not in ALLOWED_TRANSITIONS[current]:
        raise AppError(
            "invalid_state",
            f"Cannot move campaign from {current.value} to {target.value}",
            409,
        )
    campaign.status = target.value


async def list_campaigns(db: AsyncSession, user: User, limit: int = 50) -> list[Campaign]:
    result = await db.scalars(
        select(Campaign)
        .where(Campaign.user_id == user.id)
        .order_by(Campaign.created_at.desc())
        .limit(limit)
    )
    campaigns = list(result)
    for campaign in campaigns:
        await sync_delivery_counts(db, campaign)
    return campaigns


async def _validate_relations(
    db: AsyncSession, user: User, payload: CampaignCreate | CampaignUpdate
) -> tuple[Template | None, list[Lead], list[SMTPAccount]]:
    template = None
    leads: list[Lead] = []
    accounts: list[SMTPAccount] = []

    template_id = getattr(payload, "template_id", None)
    if template_id:
        template = await db.scalar(
            select(Template).where(Template.id == template_id, Template.user_id == user.id)
        )
        if template is None:
            raise NotFoundError("Template not found")

    seen_lead_ids: set = set()
    group_ids = getattr(payload, "group_ids", None) or []
    audience = _audience_settings(payload)
    if group_ids:
        groups = list(
            (
                await db.scalars(
                    select(LeadGroup).where(
                        LeadGroup.user_id == user.id, LeadGroup.id.in_(group_ids)
                    )
                )
            ).all()
        )
        if len(groups) != len(set(group_ids)):
            raise NotFoundError("One or more lead groups were not found")
        grouped = await _leads_for_groups(db, user, groups, audience)
        for lead in grouped:
            if lead.id not in seen_lead_ids:
                seen_lead_ids.add(lead.id)
                leads.append(lead)

    lead_ids = getattr(payload, "lead_ids", None) or []
    if lead_ids:
        extra = list(
            (
                await db.scalars(
                    select(Lead).where(Lead.user_id == user.id, Lead.id.in_(lead_ids))
                )
            ).all()
        )
        if len(extra) != len(set(lead_ids)):
            raise NotFoundError("One or more leads were not found")
        for lead in extra:
            if lead.id not in seen_lead_ids:
                seen_lead_ids.add(lead.id)
                leads.append(lead)
    if audience is not None:
        leads = leads[: audience["max_recipients"]]

    smtp_ids = getattr(payload, "smtp_account_ids", None)
    if smtp_ids:
        accounts = list(
            (
                await db.scalars(
                    select(SMTPAccount).where(
                        SMTPAccount.user_id == user.id,
                        SMTPAccount.id.in_(smtp_ids),
                        SMTPAccount.is_active.is_(True),
                    )
                )
            ).all()
        )
        if len(accounts) != len(set(smtp_ids)):
            raise NotFoundError("One or more SMTP accounts were not found or are inactive")
    return template, leads, accounts


FOLLOW_UP_PURPOSES = {"sent", "failed"}


def _audience_settings(payload: CampaignCreate | CampaignUpdate) -> dict | None:
    if not isinstance(payload, CampaignCreate):
        return None
    return {
        "countries": [item.strip() for item in payload.countries if item.strip()],
        "study_opportunities": [item.strip() for item in payload.study_opportunities if item.strip()],
        "role_verified_only": payload.role_verified_only,
        "work_email_only": payload.work_email_only,
        "max_recipients": payload.max_recipients,
    }


def _apply_lead_filters(query, audience: dict | None):
    if not audience:
        return query
    if audience["countries"]:
        query = query.where(Lead.country.in_(audience["countries"]))
    if audience["study_opportunities"]:
        query = query.where(Lead.study_opportunity.in_(audience["study_opportunities"]))
    if audience["role_verified_only"]:
        query = query.where(Lead.role_verified.is_(True))
    if audience["work_email_only"]:
        query = query.where(Lead.email_kind == "work")
    return query


async def _leads_for_groups(
    db: AsyncSession, user: User, groups: list[LeadGroup], audience: dict | None
) -> list[Lead]:
    source_ids = [group.id for group in groups if (group.purpose or "source") not in FOLLOW_UP_PURPOSES]
    follow_ids = [group.id for group in groups if (group.purpose or "source") in FOLLOW_UP_PURPOSES]
    busy = (
        select(CampaignEmail.lead_id)
        .join(Campaign, Campaign.id == CampaignEmail.campaign_id)
        .where(
            Campaign.user_id == user.id,
            Campaign.status.in_([CampaignStatus.RUNNING.value, CampaignStatus.QUEUED.value]),
            CampaignEmail.status.in_(
                [
                    EmailStatus.QUEUED.value,
                    EmailStatus.GENERATING.value,
                    EmailStatus.READY.value,
                    EmailStatus.SENDING.value,
                ]
            ),
        )
    )
    already_sent = (
        select(CampaignEmail.lead_id)
        .join(Campaign, Campaign.id == CampaignEmail.campaign_id)
        .where(
            Campaign.user_id == user.id,
            CampaignEmail.status == EmailStatus.SENT.value,
        )
    )
    limit = audience["max_recipients"] if audience else 100000
    chosen: list[Lead] = []
    seen: set = set()

    async def take(group_ids: list, *, skip_sent: bool) -> None:
        if not group_ids or len(chosen) >= limit:
            return
        query = (
            select(Lead)
            .join(LeadGroupMember, LeadGroupMember.lead_id == Lead.id)
            .where(LeadGroupMember.group_id.in_(group_ids), Lead.user_id == user.id, Lead.is_valid.is_(True))
        )
        query = _apply_lead_filters(query, audience)
        query = query.where(Lead.id.not_in(busy))
        if skip_sent:
            query = query.where(Lead.id.not_in(already_sent))
        query = query.order_by(Lead.company, Lead.email).limit(limit)
        for lead in (await db.scalars(query)).all():
            if lead.id in seen:
                continue
            seen.add(lead.id)
            chosen.append(lead)
            if len(chosen) >= limit:
                break

    await take(follow_ids, skip_sent=False)
    await take(source_ids, skip_sent=audience is not None)
    return chosen


async def create_campaign(
    db: AsyncSession, user: User, payload: CampaignCreate
) -> Campaign:
    template, leads, accounts = await _validate_relations(db, user, payload)
    assert template is not None
    if not leads:
        raise AppError(
            "no_recipients",
            "No leads match this batch. People already sent are skipped until you select their Sent group.",
            400,
        )
    campaign = Campaign(
        user_id=user.id,
        name=payload.name,
        template_id=template.id,
        template_snapshot={
            "name": template.name,
            "subject": template.subject,
            "html_body": template.html_body,
            "text_body": template.text_body,
            "ai_instructions": template.ai_instructions,
        },
        ai_enabled=payload.ai_enabled,
        ai_instructions=payload.ai_instructions or template.ai_instructions,
        hourly_limit=payload.hourly_limit,
        daily_limit=payload.daily_limit,
        delay_seconds=payload.delay_seconds,
        scheduled_at=payload.scheduled_at,
        audience_filters={
            "countries": payload.countries,
            "study_opportunities": payload.study_opportunities,
            "role_verified_only": payload.role_verified_only,
            "work_email_only": payload.work_email_only,
            "max_recipients": payload.max_recipients,
        },
        total_count=len(leads),
    )
    db.add(campaign)
    await db.flush()
    for lead in leads:
        db.add(CampaignLead(campaign_id=campaign.id, lead_id=lead.id))
    for account in accounts:
        db.add(CampaignSMTP(campaign_id=campaign.id, smtp_account_id=account.id))
    await db.flush()
    logger.info("campaign_created", extra={"event": "campaign_created", "campaign_id": str(campaign.id)})
    return campaign


async def update_campaign(
    db: AsyncSession, user: User, campaign_id: UUID, payload: CampaignUpdate
) -> Campaign:
    campaign = await get_owned_campaign(db, user, campaign_id)
    if campaign.status != CampaignStatus.DRAFT.value:
        raise AppError("invalid_state", "Only draft campaigns can be edited", 409)
    template, leads, accounts = await _validate_relations(db, user, payload)
    data = payload.model_dump(
        exclude_unset=True, exclude={"lead_ids", "group_ids", "smtp_account_ids"}
    )
    for key, value in data.items():
        setattr(campaign, key, value)
    if template:
        campaign.template_id = template.id
        campaign.template_snapshot = {
            "name": template.name,
            "subject": template.subject,
            "html_body": template.html_body,
            "text_body": template.text_body,
            "ai_instructions": template.ai_instructions,
        }
    if leads:
        await db.execute(delete(CampaignLead).where(CampaignLead.campaign_id == campaign.id))
        for lead in leads:
            db.add(CampaignLead(campaign_id=campaign.id, lead_id=lead.id))
        campaign.total_count = len(leads)
    if accounts:
        await db.execute(delete(CampaignSMTP).where(CampaignSMTP.campaign_id == campaign.id))
        for account in accounts:
            db.add(CampaignSMTP(campaign_id=campaign.id, smtp_account_id=account.id))
    await db.flush()
    return campaign


async def queue_emails(db: AsyncSession, campaign: Campaign) -> int:
    existing = await db.scalar(
        select(func.count()).select_from(CampaignEmail).where(
            CampaignEmail.campaign_id == campaign.id
        )
    )
    if existing:
        return existing

    lead_ids = list(
        (
            await db.scalars(
                select(CampaignLead.lead_id).where(CampaignLead.campaign_id == campaign.id)
            )
        ).all()
    )
    suppressed = set(
        (
            await db.scalars(
                select(SuppressionEntry.email).where(SuppressionEntry.user_id == campaign.user_id)
            )
        ).all()
    )
    leads = list((await db.scalars(select(Lead).where(Lead.id.in_(lead_ids)))).all())
    created = 0
    for lead in leads:
        if lead.email in suppressed or not lead.is_valid:
            continue
        db.add(
            CampaignEmail(
                campaign_id=campaign.id,
                lead_id=lead.id,
                tracking_token=generate_tracking_token(),
                status=EmailStatus.QUEUED.value,
            )
        )
        created += 1
    campaign.queued_count = created
    campaign.total_count = created
    await db.flush()
    return created


async def start_campaign(db: AsyncSession, user: User, campaign_id: UUID) -> Campaign:
    campaign = await get_owned_campaign(db, user, campaign_id)
    if campaign.status in {CampaignStatus.RUNNING.value, CampaignStatus.QUEUED.value}:
        await db.refresh(campaign)
        return campaign
    transition(campaign, CampaignStatus.QUEUED)
    created = await queue_emails(db, campaign)
    if created == 0:
        campaign.status = CampaignStatus.FAILED.value
        campaign.failure_reason = "No eligible leads to send"
        raise AppError("no_recipients", "No eligible leads remain after suppression checks", 400)
    campaign.started_at = datetime.now(timezone.utc)
    campaign.status = CampaignStatus.RUNNING.value
    campaign.updated_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(campaign)
    logger.info("campaign_started", extra={"event": "campaign_started", "campaign_id": str(campaign.id)})
    return campaign


async def pause_campaign(db: AsyncSession, user: User, campaign_id: UUID) -> Campaign:
    campaign = await get_owned_campaign(db, user, campaign_id)
    transition(campaign, CampaignStatus.PAUSED)
    campaign.paused_at = datetime.now(timezone.utc)
    logger.info("campaign_paused", extra={"event": "campaign_paused", "campaign_id": str(campaign.id)})
    return campaign


async def resume_campaign(db: AsyncSession, user: User, campaign_id: UUID) -> Campaign:
    campaign = await get_owned_campaign(db, user, campaign_id)
    transition(campaign, CampaignStatus.RUNNING)
    campaign.paused_at = None
    return campaign


async def cancel_campaign(db: AsyncSession, user: User, campaign_id: UUID) -> Campaign:
    campaign = await get_owned_campaign(db, user, campaign_id)
    transition(campaign, CampaignStatus.CANCELLED)
    return campaign


async def _embed_preview_images(
    db: AsyncSession, settings: Settings, user_id: UUID, html_body: str
) -> str:
    keys = set(re.findall(r"\{\{\s*(asset_(?:img|link)_[a-zA-Z0-9]+)\s*\}\}", html_body or ""))
    if not keys:
        return html_body
    assets = list(
        (
            await db.scalars(
                select(CampaignAsset).where(
                    CampaignAsset.user_id == user_id,
                    CampaignAsset.placeholder_key.in_(keys),
                )
            )
        ).all()
    )
    return embed_preview_asset_urls(settings, assets, html_body)


async def preview_campaign(
    db: AsyncSession,
    settings: Settings,
    user: User,
    campaign_id: UUID,
    limit: int = 5,
) -> list[dict]:
    campaign = await get_owned_campaign(db, user, campaign_id)
    snapshot = campaign.template_snapshot or {}
    lead_ids = list(
        (
            await db.scalars(
                select(CampaignLead.lead_id)
                .where(CampaignLead.campaign_id == campaign.id)
                .limit(limit)
            )
        ).all()
    )
    leads = list((await db.scalars(select(Lead).where(Lead.id.in_(lead_ids)))).all())
    previews = []
    for lead in leads:
        context = apply_sender_context(
            lead_context(lead),
            from_name=user.full_name,
            company=user.company_name or "",
        )
        personalization = {}
        if campaign.ai_enabled:
            personalization = await asyncio.to_thread(
                generate_personalization,
                settings,
                context,
                campaign.ai_instructions,
                subject=snapshot.get("subject", ""),
                html_body=snapshot.get("html_body", ""),
                text_body=snapshot.get("text_body", ""),
            )
            context.update(
                {
                    key: personalization[key]
                    for key in ("opener", "signoff", "company_note")
                    if personalization.get(key)
                }
            )
            context = apply_sender_context(
                context,
                from_name=user.full_name,
                company=user.company_name or "",
            )
        html_body, text_body = wrap_outbound_email(
            render_template(
                personalization.get("html_body") or snapshot.get("html_body", ""), context
            ),
            render_template(
                personalization.get("text_body") or snapshot.get("text_body", ""), context
            ),
            from_name=user.full_name,
            company=user.company_name or "",
            physical_address=user.physical_address or "",
        )
        if campaign.template_id is not None:
            pdf_keys = list(
                (
                    await db.scalars(
                        select(CampaignAsset.placeholder_key).where(
                            CampaignAsset.user_id == user.id,
                            CampaignAsset.template_id == campaign.template_id,
                            CampaignAsset.kind == "pdf",
                        )
                    )
                ).all()
            )
            html_body = strip_pdf_placeholders(html_body, pdf_keys)
            text_body = strip_pdf_placeholders(text_body, pdf_keys)
        html_body = await _embed_preview_images(db, settings, user.id, html_body)
        previews.append(
            {
                "lead_id": lead.id,
                "email": lead.email,
                "subject": render_template(
                    personalization.get("subject") or snapshot.get("subject", ""), context
                ),
                "html_body": html_body,
                "text_body": text_body,
                "personalization": personalization,
            }
        )
    return previews


async def dashboard(db: AsyncSession, user: User) -> dict:
    campaigns = list(
        (
            await db.scalars(
                select(Campaign)
                .where(Campaign.user_id == user.id)
                .order_by(Campaign.created_at.desc())
                .limit(8)
            )
        ).all()
    )
    lead_count = await db.scalar(select(func.count()).select_from(Lead).where(Lead.user_id == user.id))
    active = await db.scalar(
        select(func.count())
        .select_from(Campaign)
        .where(
            Campaign.user_id == user.id,
            Campaign.status.in_(
                [CampaignStatus.RUNNING.value, CampaignStatus.QUEUED.value, CampaignStatus.PAUSED.value]
            ),
        )
    )
    totals = (
        await db.execute(
            select(
                func.coalesce(func.sum(Campaign.sent_count), 0),
                func.coalesce(func.sum(Campaign.open_count), 0),
                func.coalesce(func.sum(Campaign.click_count), 0),
                func.coalesce(func.sum(Campaign.failed_count), 0),
                func.coalesce(func.sum(Campaign.bounced_count), 0),
            ).where(Campaign.user_id == user.id)
        )
    ).one()
    return {
        "active_campaigns": active or 0,
        "total_leads": lead_count or 0,
        "emails_sent": int(totals[0]),
        "tracked_opens": int(totals[1]),
        "clicks": int(totals[2]),
        "failures": int(totals[3]),
        "bounce_signals": int(totals[4]),
        "recent_campaigns": campaigns,
    }
