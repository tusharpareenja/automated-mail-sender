"""Authenticated media serving for template asset previews."""

from uuid import UUID

from fastapi import APIRouter
from fastapi.responses import Response

from app.core.deps import AppSettings, CurrentUser, DB
from app.services import asset_service
from app.services.asset_storage import load_asset_bytes

router = APIRouter(prefix="/media", tags=["media"])


@router.get("/assets/{asset_id}")
async def get_media_asset(
    asset_id: UUID,
    user: CurrentUser,
    db: DB,
    settings: AppSettings,
):
    asset = await asset_service.get_owned_asset(db, user, asset_id)
    data, _hint = load_asset_bytes(settings, user.id, asset.stored_filename)
    return Response(
        content=data,
        media_type=asset.content_type,
        headers={
            "Cache-Control": "private, max-age=120",
            "Content-Disposition": f'inline; filename="{asset.original_filename}"',
        },
    )
