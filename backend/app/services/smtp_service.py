import logging
import smtplib
import ssl
from datetime import datetime, timezone
from email.message import EmailMessage
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import NotFoundError, ProviderError
from app.core.security import decrypt_secret, encrypt_secret
from app.models.enums import SMTPHealth
from app.models.smtp import SMTPAccount
from app.models.user import User
from app.schemas.smtp import SMTPCreate, SMTPUpdate

logger = logging.getLogger(__name__)


def _to_out(account: SMTPAccount):
    from app.schemas.smtp import SMTPOut

    return SMTPOut.model_validate(account)


async def get_owned_smtp(db: AsyncSession, user: User, smtp_id: UUID) -> SMTPAccount:
    account = await db.scalar(
        select(SMTPAccount).where(SMTPAccount.id == smtp_id, SMTPAccount.user_id == user.id)
    )
    if account is None:
        raise NotFoundError("SMTP account not found")
    return account


async def list_smtp(db: AsyncSession, user: User) -> list[SMTPAccount]:
    result = await db.scalars(
        select(SMTPAccount)
        .where(SMTPAccount.user_id == user.id)
        .order_by(SMTPAccount.created_at.desc())
    )
    return list(result)


async def create_smtp(
    db: AsyncSession, settings: Settings, user: User, payload: SMTPCreate
) -> SMTPAccount:
    account = SMTPAccount(
        user_id=user.id,
        name=payload.name,
        host=payload.host,
        port=payload.port,
        username=payload.username,
        password_encrypted=encrypt_secret(settings, payload.password),
        from_email=payload.from_email,
        from_name=payload.from_name,
        use_tls=payload.use_tls,
        use_ssl=payload.use_ssl,
        hourly_limit=payload.hourly_limit,
        daily_limit=payload.daily_limit,
    )
    db.add(account)
    await db.flush()
    return account


async def update_smtp(
    db: AsyncSession,
    settings: Settings,
    user: User,
    smtp_id: UUID,
    payload: SMTPUpdate,
) -> SMTPAccount:
    account = await get_owned_smtp(db, user, smtp_id)
    data = payload.model_dump(exclude_unset=True)
    password = data.pop("password", None)
    for key, value in data.items():
        setattr(account, key, value)
    if password:
        account.password_encrypted = encrypt_secret(settings, password)
    await db.flush()
    return account


async def delete_smtp(db: AsyncSession, user: User, smtp_id: UUID) -> None:
    account = await get_owned_smtp(db, user, smtp_id)
    await db.delete(account)


def build_message(
    account: SMTPAccount,
    to_email: str,
    subject: str,
    html_body: str,
    text_body: str,
    message_id: str | None = None,
    extra_headers: dict[str, str] | None = None,
    attachments: list[tuple[str, str, bytes]] | None = None,
) -> EmailMessage:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = (
        f"{account.from_name} <{account.from_email}>" if account.from_name else account.from_email
    )
    message["To"] = to_email
    if message_id:
        message["Message-ID"] = message_id
    if extra_headers:
        for key, value in extra_headers.items():
            message[key] = value

    files = attachments or []
    if files:
        message.make_mixed()
        body = EmailMessage()
        body.set_content(text_body or " ", charset="utf-8")
        body.add_alternative(html_body, subtype="html", charset="utf-8")
        message.attach(body)
    else:
        message.set_content(text_body or " ", charset="utf-8")
        message.add_alternative(html_body, subtype="html", charset="utf-8")

    for filename, content_type, data in files:
        if "/" in (content_type or ""):
            maintype, subtype = content_type.split("/", 1)
        else:
            maintype, subtype = "application", "octet-stream"
        message.add_attachment(
            data,
            maintype=maintype,
            subtype=subtype,
            filename=filename,
            disposition="attachment",
        )
    return message


def send_via_smtp(
    settings: Settings,
    account: SMTPAccount,
    to_email: str,
    subject: str,
    html_body: str,
    text_body: str,
    message_id: str | None = None,
    extra_headers: dict[str, str] | None = None,
    attachments: list[tuple[str, str, bytes]] | None = None,
) -> None:
    password = decrypt_secret(settings, account.password_encrypted)
    message = build_message(
        account,
        to_email,
        subject,
        html_body,
        text_body,
        message_id=message_id,
        extra_headers=extra_headers,
        attachments=attachments,
    )

    context = ssl.create_default_context()
    try:
        if account.use_ssl:
            with smtplib.SMTP_SSL(account.host, account.port, timeout=20, context=context) as smtp:
                smtp.login(account.username, password)
                smtp.send_message(message)
        else:
            with smtplib.SMTP(account.host, account.port, timeout=20) as smtp:
                smtp.ehlo()
                if account.use_tls:
                    smtp.starttls(context=context)
                    smtp.ehlo()
                smtp.login(account.username, password)
                smtp.send_message(message)
    except smtplib.SMTPAuthenticationError as exc:
        raise ProviderError("SMTP authentication failed") from exc
    except smtplib.SMTPException as exc:
        raise ProviderError("SMTP provider rejected the message") from exc
    except OSError as exc:
        raise ProviderError("Could not reach the SMTP server") from exc


async def test_connection(
    db: AsyncSession, settings: Settings, user: User, smtp_id: UUID
) -> SMTPAccount:
    account = await get_owned_smtp(db, user, smtp_id)
    try:
        send_via_smtp(
            settings,
            account,
            account.from_email,
            "SMTP connection test",
            "<p>Connection test succeeded.</p>",
            "Connection test succeeded.",
        )
        account.health_status = SMTPHealth.HEALTHY.value
        account.consecutive_failures = 0
        account.last_error = None
        account.last_tested_at = datetime.now(timezone.utc)
    except ProviderError as exc:
        account.consecutive_failures += 1
        account.last_error = exc.message
        account.last_tested_at = datetime.now(timezone.utc)
        account.health_status = (
            SMTPHealth.UNHEALTHY.value
            if account.consecutive_failures >= 3
            else SMTPHealth.DEGRADED.value
        )
        raise
    return account


async def send_test_email(
    db: AsyncSession,
    settings: Settings,
    user: User,
    smtp_id: UUID,
    to_email: str,
    subject: str = "Test email",
    html_body: str = "<p>This is a test email from your campaign platform.</p>",
    text_body: str = "This is a test email from your campaign platform.",
) -> None:
    account = await get_owned_smtp(db, user, smtp_id)
    if not account.is_active:
        raise ProviderError("SMTP account is inactive")
    send_via_smtp(settings, account, to_email, subject, html_body, text_body)
    account.last_tested_at = datetime.now(timezone.utc)
    account.health_status = SMTPHealth.HEALTHY.value
    account.consecutive_failures = 0
    account.last_error = None
