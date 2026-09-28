from uuid import UUID

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.core.deps import AppSettings, CurrentUser, DB
from app.models.campaign import CampaignEmail, CampaignSMTP
from app.models.enums import EventType, SignalClassification
from app.models.lead import Lead
from app.models.tracking import CampaignAsset, EmailEvent, TrackedLink, TrackingRequest
from app.schemas.campaign import (
    AnalyticsOut,
    AssetActivityOut,
    CampaignCreate,
    CampaignEmailOut,
    CampaignOut,
    CampaignPreviewOut,
    CampaignTestEmail,
    CampaignUpdate,
    TimelineEventOut,
    TrackedLinkOut,
    TrackingRequestOut,
)
from app.schemas.common import SuccessResponse
from app.services import campaign_service, smtp_service
from app.services.tracking_service import (
    classification_for_label,
    display_classification,
    open_label_from_requests,
)
from app.workers.email_tasks import dispatch_running_campaigns

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


@router.get("", response_model=SuccessResponse[list[CampaignOut]])
async def list_campaigns(user: CurrentUser, db: DB):
    rows = await campaign_service.list_campaigns(db, user)
    return SuccessResponse(data=[CampaignOut.model_validate(c) for c in rows])


@router.post("", response_model=SuccessResponse[CampaignOut])
async def create_campaign(payload: CampaignCreate, user: CurrentUser, db: DB):
    campaign = await campaign_service.create_campaign(db, user, payload)
    return SuccessResponse(data=CampaignOut.model_validate(campaign))


@router.get("/{campaign_id}", response_model=SuccessResponse[CampaignOut])
async def get_campaign(campaign_id: UUID, user: CurrentUser, db: DB):
    campaign = await campaign_service.get_owned_campaign(db, user, campaign_id)
    return SuccessResponse(data=CampaignOut.model_validate(campaign))


@router.patch("/{campaign_id}", response_model=SuccessResponse[CampaignOut])
async def update_campaign(
    campaign_id: UUID, payload: CampaignUpdate, user: CurrentUser, db: DB
):
    campaign = await campaign_service.update_campaign(db, user, campaign_id, payload)
    return SuccessResponse(data=CampaignOut.model_validate(campaign))


@router.post("/{campaign_id}/start", response_model=SuccessResponse[CampaignOut])
async def start_campaign(campaign_id: UUID, user: CurrentUser, db: DB):
    campaign = await campaign_service.start_campaign(db, user, campaign_id)
    try:
        dispatch_running_campaigns.delay()
    except Exception:
        pass
    await db.refresh(campaign)
    return SuccessResponse(data=CampaignOut.model_validate(campaign))


@router.post("/{campaign_id}/pause", response_model=SuccessResponse[CampaignOut])
async def pause_campaign(campaign_id: UUID, user: CurrentUser, db: DB):
    campaign = await campaign_service.pause_campaign(db, user, campaign_id)
    await db.refresh(campaign)
    return SuccessResponse(data=CampaignOut.model_validate(campaign))


@router.post("/{campaign_id}/resume", response_model=SuccessResponse[CampaignOut])
async def resume_campaign(campaign_id: UUID, user: CurrentUser, db: DB):
    campaign = await campaign_service.resume_campaign(db, user, campaign_id)
    try:
        dispatch_running_campaigns.delay()
    except Exception:
        pass
    await db.refresh(campaign)
    return SuccessResponse(data=CampaignOut.model_validate(campaign))


@router.post("/{campaign_id}/cancel", response_model=SuccessResponse[CampaignOut])
async def cancel_campaign(campaign_id: UUID, user: CurrentUser, db: DB):
    campaign = await campaign_service.cancel_campaign(db, user, campaign_id)
    await db.refresh(campaign)
    return SuccessResponse(data=CampaignOut.model_validate(campaign))


