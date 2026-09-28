from uuid import UUID

from fastapi import APIRouter

from app.core.deps import AppSettings, CurrentUser, DB
from app.schemas.common import SuccessResponse
from app.schemas.smtp import SMTPCreate, SMTPOut, SMTPTestEmail, SMTPUpdate
from app.services import smtp_service

router = APIRouter(prefix="/smtp", tags=["smtp"])


@router.get("", response_model=SuccessResponse[list[SMTPOut]])
async def list_accounts(user: CurrentUser, db: DB):
    accounts = await smtp_service.list_smtp(db, user)
    return SuccessResponse(data=[SMTPOut.model_validate(a) for a in accounts])


@router.post("", response_model=SuccessResponse[SMTPOut])
async def create_account(payload: SMTPCreate, user: CurrentUser, db: DB, settings: AppSettings):
    account = await smtp_service.create_smtp(db, settings, user, payload)
    return SuccessResponse(data=SMTPOut.model_validate(account))


@router.get("/{smtp_id}", response_model=SuccessResponse[SMTPOut])
async def get_account(smtp_id: UUID, user: CurrentUser, db: DB):
    account = await smtp_service.get_owned_smtp(db, user, smtp_id)
    return SuccessResponse(data=SMTPOut.model_validate(account))


@router.patch("/{smtp_id}", response_model=SuccessResponse[SMTPOut])
async def update_account(
    smtp_id: UUID, payload: SMTPUpdate, user: CurrentUser, db: DB, settings: AppSettings
):
    account = await smtp_service.update_smtp(db, settings, user, smtp_id, payload)
    return SuccessResponse(data=SMTPOut.model_validate(account))


@router.delete("/{smtp_id}")
async def delete_account(smtp_id: UUID, user: CurrentUser, db: DB):
    await smtp_service.delete_smtp(db, user, smtp_id)
    return {"data": {"ok": True}}


@router.post("/{smtp_id}/test", response_model=SuccessResponse[SMTPOut])
async def test_account(smtp_id: UUID, user: CurrentUser, db: DB, settings: AppSettings):
    account = await smtp_service.test_connection(db, settings, user, smtp_id)
    return SuccessResponse(data=SMTPOut.model_validate(account))


@router.post("/{smtp_id}/send-test")
async def send_test(
    smtp_id: UUID, payload: SMTPTestEmail, user: CurrentUser, db: DB, settings: AppSettings
):
    await smtp_service.send_test_email(db, settings, user, smtp_id, payload.to_email)
    return {"data": {"ok": True}}
