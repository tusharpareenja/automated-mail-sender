from uuid import UUID

from fastapi import APIRouter, File, Query, UploadFile

from app.core.deps import CurrentUser, DB
from app.core.exceptions import AppError
from app.schemas.common import CursorPage, SuccessResponse
from app.schemas.lead import (
    ImportCommitRequest,
    ImportInspectOut,
    ImportOut,
    LeadCreate,
    LeadGroupDetail,
    LeadFacetsOut,
    LeadGroupOut,
    LeadGroupRename,
    LeadOut,
    WorkbookImportOut,
)
from app.services import lead_service

router = APIRouter(prefix="/leads", tags=["leads"])


@router.get("", response_model=SuccessResponse[CursorPage[LeadOut]])
async def list_leads(
    user: CurrentUser,
    db: DB,
    cursor: str | None = None,
    q: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=50, ge=1, le=100),
):
    rows, next_cursor = await lead_service.list_leads(db, user, cursor, limit, q)
    return SuccessResponse(
        data=CursorPage(
            items=[LeadOut.model_validate(r) for r in rows],
            next_cursor=next_cursor,
            has_more=next_cursor is not None,
        )
    )


@router.post("/inspect", response_model=SuccessResponse[ImportInspectOut])
async def inspect_csv(payload: ImportCommitRequest, user: CurrentUser):
    if len(payload.csv_text.encode("utf-8")) > 20 * 1024 * 1024:
        raise AppError("file_too_large", "CSV exceeds the 20MB limit", 413)
    return SuccessResponse(data=ImportInspectOut(**lead_service.inspect_csv(payload.csv_text)))


@router.post("/import", response_model=SuccessResponse[ImportOut])
async def import_leads(payload: ImportCommitRequest, user: CurrentUser, db: DB):
    if len(payload.csv_text.encode("utf-8")) > 20 * 1024 * 1024:
        raise AppError("file_too_large", "CSV exceeds the 20MB limit", 413)
    record = await lead_service.import_leads(
        db,
        user,
        payload.filename,
        payload.csv_text,
        payload.column_mapping,
        payload.group_name,
    )
    return SuccessResponse(data=ImportOut.model_validate(record))


@router.get("/facets", response_model=SuccessResponse[LeadFacetsOut])
async def lead_facets(user: CurrentUser, db: DB):
    return SuccessResponse(data=LeadFacetsOut(**await lead_service.lead_facets(db, user)))


@router.post("/import-workbook", response_model=SuccessResponse[WorkbookImportOut])
async def import_workbook(user: CurrentUser, db: DB, file: UploadFile = File(...)):
    filename = file.filename or "leads.xlsx"
    if not filename.lower().endswith(".xlsx"):
        raise AppError("invalid_workbook", "Upload the MindSurve .xlsx workbook", 400)
    raw = await file.read()
    if len(raw) > 25 * 1024 * 1024:
        raise AppError("file_too_large", "Workbook exceeds the 25MB limit", 413)
    result = await lead_service.import_mindsurve_workbook(db, user, filename, raw)
    return SuccessResponse(data=WorkbookImportOut(**result))


@router.get("/groups", response_model=SuccessResponse[list[LeadGroupOut]])
async def list_groups(user: CurrentUser, db: DB):
    rows = await lead_service.list_groups(db, user)
    return SuccessResponse(data=[LeadGroupOut.model_validate(row) for row in rows])


def _group_detail(group: dict) -> LeadGroupDetail:
    return LeadGroupDetail(
        id=group["id"],
        name=group["name"],
        lead_count=group["lead_count"],
        match_count=group.get("match_count", group["lead_count"]),
        purpose=group.get("purpose") or "source",
        created_at=group["created_at"],
        leads=[LeadOut.model_validate(lead) for lead in group["leads"]],
    )


@router.get("/groups/{group_id}", response_model=SuccessResponse[LeadGroupDetail])
async def get_group(
    group_id: UUID,
    user: CurrentUser,
    db: DB,
    q: str | None = Query(default=None, max_length=120),
    offset: int = Query(default=0, ge=0),
):
    group = await lead_service.get_group(db, user, group_id, q, offset)
    return SuccessResponse(data=_group_detail(group))


@router.patch("/groups/{group_id}", response_model=SuccessResponse[LeadGroupDetail])
async def rename_group(group_id: UUID, payload: LeadGroupRename, user: CurrentUser, db: DB):
    group = await lead_service.rename_group(db, user, group_id, payload.name)
    return SuccessResponse(data=_group_detail(group))


@router.delete("/groups/{group_id}", response_model=SuccessResponse[dict])
async def delete_group(group_id: UUID, user: CurrentUser, db: DB):
    await lead_service.delete_group(db, user, group_id)
    return SuccessResponse(data={"deleted": True})


@router.post("/groups/{group_id}/leads", response_model=SuccessResponse[LeadOut])
async def add_group_lead(group_id: UUID, payload: LeadCreate, user: CurrentUser, db: DB):
    lead = await lead_service.add_lead_to_group(db, user, group_id, payload.model_dump())
    return SuccessResponse(data=LeadOut.model_validate(lead))


@router.delete("/groups/{group_id}/leads/{lead_id}", response_model=SuccessResponse[dict])
async def remove_group_lead(group_id: UUID, lead_id: UUID, user: CurrentUser, db: DB):
    await lead_service.remove_lead_from_group(db, user, group_id, lead_id)
    return SuccessResponse(data={"deleted": True})


@router.get("/imports/{import_id}", response_model=SuccessResponse[ImportOut])
async def get_import(import_id: UUID, user: CurrentUser, db: DB):
    record = await lead_service.get_import(db, user, import_id)
    return SuccessResponse(data=ImportOut.model_validate(record))