@router.get("/{campaign_id}/preview", response_model=SuccessResponse[list[CampaignPreviewOut]])
async def preview(campaign_id: UUID, user: CurrentUser, db: DB, settings: AppSettings):
    rows = await campaign_service.preview_campaign(db, settings, user, campaign_id)
    return SuccessResponse(data=[CampaignPreviewOut(**row) for row in rows])


@router.post("/{campaign_id}/test-email")
async def test_email(
    campaign_id: UUID,
    payload: CampaignTestEmail,
    user: CurrentUser,
    db: DB,
    settings: AppSettings,
):
    campaign = await campaign_service.get_owned_campaign(db, user, campaign_id)
    previews = await campaign_service.preview_campaign(db, settings, user, campaign_id, limit=1)
    if not previews:
        from app.core.exceptions import AppError

        raise AppError("no_preview", "Add at least one lead before sending a test email", 400)
    preview_row = previews[0]
    smtp_link = (
        await db.scalars(
            select(CampaignSMTP).where(CampaignSMTP.campaign_id == campaign.id)
        )
    ).first()
    if smtp_link is None:
        from app.core.exceptions import AppError

        raise AppError("no_smtp", "Select an SMTP account first", 400)
    await smtp_service.send_test_email(
        db,
        settings,
        user,
        smtp_link.smtp_account_id,
        payload.to_email,
        subject=f"[TEST] {preview_row['subject']}",
        html_body=preview_row["html_body"],
        text_body=preview_row["text_body"],
    )
    return {"data": {"ok": True}}


def _asset_activity_map(
    requests: list[TrackingRequest], assets_by_id: dict
) -> dict[UUID, AssetActivityOut]:
    by_asset: dict[UUID, AssetActivityOut] = {}
    for req in requests:
        if req.asset_id is None:
            continue
        asset = assets_by_id.get(req.asset_id)
        if asset is None:
            continue
        row = by_asset.get(req.asset_id)
        if row is None:
            row = AssetActivityOut(
                asset_id=asset.id,
                filename=asset.original_filename,
                kind=asset.kind,
                access_count=0,
                download_count=0,
            )
            by_asset[req.asset_id] = row
        row.access_count += 1
        if req.request_type == "image_loaded":
            row.image_loads += 1
        elif req.request_type == "pdf_accessed":
            row.pdf_accesses += 1
        elif req.request_type == "download_requested":
            row.downloads += 1
            row.download_count += 1
    return by_asset


