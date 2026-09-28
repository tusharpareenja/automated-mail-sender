from fastapi import APIRouter
from sqlalchemy import select

from app.core.deps import CurrentUser, DB
from app.models.tracking import EmailEvent
from app.schemas.campaign import DashboardOut, EventOut
from app.schemas.common import SuccessResponse
from app.services.campaign_service import dashboard

router = APIRouter(tags=["analytics"])


@router.get("/dashboard", response_model=SuccessResponse[DashboardOut])
async def get_dashboard(user: CurrentUser, db: DB):
    data = await dashboard(db, user)
    return SuccessResponse(
        data=DashboardOut(
            active_campaigns=data["active_campaigns"],
            total_leads=data["total_leads"],
            emails_sent=data["emails_sent"],
            tracked_opens=data["tracked_opens"],
            clicks=data["clicks"],
            failures=data["failures"],
            bounce_signals=data["bounce_signals"],
            recent_campaigns=data["recent_campaigns"],
        )
    )


@router.get("/events", response_model=SuccessResponse[list[EventOut]])
async def recent_events(user: CurrentUser, db: DB):
    rows = list(
        (
            await db.scalars(
                select(EmailEvent)
                .where(EmailEvent.user_id == user.id)
                .order_by(EmailEvent.created_at.desc())
                .limit(40)
            )
        ).all()
    )
    return SuccessResponse(data=[EventOut.model_validate(r) for r in rows])
