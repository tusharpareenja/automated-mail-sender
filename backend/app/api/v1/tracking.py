from pathlib import Path

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import select

from app.core.config import get_settings
from app.core.deps import DB
from app.core.runtime import get_public_url, is_local_url
from app.models.campaign import CampaignEmail
from app.services.asset_storage import load_asset_bytes
from app.services.tracking_service import (
    TRANSPARENT_PNG,
    extract_client_signal,
    record_asset_access,
    record_click,
    record_open,
    unsubscribe,
)

router = APIRouter(tags=["tracking"])

_PIXEL_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
}


def _pixel() -> Response:
    return Response(content=TRANSPARENT_PNG, media_type="image/png", headers=_PIXEL_HEADERS)


@router.get("/t/status")
async def tracking_status():
    url = get_public_url()
    return {"data": {"public_url": url, "is_local": is_local_url(url)}}


@router.get("/t/o/{token}.png")
async def open_pixel(token: str, request: Request, db: DB):
    await record_open(db, token, signal=extract_client_signal(request), source="pixel")
    return _pixel()


@router.get("/t/o/{token}")
async def open_pixel_plain(token: str, request: Request, db: DB):
    await record_open(db, token, signal=extract_client_signal(request), source="pixel")
    return _pixel()


@router.get("/t/v/{token}")
async def view_email(token: str, request: Request, db: DB):
    email = await record_open(db, token, signal=extract_client_signal(request), source="view")
    if email is None:
        email = await db.scalar(select(CampaignEmail).where(CampaignEmail.tracking_token == token))
    body = (email.html_body if email else "") or "<p>This email is no longer available.</p>"
    return HTMLResponse(body)


@router.get("/t/c/{token}")
async def click_redirect(token: str, request: Request, db: DB):
    url = await record_click(db, token, signal=extract_client_signal(request))
    return RedirectResponse(url=url, status_code=302)


@router.get("/t/a/{token}")
async def asset_delivery(
    token: str,
    request: Request,
    db: DB,
    download: bool = Query(default=False),
):
    settings = get_settings()
    asset, _delivery, email = await record_asset_access(
        db,
        token,
        download=download,
        signal=extract_client_signal(request),
        settings=settings,
    )
    data, _hint = load_asset_bytes(settings, asset.user_id, asset.stored_filename)
    if download:
        headers = {
            "Cache-Control": "private, no-store",
            "Content-Disposition": (
                f'attachment; filename="{Path(asset.original_filename).name}"'
            ),
        }
    else:
        # Public caching lets mailbox image proxies display the picture.
        headers = {
            "Cache-Control": "public, max-age=86400",
            "Content-Disposition": "inline",
        }
    return Response(
        content=data,
        media_type=asset.content_type,
        headers=headers,
    )


@router.api_route("/unsubscribe/{token}", methods=["GET", "POST"])
async def unsubscribe_route(token: str, db: DB):
    await unsubscribe(db, token)
    return HTMLResponse(
        "<html><body style='font-family:sans-serif;padding:48px'>"
        "<h1>You have been unsubscribed</h1>"
        "<p>You will no longer receive emails from this sender.</p>"
        "</body></html>"
    )