@router.get("/{campaign_id}/emails", response_model=SuccessResponse[list[CampaignEmailOut]])
async def list_emails(
    campaign_id: UUID,
    user: CurrentUser,
    db: DB,
    limit: int = Query(default=50, ge=1, le=200),
):
    campaign = await campaign_service.get_owned_campaign(db, user, campaign_id)
    rows = list(
        (
            await db.scalars(
                select(CampaignEmail)
                .where(CampaignEmail.campaign_id == campaign.id)
                .order_by(CampaignEmail.created_at.desc())
                .limit(limit)
            )
        ).all()
    )
    email_ids = [row.id for row in rows]
    lead_ids = [row.lead_id for row in rows]
    leads = {
        lead.id: lead.email
        for lead in (await db.scalars(select(Lead).where(Lead.id.in_(lead_ids)))).all()
    } if lead_ids else {}

    open_events = (
        list(
            (
                await db.scalars(
                    select(EmailEvent)
                    .where(
                        EmailEvent.email_id.in_(email_ids),
                        EmailEvent.event_type == EventType.OPENED.value,
                    )
                    .order_by(EmailEvent.created_at)
                )
            ).all()
        )
        if email_ids
        else []
    )
    first_open_by_email = {}
    for event in open_events:
        first_open_by_email.setdefault(event.email_id, event)

    requests = (
        list(
            (
                await db.scalars(
                    select(TrackingRequest)
                    .where(TrackingRequest.email_id.in_(email_ids))
                    .order_by(TrackingRequest.created_at.desc())
                )
            ).all()
        )
        if email_ids
        else []
    )
    requests_by_email: dict = {}
    for req in requests:
        requests_by_email.setdefault(req.email_id, []).append(req)

    links = (
        list(
            (await db.scalars(select(TrackedLink).where(TrackedLink.email_id.in_(email_ids)))).all()
        )
        if email_ids
        else []
    )
    links_by_email: dict = {}
    for link in links:
        links_by_email.setdefault(link.email_id, []).append(link)

    asset_ids = {req.asset_id for req in requests if req.asset_id} | {
        link.asset_id for link in links if link.asset_id
    }
    assets_by_id = {
        asset.id: asset
        for asset in (
            await db.scalars(select(CampaignAsset).where(CampaignAsset.id.in_(asset_ids)))
        ).all()
    } if asset_ids else {}

    payload = []
    for row in rows:
        open_event = first_open_by_email.get(row.id)
        email_requests = requests_by_email.get(row.id, [])
        open_reqs = [
            r
            for r in email_requests
            if r.request_type in {"open_pixel", "view_email", "link_click"}
        ]
        classifications = [
            classification_for_label(r.classification, r.seconds_after_send) for r in open_reqs
        ]
        open_classification = open_label_from_requests(classifications)
        if open_event is not None and open_classification == "none":
            open_classification = open_label_from_requests(
                [open_event.classification]
                if open_event.classification
                else ["proxy_or_uncertain"]
            )

        strongest_req = None
        order = {
            SignalClassification.POSSIBLE_HUMAN.value: 3,
            SignalClassification.PROXY_OR_UNCERTAIN.value: 2,
            SignalClassification.AUTOMATED.value: 1,
        }
        for req in open_reqs:
            if strongest_req is None or order.get(req.classification, 0) >= order.get(
                strongest_req.classification, 0
            ):
                strongest_req = req

        latest_open = open_reqs[0] if open_reqs else None
        email_links = [
            TrackedLinkOut(
                destination_url=link.destination_url,
                click_count=link.click_count,
                clicked=link.click_count > 0,
                asset_id=link.asset_id,
            )
            for link in links_by_email.get(row.id, [])
        ]
        asset_map = _asset_activity_map(email_requests, assets_by_id)
        request_outs = [
            TrackingRequestOut(
                id=req.id,
                request_type=req.request_type,
                classification=classification_for_label(
                    req.classification, req.seconds_after_send
                ),
                confidence=req.confidence,
                classification_reasons=req.classification_reasons or [],
                seconds_after_send=req.seconds_after_send,
                user_agent=req.user_agent,
                created_at=req.created_at,
                asset_id=req.asset_id,
                filename=(
                    assets_by_id[req.asset_id].original_filename
                    if req.asset_id and req.asset_id in assets_by_id
                    else None
                ),
            )
            for req in email_requests[:40]
        ]
        first_open_at = None
        if open_event:
            first_open_at = open_event.created_at
        elif open_reqs:
            first_open_at = open_reqs[-1].created_at
        payload.append(
            CampaignEmailOut(
                id=row.id,
                campaign_id=row.campaign_id,
                lead_id=row.lead_id,
                recipient_email=leads.get(row.lead_id, ""),
                status=row.status,
                subject=row.subject,
                error_message=row.error_message,
                sent_at=row.sent_at,
                created_at=row.created_at,
                opened=open_event is not None or bool(open_reqs),
                opened_at=first_open_at,
                latest_open_at=latest_open.created_at if latest_open else None,
                open_classification=open_classification,
                open_request_count=len(open_reqs),
                open_confidence=strongest_req.confidence if strongest_req else None,
                open_reasons=(strongest_req.classification_reasons if strongest_req else []) or [],
                clicked=any(item.clicked for item in email_links),
                click_count=sum(item.click_count for item in email_links),
                links=email_links,
                assets=list(asset_map.values()),
                requests=request_outs,
            )
        )
    return SuccessResponse(data=payload)


