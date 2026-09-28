from uuid import UUID

from fastapi import APIRouter, File, UploadFile
from sqlalchemy import select

from app.core.deps import AppSettings, CurrentUser, DB
from app.core.exceptions import NotFoundError, ValidationError
from app.models.template import Template
from app.schemas.common import SuccessResponse
from app.schemas.template import (
    AssetOut,
    TemplateCreate,
    TemplateOut,
    TemplatePreviewRequest,
    TemplateUpdate,
    asset_to_out,
)
from app.services import asset_service
from app.services.asset_storage import blob_preview_url
from app.services.template_service import (
    apply_sender_context,
    extract_variables,
    html_to_text,
    render_template,
    sanitize_html,
    wrap_outbound_email,
)

router = APIRouter(prefix="/templates", tags=["templates"])


async def _owned(db, user, template_id: UUID) -> Template:
    template = await db.scalar(
        select(Template).where(Template.id == template_id, Template.user_id == user.id)
    )
    if template is None:
        raise NotFoundError("Template not found")
    return template


@router.get("", response_model=SuccessResponse[list[TemplateOut]])
async def list_templates(user: CurrentUser, db: DB):
    rows = list(
        (
            await db.scalars(
                select(Template)
                .where(Template.user_id == user.id)
                .order_by(Template.updated_at.desc())
            )
        ).all()
    )
    return SuccessResponse(data=[TemplateOut.model_validate(t) for t in rows])


@router.post("", response_model=SuccessResponse[TemplateOut])
async def create_template(payload: TemplateCreate, user: CurrentUser, db: DB):
    html_body = sanitize_html(payload.html_body)
    text_body = payload.text_body or html_to_text(html_body)
    template = Template(
        user_id=user.id,
        name=payload.name,
        subject=payload.subject,
        html_body=html_body,
        text_body=text_body,
        ai_instructions=payload.ai_instructions,
        variables=extract_variables(payload.subject, html_body, text_body),
    )
    db.add(template)
    await db.flush()
    return SuccessResponse(data=TemplateOut.model_validate(template))


@router.get("/{template_id}", response_model=SuccessResponse[TemplateOut])
async def get_template(template_id: UUID, user: CurrentUser, db: DB):
    return SuccessResponse(data=TemplateOut.model_validate(await _owned(db, user, template_id)))


@router.patch("/{template_id}", response_model=SuccessResponse[TemplateOut])
async def update_template(template_id: UUID, payload: TemplateUpdate, user: CurrentUser, db: DB):
    template = await _owned(db, user, template_id)
    data = payload.model_dump(exclude_unset=True)
    if "html_body" in data and data["html_body"] is not None:
        data["html_body"] = sanitize_html(data["html_body"])
        if "text_body" not in data or not data["text_body"]:
            data["text_body"] = html_to_text(data["html_body"])
    for key, value in data.items():
        setattr(template, key, value)
    template.variables = extract_variables(template.subject, template.html_body, template.text_body)
    await db.flush()
    return SuccessResponse(data=TemplateOut.model_validate(template))


@router.post("/{template_id}/duplicate", response_model=SuccessResponse[TemplateOut])
async def duplicate_template(template_id: UUID, user: CurrentUser, db: DB):
    source = await _owned(db, user, template_id)
    clone = Template(
        user_id=user.id,
        name=f"{source.name} copy",
        subject=source.subject,
        html_body=source.html_body,
        text_body=source.text_body,
        ai_instructions=source.ai_instructions,
        variables=source.variables,
    )
    db.add(clone)
    await db.flush()
    return SuccessResponse(data=TemplateOut.model_validate(clone))


@router.delete("/{template_id}")
async def delete_template(template_id: UUID, user: CurrentUser, db: DB):
    template = await _owned(db, user, template_id)
    await db.delete(template)
    return {"data": {"ok": True}}


@router.post("/{template_id}/preview")
async def preview_template(
    template_id: UUID, payload: TemplatePreviewRequest, user: CurrentUser, db: DB
):
    template = await _owned(db, user, template_id)
    context = payload.model_dump()
    custom = context.pop("custom_fields", {}) or {}
    context.update(custom)
    context = apply_sender_context(
        context,
        from_name=user.full_name,
        company=user.company_name or "",
    )
    html_body, text_body = wrap_outbound_email(
        render_template(template.html_body, context),
        render_template(template.text_body, context),
        from_name=user.full_name,
        company=user.company_name or "",
        physical_address=user.physical_address or "",
    )
    return {
        "data": {
            "subject": render_template(template.subject, context),
            "html_body": html_body,
            "text_body": text_body,
        }
    }


@router.get("/{template_id}/assets", response_model=SuccessResponse[list[AssetOut]])
async def list_template_assets(template_id: UUID, user: CurrentUser, db: DB, settings: AppSettings):
    await _owned(db, user, template_id)
    rows = await asset_service.list_assets(db, user, template_id=template_id)
    return SuccessResponse(
        data=[
            asset_to_out(
                row,
                preview_url=blob_preview_url(
                    settings, row.user_id, row.stored_filename, row.content_type
                ),
            )
            for row in rows
        ]
    )


@router.post("/{template_id}/assets", response_model=SuccessResponse[AssetOut])
async def upload_template_asset(
    template_id: UUID,
    user: CurrentUser,
    db: DB,
    settings: AppSettings,
    file: UploadFile = File(...),
):
    await _owned(db, user, template_id)
    data = await file.read()
    if not file.filename:
        raise ValidationError("Filename is required")
    asset = await asset_service.upload_asset(
        db,
        settings,
        user,
        filename=file.filename,
        data=data,
        content_type=file.content_type,
        template_id=template_id,
    )
    return SuccessResponse(
        data=asset_to_out(
            asset,
            preview_url=blob_preview_url(
                settings, asset.user_id, asset.stored_filename, asset.content_type
            ),
        )
    )


@router.get("/assets/{asset_id}/content")
async def get_asset_content(
    asset_id: UUID,
    user: CurrentUser,
    db: DB,
    settings: AppSettings,
):
    from fastapi.responses import Response

    from app.services.asset_storage import load_asset_bytes

    asset = await asset_service.get_owned_asset(db, user, asset_id)
    data, _hint = load_asset_bytes(settings, user.id, asset.stored_filename)
    return Response(
        content=data,
        media_type=asset.content_type,
        headers={
            "Cache-Control": "private, max-age=60",
            "Content-Disposition": f'inline; filename="{asset.original_filename}"',
        },
    )


@router.delete("/assets/{asset_id}")
async def delete_asset(asset_id: UUID, user: CurrentUser, db: DB, settings: AppSettings):
    await asset_service.delete_asset(db, settings, user, asset_id)
    return {"data": {"ok": True}}
