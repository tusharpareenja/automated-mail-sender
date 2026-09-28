from fastapi import APIRouter, Request, Response

from app.core.deps import AppSettings, CurrentUser, DB
from app.core.rate_limit import enforce_rate_limit
from app.core.security import REFRESH_COOKIE, create_ws_token
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
    UpdateProfileRequest,
    UserOut,
    VerifyEmailRequest,
)
from app.schemas.common import SuccessResponse
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


def _client_meta(request: Request) -> tuple[str | None, str | None]:
    return request.headers.get("user-agent"), request.client.host if request.client else None


@router.post("/register", response_model=SuccessResponse[UserOut])
async def register(
    payload: RegisterRequest,
    request: Request,
    response: Response,
    db: DB,
    settings: AppSettings,
):
    enforce_rate_limit(f"register:{request.client.host if request.client else 'unknown'}", 8, 3600)
    user = await auth_service.register_user(db, payload)
    await auth_service.issue_session(db, settings, response, user, *_client_meta(request))
    return SuccessResponse(data=UserOut.model_validate(user))


@router.post("/login", response_model=SuccessResponse[UserOut])
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: DB,
    settings: AppSettings,
):
    enforce_rate_limit(f"login:{request.client.host if request.client else 'unknown'}", 20, 300)
    user = await auth_service.authenticate(db, payload)
    await auth_service.issue_session(db, settings, response, user, *_client_meta(request))
    return SuccessResponse(data=UserOut.model_validate(user))


@router.post("/refresh", response_model=SuccessResponse[UserOut])
async def refresh(request: Request, response: Response, db: DB, settings: AppSettings):
    user = await auth_service.refresh_session(
        db,
        settings,
        response,
        request.cookies.get(REFRESH_COOKIE),
        *_client_meta(request),
    )
    return SuccessResponse(data=UserOut.model_validate(user))


@router.post("/logout")
async def logout(request: Request, response: Response, db: DB):
    await auth_service.logout_session(db, request.cookies.get(REFRESH_COOKIE), response)
    return {"data": {"ok": True}}


@router.get("/me", response_model=SuccessResponse[UserOut])
async def me(user: CurrentUser):
    return SuccessResponse(data=UserOut.model_validate(user))


@router.get("/ws-ticket")
async def ws_ticket(user: CurrentUser, settings: AppSettings):
    return {"data": {"token": create_ws_token(settings, user.id)}}


@router.patch("/me", response_model=SuccessResponse[UserOut])
async def update_me(payload: UpdateProfileRequest, user: CurrentUser, db: DB):
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(user, key, value)
    await db.flush()
    return SuccessResponse(data=UserOut.model_validate(user))


@router.post("/forgot-password")
async def forgot_password(payload: ForgotPasswordRequest, db: DB):
    token = await auth_service.request_password_reset(db, payload.email)
    # Token is returned only in non-production to allow local testing without email.
    return {"data": {"ok": True, "reset_token": token}}


@router.post("/reset-password")
async def reset_password(payload: ResetPasswordRequest, db: DB):
    await auth_service.reset_password(db, payload)
    return {"data": {"ok": True}}


@router.post("/verify-email")
async def verify_email(payload: VerifyEmailRequest, db: DB):
    await auth_service.verify_email(db, payload.token)
    return {"data": {"ok": True}}
