import csv
import io
import re
from pathlib import Path
from uuid import UUID

from email_validator import EmailNotValidError, validate_email
from sqlalchemy import String, cast, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError, NotFoundError
from app.models.enums import ImportStatus
from app.models.campaign import CampaignEmail, CampaignLead
from app.models.lead import Lead, LeadGroup, LeadGroupMember, LeadImport
from app.models.user import User
from app.schemas.lead import STANDARD_FIELDS

HEADER_ALIASES = {
    "email": "email",
    "e-mail": "email",
    "email address": "email",
    "mail": "email",
    "first name": "first_name",
    "firstname": "first_name",
    "first_name": "first_name",
    "last name": "last_name",
    "lastname": "last_name",
    "last_name": "last_name",
    "company": "company",
    "organization": "company",
    "title": "title",
    "job title": "title",
    "job_title": "title",
    "industry": "industry",
    "website": "website",
    "url": "website",
}


def suggest_mapping(headers: list[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    used: set[str] = set()
    for header in headers:
        key = re.sub(r"\s+", " ", header.strip().lower())
        target = HEADER_ALIASES.get(key)
        if target and target not in used:
            mapping[header] = target
            used.add(target)
        else:
            slug = re.sub(r"[^a-z0-9]+", "_", key).strip("_") or "custom"
            mapping[header] = slug if slug not in STANDARD_FIELDS else slug
    return mapping


def inspect_csv(csv_text: str) -> dict:
    reader = csv.DictReader(io.StringIO(csv_text))
    if not reader.fieldnames:
        raise AppError("invalid_csv", "CSV file is missing a header row", 400)
    headers = [h.strip() for h in reader.fieldnames if h and h.strip()]
    preview: list[dict[str, str]] = []
    count = 0
    for row in reader:
        count += 1
        if len(preview) < 8:
            preview.append({k: (v or "") for k, v in row.items() if k})
    return {
        "headers": headers,
        "suggested_mapping": suggest_mapping(headers),
        "preview_rows": preview,
        "row_count": count,
    }


def normalize_email(value: str) -> str | None:
    try:
        result = validate_email(value.strip(), check_deliverability=False)
        return result.normalized.lower()
    except EmailNotValidError:
        return None


async def list_leads(
    db: AsyncSession,
    user: User,
    cursor: str | None,
    limit: int = 50,
    search: str | None = None,
) -> tuple[list[Lead], str | None]:
    query = select(Lead).where(Lead.user_id == user.id)
    if search:
        like = f"%{search.lower()}%"
        query = query.where(
            func.lower(Lead.email).like(like)
            | func.lower(func.coalesce(Lead.first_name, "")).like(like)
            | func.lower(func.coalesce(Lead.company, "")).like(like)
        )
    if cursor:
        query = query.where(Lead.id < UUID(cursor))
    query = query.order_by(Lead.created_at.desc(), Lead.id.desc()).limit(limit + 1)
    rows = list((await db.scalars(query)).all())
    next_cursor = str(rows[-1].id) if len(rows) > limit else None
    return rows[:limit], next_cursor


async def import_leads(
    db: AsyncSession,
    user: User,
    filename: str,
    csv_text: str,
    column_mapping: dict[str, str],
    group_name: str | None = None,
) -> LeadImport:
    if "email" not in column_mapping.values():
        raise AppError("validation_error", "Column mapping must include email", 400)

    record = LeadImport(
        user_id=user.id,
        filename=filename,
        status=ImportStatus.PROCESSING.value,
        column_mapping=column_mapping,
        raw_csv="",
    )
    db.add(record)
    await db.flush()

    reader = csv.DictReader(io.StringIO(csv_text))
    seen: set[str] = set()
    error_report: list[dict] = []
    valid_rows: list[dict] = []
    invalid = 0
    duplicates = 0
    total = 0

    for index, row in enumerate(reader, start=2):
        total += 1
        mapped: dict[str, str] = {}
        custom: dict[str, str] = {}
        for header, target in column_mapping.items():
            value = (row.get(header) or "").strip()
            if target in STANDARD_FIELDS:
                mapped[target] = value
            else:
                custom[target] = value
        email = normalize_email(mapped.get("email", ""))
        if not email:
            invalid += 1
            error_report.append({"row": index, "reason": "invalid_email"})
            continue
        if email in seen:
            duplicates += 1
            error_report.append({"row": index, "reason": "duplicate_in_file", "email": email})
            continue
        seen.add(email)
        valid_rows.append({**mapped, "email": email, "custom_fields": custom})

    existing_by_email: dict[str, Lead] = {}
    if seen:
        existing_rows = list(
            (
                await db.scalars(
                    select(Lead).where(Lead.user_id == user.id, Lead.email.in_(seen))
                )
            ).all()
        )
        existing_by_email = {lead.email: lead for lead in existing_rows}

    created = 0
    new_leads: list[Lead] = []
    for row in valid_rows:
        if row["email"] in existing_by_email:
            continue
        lead = Lead(
            user_id=user.id,
            email=row["email"],
            first_name=row.get("first_name") or None,
            last_name=row.get("last_name") or None,
            company=row.get("company") or None,
            title=row.get("title") or None,
            industry=row.get("industry") or None,
            website=row.get("website") or None,
            custom_fields=row.get("custom_fields") or {},
            is_valid=True,
        )
        db.add(lead)
        new_leads.append(lead)
        created += 1
    if new_leads:
        await db.flush()

    chosen_name = (group_name or "").strip() or group_name_from_file(filename)
    group_name = await _unique_group_name(db, user.id, chosen_name)
    group = LeadGroup(user_id=user.id, name=group_name)
    db.add(group)
    await db.flush()

    members = new_leads + [
        existing_by_email[row["email"]]
        for row in valid_rows
        if row["email"] in existing_by_email
    ]
    for lead in members:
        db.add(LeadGroupMember(group_id=group.id, lead_id=lead.id))

    record.total_rows = total
    record.valid_count = len(members)
    record.invalid_count = invalid
    record.duplicate_count = duplicates
    record.error_report = error_report[:200]
    record.status = ImportStatus.COMPLETED.value
    record.group_id = group.id
    record.group_name = group.name
    await db.flush()
    return record


def group_name_from_file(filename: str) -> str:
    stem = Path(filename or "").stem.strip()
    return (stem or "Imported leads")[:200]


async def _unique_group_name(db: AsyncSession, user_id: UUID, name: str) -> str:
    base = name.strip()[:200] or "Imported leads"
    candidate = base
    number = 2
    while await db.scalar(
        select(LeadGroup.id).where(LeadGroup.user_id == user_id, LeadGroup.name == candidate)
    ):
        suffix = f" ({number})"
        candidate = f"{base[: 200 - len(suffix)]}{suffix}"
        number += 1
    return candidate


async def _owned_group(db: AsyncSession, user: User, group_id: UUID) -> LeadGroup:
    group = await db.scalar(
        select(LeadGroup).where(LeadGroup.id == group_id, LeadGroup.user_id == user.id)
    )
    if group is None:
        raise NotFoundError("Lead group not found")
    return group


async def list_groups(db: AsyncSession, user: User) -> list[dict]:
    rows = (
        await db.execute(
            select(LeadGroup, func.count(LeadGroupMember.id))
            .outerjoin(LeadGroupMember, LeadGroupMember.group_id == LeadGroup.id)
            .where(LeadGroup.user_id == user.id)
            .group_by(LeadGroup.id)
            .order_by(LeadGroup.created_at.desc())
        )
    ).all()
    return [
        {
            "id": group.id,
            "name": group.name,
            "lead_count": int(count),
            "purpose": group.purpose or "source",
            "created_at": group.created_at,
        }
        for group, count in rows
    ]


async def get_group(
    db: AsyncSession,
    user: User,
    group_id: UUID,
    q: str | None = None,
    offset: int = 0,
    limit: int = 100,
) -> dict:
    group = await _owned_group(db, user, group_id)
    lead_count = int(
        await db.scalar(
            select(func.count()).select_from(LeadGroupMember).where(LeadGroupMember.group_id == group.id)
        )
        or 0
    )
    filters = [LeadGroupMember.group_id == group.id, Lead.user_id == user.id]
    term = (q or "").strip()
    if term:
        safe = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        like = f"%{safe}%"
        filters.append(
            or_(
                Lead.email.ilike(like, escape="\\"),
                Lead.first_name.ilike(like, escape="\\"),
                Lead.last_name.ilike(like, escape="\\"),
                Lead.company.ilike(like, escape="\\"),
                Lead.title.ilike(like, escape="\\"),
                Lead.country.ilike(like, escape="\\"),
                Lead.website.ilike(like, escape="\\"),
                Lead.study_opportunity.ilike(like, escape="\\"),
                cast(Lead.custom_fields, String).ilike(like, escape="\\"),
            )
        )
    matched = (
        select(Lead.id)
        .join(LeadGroupMember, LeadGroupMember.lead_id == Lead.id)
        .where(*filters)
    )
    match_count = int(await db.scalar(select(func.count()).select_from(matched.subquery())) or 0)
    leads = list(
        (
            await db.scalars(
                select(Lead)
                .join(LeadGroupMember, LeadGroupMember.lead_id == Lead.id)
                .where(*filters)
                .order_by(Lead.email)
                .offset(max(offset, 0))
                .limit(min(limit, 100))
            )
        ).all()
    )
    return {
        "id": group.id,
        "name": group.name,
        "lead_count": lead_count,
        "match_count": match_count,
        "purpose": group.purpose or "source",
        "created_at": group.created_at,
        "leads": leads,
    }


async def rename_group(db: AsyncSession, user: User, group_id: UUID, name: str) -> dict:
    group = await _owned_group(db, user, group_id)
    cleaned = name.strip()
    if not cleaned:
        raise AppError("validation_error", "Group name is required", 400)
    taken = await db.scalar(
        select(LeadGroup.id).where(
            LeadGroup.user_id == user.id,
            LeadGroup.name == cleaned,
            LeadGroup.id != group.id,
        )
    )
    if taken is not None:
        raise AppError("duplicate_name", "You already have a group with that name", 409)
    group.name = cleaned[:200]
    await db.flush()
    return await get_group(db, user, group.id)


async def delete_group(db: AsyncSession, user: User, group_id: UUID) -> None:
    group = await _owned_group(db, user, group_id)
    lead_ids = list(
        (
            await db.scalars(
                select(LeadGroupMember.lead_id).where(LeadGroupMember.group_id == group.id)
            )
        ).all()
    )
    await db.execute(delete(LeadGroupMember).where(LeadGroupMember.group_id == group.id))
    await db.delete(group)
    await db.flush()
    if not lead_ids:
        return
    still_grouped = set(
        (
            await db.scalars(
                select(LeadGroupMember.lead_id).where(LeadGroupMember.lead_id.in_(lead_ids))
            )
        ).all()
    )
    in_campaigns = set(
        (
            await db.scalars(
                select(CampaignLead.lead_id).where(CampaignLead.lead_id.in_(lead_ids))
            )
        ).all()
    )
    in_emails = set(
        (
            await db.scalars(
                select(CampaignEmail.lead_id).where(CampaignEmail.lead_id.in_(lead_ids))
            )
        ).all()
    )
    removable = [
        lead_id
        for lead_id in lead_ids
        if lead_id not in still_grouped and lead_id not in in_campaigns and lead_id not in in_emails
    ]
    if removable:
        await db.execute(delete(Lead).where(Lead.id.in_(removable), Lead.user_id == user.id))
        await db.flush()


async def add_lead_to_group(db: AsyncSession, user: User, group_id: UUID, fields: dict) -> Lead:
    group = await _owned_group(db, user, group_id)
    email = normalize_email(str(fields.get("email") or ""))
    if not email:
        raise AppError("validation_error", "A valid email is required", 400)
    lead = await db.scalar(select(Lead).where(Lead.user_id == user.id, Lead.email == email))
    if lead is None:
        lead = Lead(
            user_id=user.id,
            email=email,
            first_name=(fields.get("first_name") or None),
            last_name=(fields.get("last_name") or None),
            company=(fields.get("company") or None),
            title=(fields.get("title") or None),
            industry=(fields.get("industry") or None),
            website=(fields.get("website") or None),
            custom_fields={},
            is_valid=True,
        )
        db.add(lead)
        await db.flush()
    existing = await db.scalar(
        select(LeadGroupMember.id).where(
            LeadGroupMember.group_id == group.id,
            LeadGroupMember.lead_id == lead.id,
        )
    )
    if existing is None:
        db.add(LeadGroupMember(group_id=group.id, lead_id=lead.id))
        await db.flush()
    return lead


async def remove_lead_from_group(
    db: AsyncSession, user: User, group_id: UUID, lead_id: UUID
) -> None:
    group = await _owned_group(db, user, group_id)
    member = await db.scalar(
        select(LeadGroupMember).where(
            LeadGroupMember.group_id == group.id,
            LeadGroupMember.lead_id == lead_id,
        )
    )
    if member is None:
        raise NotFoundError("Lead is not in this group")
    await db.delete(member)
    await db.flush()


def choose_prospect_email(work_email: str, personal_email: str) -> tuple[str, str] | None:
    """Prefer a work address. Fall back to the personal source address."""
    work = normalize_email(work_email)
    personal = normalize_email(personal_email)
    if work:
        return work, "work"
    if personal:
        return personal, "personal"
    return None


def split_person_name(full_name: str) -> tuple[str | None, str | None]:
    parts = [part for part in (full_name or "").split() if part]
    if not parts:
        return None, None
    if len(parts) == 1:
        return parts[0][:120], None
    return parts[0][:120], " ".join(parts[1:])[:120]


def _website(domain: str) -> str | None:
    domain = (domain or "").strip()
    if not domain:
        return None
    if domain.startswith("http://") or domain.startswith("https://"):
        return domain[:400]
    return f"https://{domain}"[:400]


async def lead_facets(db: AsyncSession, user: User) -> dict:
    countries = list(
        (
            await db.scalars(
                select(Lead.country)
                .where(Lead.user_id == user.id, Lead.country.is_not(None), Lead.country != "")
                .distinct()
                .order_by(Lead.country)
            )
        ).all()
    )
    studies = list(
        (
            await db.scalars(
                select(Lead.study_opportunity)
                .where(
                    Lead.user_id == user.id,
                    Lead.study_opportunity.is_not(None),
                    Lead.study_opportunity != "",
                )
                .distinct()
                .order_by(Lead.study_opportunity)
            )
        ).all()
    )
    return {"countries": countries, "study_opportunities": studies}


async def import_mindsurve_workbook(
    db: AsyncSession, user: User, filename: str, raw: bytes
) -> dict:
    from openpyxl import load_workbook

    try:
        workbook = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    except Exception as exc:
        raise AppError("invalid_workbook", "This file is not a readable Excel workbook", 400) from exc
    if "Prospects" not in workbook.sheetnames:
        workbook.close()
        raise AppError(
            "invalid_workbook",
            "The workbook needs a Prospects sheet with the MindSurve lead columns",
            400,
        )

    sheet = workbook["Prospects"]
    rows = sheet.iter_rows(values_only=True)
    headers = next(rows, None)
    if not headers:
        workbook.close()
        raise AppError("invalid_workbook", "The Prospects sheet is empty", 400)
    columns = {str(header).strip(): index for index, header in enumerate(headers) if header}

    required = {"Company", "Work email", "Personal email (source)"}
    missing = required - set(columns)
    if missing:
        workbook.close()
        raise AppError(
            "invalid_workbook",
            "Prospects is missing columns: " + ", ".join(sorted(missing)),
            400,
        )

    def value(row: tuple, name: str) -> str:
        index = columns.get(name)
        if index is None or index >= len(row) or row[index] is None:
            return ""
        return str(row[index]).strip()

    existing = {
        lead.email: lead
        for lead in (
            await db.scalars(select(Lead).where(Lead.user_id == user.id))
        ).all()
    }
    group = await db.scalar(
        select(LeadGroup).where(
            LeadGroup.user_id == user.id, LeadGroup.name == "MindSurve prospects"
        )
    )
    if group is None:
        group = LeadGroup(user_id=user.id, name="MindSurve prospects", purpose="source")
        db.add(group)
        await db.flush()

    member_ids = set(
        (
            await db.scalars(
                select(LeadGroupMember.lead_id).where(LeadGroupMember.group_id == group.id)
            )
        ).all()
    )

    imported = 0
    updated = 0
    skipped = 0
    pending = 0
    touched_emails: set[str] = set()
    for row in rows:
        chosen = choose_prospect_email(
            value(row, "Work email"), value(row, "Personal email (source)")
        )
        if chosen is None:
            skipped += 1
            continue
        email, kind = chosen
        first_name, last_name = split_person_name(value(row, "Contact"))
        role = value(row, "Role verification")
        custom = {
            "domain": value(row, "Domain"),
            "phone": value(row, "Mobile phone") or value(row, "Company phone"),
            "linkedin": value(row, "LinkedIn"),
            "work_email": normalize_email(value(row, "Work email")) or "",
            "personal_email": normalize_email(value(row, "Personal email (source)")) or "",
            "study_question": value(row, "Potential study question"),
            "initiative": value(row, "Observed initiative"),
            "initiative_url": value(row, "Initiative source URL"),
            "publication_date": value(row, "Publication date"),
            "company_id": value(row, "Company ID"),
            "in_main_research": value(row, "In main research"),
            "contact_verification": value(row, "Contact verification"),
            "role_verification": role,
        }
        fields = {
            "first_name": first_name,
            "last_name": last_name,
            "company": (value(row, "Company") or None),
            "title": (value(row, "Title") or None),
            "industry": (value(row, "Study opportunity") or None),
            "website": _website(value(row, "Domain")),
            "country": (value(row, "Country") or None),
            "study_opportunity": (value(row, "Study opportunity") or None),
            "role_verified": role.lower().startswith("role verified"),
            "email_kind": kind,
            "custom_fields": {key: item for key, item in custom.items() if item},
            "is_valid": True,
        }
        if fields["company"]:
            fields["company"] = fields["company"][:200]
        if fields["title"]:
            fields["title"] = fields["title"][:200]
        if fields["country"]:
            fields["country"] = fields["country"][:80]
        if fields["study_opportunity"]:
            fields["study_opportunity"] = fields["study_opportunity"][:160]
        if fields["industry"]:
            fields["industry"] = fields["industry"][:160]

        lead = existing.get(email)
        if lead is None:
            lead = Lead(user_id=user.id, email=email, **fields)
            db.add(lead)
            existing[email] = lead
            imported += 1
            pending += 1
        else:
            for key, item in fields.items():
                setattr(lead, key, item)
            updated += 1
        touched_emails.add(email)
        if pending >= 400:
            await db.flush()
            pending = 0
    await db.flush()
    workbook.close()

    for email in touched_emails:
        lead = existing[email]
        if lead.id in member_ids:
            continue
        db.add(LeadGroupMember(group_id=group.id, lead_id=lead.id))
        member_ids.add(lead.id)
    await db.flush()
    return {
        "group_id": group.id,
        "group_name": group.name,
        "imported": imported,
        "updated": updated,
        "skipped_no_email": skipped,
    }


async def get_import(db: AsyncSession, user: User, import_id: UUID) -> LeadImport:
    record = await db.scalar(
        select(LeadImport).where(LeadImport.id == import_id, LeadImport.user_id == user.id)
    )
    if record is None:
        raise NotFoundError("Import not found")
    return record