@router.get("/{campaign_id}/analytics", response_model=SuccessResponse[AnalyticsOut])
async def analytics(campaign_id: UUID, user: CurrentUser, db: DB):
    campaign = await campaign_service.get_owned_campaign(db, user, campaign_id)
    sent = campaign.sent_count

    emails = list(
        (await db.scalars(select(CampaignEmail).where(CampaignEmail.campaign_id == campaign.id))).all()
    )
    email_ids = [e.id for e in emails]
    leads = {
        lead.id: lead.email
        for lead in (
            await db.scalars(select(Lead).where(Lead.id.in_([e.lead_id for e in emails])))
        ).all()
    } if emails else {}

    requests = (
        list(
            (
                await db.scalars(
                    select(TrackingRequest)
                    .where(TrackingRequest.campaign_id == campaign.id)
                    .order_by(TrackingRequest.created_at.desc())
                )
            ).all()
        )
        if email_ids
        else []
    )
    open_events = (
        list(
            (
                await db.scalars(
                    select(EmailEvent).where(
                        EmailEvent.campaign_id == campaign.id,
                        EmailEvent.event_type == EventType.OPENED.value,
                    )
                )
            ).all()
        )
        if email_ids
        else []
    )

    reqs_by_email: dict = {}
    for req in requests:
        if req.request_type in {"open_pixel", "view_email"}:
            reqs_by_email.setdefault(req.email_id, []).append(
                classification_for_label(req.classification, req.seconds_after_send)
            )

    automated = uncertain = possible = 0
    for event in open_events:
        label = open_label_from_requests(reqs_by_email.get(event.email_id, []))
        if label == "likely_automated":
            automated += 1
        elif label == "possible_human":
            possible += 1
        else:
            uncertain += 1

    asset_ids = {req.asset_id for req in requests if req.asset_id}
    assets_by_id = {
        asset.id: asset
        for asset in (
            await db.scalars(select(CampaignAsset).where(CampaignAsset.id.in_(asset_ids)))
        ).all()
    } if asset_ids else {}
    asset_activity = list(_asset_activity_map(requests, assets_by_id).values())

    timeline_events = list(
        (
            await db.scalars(
                select(EmailEvent)
                .where(EmailEvent.campaign_id == campaign.id)
                .order_by(EmailEvent.created_at.desc())
                .limit(100)
            )
        ).all()
    )
    email_by_id = {e.id: e for e in emails}
    timeline = [
        TimelineEventOut(
            id=ev.id,
            email_id=ev.email_id,
            recipient_email=leads.get(email_by_id[ev.email_id].lead_id)
            if ev.email_id in email_by_id
            else None,
            event_type=ev.event_type,
            classification=display_classification(
                ev.classification, ev.classification_reasons
            ),
            confidence=ev.confidence,
            classification_reasons=ev.classification_reasons or [],
            created_at=ev.created_at,
            metadata_json=ev.metadata_json or {},
            filename=(ev.metadata_json or {}).get("filename"),
        )
        for ev in timeline_events
    ]

    image_loads = sum(1 for r in requests if r.request_type == "image_loaded")
    pdf_accesses = sum(1 for r in requests if r.request_type == "pdf_accessed")
    downloads = sum(1 for r in requests if r.request_type == "download_requested")
    open_requests = sum(1 for r in requests if r.request_type in {"open_pixel", "view_email"})

    return SuccessResponse(
        data=AnalyticsOut(
            campaign=CampaignOut.model_validate(campaign),
            sent=sent,
            queued=campaign.queued_count,
            failed=campaign.failed_count,
            bounced=campaign.bounced_count,
            tracked_opens=campaign.open_count,
            open_requests=open_requests,
            automated_opens=automated,
            uncertain_opens=uncertain,
            possible_human_opens=possible,
            clicks=campaign.click_count,
            image_loads=image_loads,
            pdf_accesses=pdf_accesses,
            downloads=downloads,
            unsubscribes=campaign.unsubscribe_count,
            open_rate=(campaign.open_count / sent) if sent else 0,
            click_rate=(campaign.click_count / sent) if sent else 0,
            assets=asset_activity,
            timeline=timeline,
        )
    )
