import logging
from datetime import datetime, timedelta, timezone

from fastapi import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import AppError, ConflictError, NotFoundError, UnauthorizedError
from app.core.security import (
    ACCESS_COOKIE,
    CSRF_COOKIE,
    REFRESH_COOKIE,
    create_access_token,
    generate_csrf_token,
    generate_refresh_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.models.user import EmailVerificationToken, PasswordResetToken, RefreshSession, User
from app.schemas.auth import LoginRequest, RegisterRequest, ResetPasswordRequest

logger = logging.getLogger(__name__)


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _set_auth_cookies(
    response: Response,
    settings: Settings,
    access_token: str,
    refresh_token: str,
    csrf_token: str,
) -> None:
    cookie_kwargs = {
        "httponly": True,
        "secure": settings.cookie_secure or settings.is_production,
        "samesite": settings.cookie_samesite,
        "path": "/",
    }
    response.set_cookie(
        ACCESS_COOKIE,
        access_token,
        max_age=settings.access_token_minutes * 60,
        **cookie_kwargs,
    )
    response.set_cookie(
        REFRESH_COOKIE,
        refresh_token,
        max_age=settings.refresh_token_days * 86400,
        **cookie_kwargs,
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf_token,
        max_age=settings.refresh_token_days * 86400,
        httponly=False,
        secure=settings.cookie_secure or settings.is_production,
        samesite=settings.cookie_samesite,
        path="/",
    )


def clear_auth_cookies(response: Response) -> None:
    for name in (ACCESS_COOKIE, REFRESH_COOKIE, CSRF_COOKIE):
        response.delete_cookie(name, path="/")


async def register_user(db: AsyncSession, payload: RegisterRequest) -> User:
    email = _normalize_email(payload.email)
    existing = await db.scalar(select(User).where(User.email == email))
    if existing:
        raise ConflictError("An account with this email already exists")
    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name.strip(),
        company_name=payload.company_name,
        is_verified=False,
    )
    db.add(user)
    await db.flush()
    token = generate_refresh_token()
    db.add(
        EmailVerificationToken(
            user_id=user.id,
            token_hash=hash_token(token),
            expires_at=datetime.now(timezone.utc) + timedelta(days=2),
        )
    )
    logger.info("user_registered", extra={"event": "user_registered", "user_id": str(user.id)})
    user._verification_token = token  # type: ignore[attr-defined]
    return user


async def authenticate(db: AsyncSession, payload: LoginRequest) -> User:
    email = _normalize_email(payload.email)
    user = await db.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise UnauthorizedError("Invalid email or password")
    if not user.is_active:
        raise UnauthorizedError("Account is disabled")
    return user


async def issue_session(
    db: AsyncSession,
    settings: Settings,
    response: Response,
    user: User,
    user_agent: str | None,
    ip_address: str | None,
) -> None:
    refresh = generate_refresh_token()
    session = RefreshSession(
        user_id=user.id,
        token_hash=hash_token(refresh),
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_days),
        user_agent=user_agent,
        ip_address=ip_address,
    )
    db.add(session)
    await db.flush()
    access = create_access_token(settings, user.id)
    _set_auth_cookies(response, settings, access, refresh, generate_csrf_token())


async def refresh_session(
    db: AsyncSession,
    settings: Settings,
    response: Response,
    refresh_token: str | None,
    user_agent: str | None,
    ip_address: str | None,
) -> User:
    if not refresh_token:
        raise UnauthorizedError("Missing refresh session")
    token_hash = hash_token(refresh_token)
    session = await db.scalar(select(RefreshSession).where(RefreshSession.token_hash == token_hash))
    now = datetime.now(timezone.utc)
    if session is None or session.revoked_at is not None or session.expires_at <= now:
        raise UnauthorizedError("Refresh session is invalid")
    session.revoked_at = now
    user = await db.scalar(select(User).where(User.id == session.user_id))
    if user is None or not user.is_active:
        raise UnauthorizedError("Account is inactive")
    await issue_session(db, settings, response, user, user_agent, ip_address)
    return user


async def logout_session(db: AsyncSession, refresh_token: str | None, response: Response) -> None:
    if refresh_token:
        session = await db.scalar(
            select(RefreshSession).where(RefreshSession.token_hash == hash_token(refresh_token))
        )
        if session and session.revoked_at is None:
            session.revoked_at = datetime.now(timezone.utc)
    clear_auth_cookies(response)


async def request_password_reset(db: AsyncSession, email: str) -> str | None:
    user = await db.scalar(select(User).where(User.email == _normalize_email(email)))
    if user is None:
        return None
    token = generate_refresh_token()
    db.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=hash_token(token),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
    )
    logger.info("password_reset_requested", extra={"event": "password_reset_requested"})
    return token


async def reset_password(db: AsyncSession, payload: ResetPasswordRequest) -> None:
    token_hash = hash_token(payload.token)
    record = await db.scalar(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash)
    )
    now = datetime.now(timezone.utc)
    if record is None or record.used_at is not None or record.expires_at <= now:
        raise AppError("invalid_token", "Reset token is invalid or expired", 400)
    user = await db.scalar(select(User).where(User.id == record.user_id))
    if user is None:
        raise NotFoundError("User not found")
    user.password_hash = hash_password(payload.password)
    record.used_at = now
    sessions = (
        await db.scalars(select(RefreshSession).where(RefreshSession.user_id == user.id))
    ).all()
    for session in sessions:
        if session.revoked_at is None:
            session.revoked_at = now


async def verify_email(db: AsyncSession, token: str) -> None:
    record = await db.scalar(
        select(EmailVerificationToken).where(
            EmailVerificationToken.token_hash == hash_token(token)
        )
    )
    now = datetime.now(timezone.utc)
    if record is None or record.used_at is not None or record.expires_at <= now:
        raise AppError("invalid_token", "Verification token is invalid or expired", 400)
    user = await db.scalar(select(User).where(User.id == record.user_id))
    if user is None:
        raise NotFoundError()
    user.is_verified = True
    record.used_at = now
