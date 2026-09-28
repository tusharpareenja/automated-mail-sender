from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import Cookie, Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.security import (
    ACCESS_COOKIE,
    CSRF_COOKIE,
    CSRF_HEADER,
    csrf_tokens_match,
    decode_token,
)
from app.models.user import User

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


async def get_current_user(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    access_token: Annotated[str | None, Cookie()] = None,
    authorization: Annotated[str | None, Header()] = None,
    csrf_cookie: Annotated[str | None, Cookie(alias=CSRF_COOKIE)] = None,
    csrf_header: Annotated[str | None, Header(alias=CSRF_HEADER)] = None,
) -> User:
    token = None
    used_cookie = False
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
    elif access_token:
        token = access_token
        used_cookie = True
    if not token:
        raise UnauthorizedError()

    if used_cookie and request.method not in SAFE_METHODS:
        if not csrf_tokens_match(csrf_cookie, csrf_header):
            raise ForbiddenError("CSRF validation failed")

    try:
        payload = decode_token(settings, token, "access")
        user_id = UUID(payload["sub"])
    except (ValueError, KeyError) as exc:
        raise UnauthorizedError("Invalid or expired session") from exc

    user = await db.scalar(select(User).where(User.id == user_id))
    if user is None or not user.is_active:
        raise UnauthorizedError("Account is inactive or does not exist")
    return user


def require_owner(user: User, resource_user_id: UUID) -> None:
    if resource_user_id != user.id:
        raise ForbiddenError()


CurrentUser = Annotated[User, Depends(get_current_user)]
DB = Annotated[AsyncSession, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]
