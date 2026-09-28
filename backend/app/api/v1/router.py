from fastapi import APIRouter

from app.api.v1 import analytics, auth, campaigns, leads, media, smtp, templates, tracking, websocket

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(smtp.router)
api_router.include_router(templates.router)
api_router.include_router(media.router)
api_router.include_router(leads.router)
api_router.include_router(campaigns.router)
api_router.include_router(analytics.router)
api_router.include_router(websocket.router)

public_router = APIRouter()
public_router.include_router(tracking.router)
