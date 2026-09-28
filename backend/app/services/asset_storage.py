"""Asset storage: Azure Blob when configured, otherwise local filesystem."""

from __future__ import annotations

import hashlib
import logging
import mimetypes
import re
from pathlib import Path
from uuid import UUID, uuid4

from app.core.config import Settings
from app.core.exceptions import AppError, NotFoundError, ValidationError
from app.models.enums import AssetKind

logger = logging.getLogger(__name__)

SAFE_NAME_RE = re.compile(r"[^a-zA-Z0-9._-]+")

MAGIC_SIGNATURES: list[tuple[bytes, str]] = [
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"%PDF", "application/pdf"),
    (b"RIFF", "image/webp"),
]


def _detect_mime(data: bytes, fallback: str | None = None) -> str:
    for signature, mime in MAGIC_SIGNATURES:
        if data.startswith(signature):
            if mime == "image/webp":
                if len(data) >= 12 and data[8:12] == b"WEBP":
                    return "image/webp"
                continue
            return mime
    guessed, _ = mimetypes.guess_type(fallback or "")
    return (guessed or fallback or "application/octet-stream").lower()


def kind_for_mime(mime: str) -> str:
    if mime.startswith("image/"):
        return AssetKind.IMAGE.value
    if mime == "application/pdf":
        return AssetKind.PDF.value
    return AssetKind.OTHER.value


def sanitize_filename(name: str) -> str:
    cleaned = SAFE_NAME_RE.sub("_", Path(name).name).strip("._")
    return (cleaned or "file")[:180]


def build_stored_filename(original: str) -> str:
    safe = sanitize_filename(original)
    return f"{uuid4().hex}_{safe}"


def blob_key(user_id: UUID, stored_filename: str) -> str:
    safe_name = Path(stored_filename).name
    if ".." in safe_name or "/" in safe_name or "\\" in safe_name:
        raise AppError("invalid_path", "Invalid storage path", 400)
    return f"{user_id}/{safe_name}"


def storage_root(settings: Settings) -> Path:
    root = Path(settings.asset_storage_dir)
    if not root.is_absolute():
        root = Path(__file__).resolve().parents[2] / root
    root.mkdir(parents=True, exist_ok=True)
    return root


def user_dir(settings: Settings, user_id: UUID) -> Path:
    path = storage_root(settings) / str(user_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _azure_container(settings: Settings):
    from azure.core.exceptions import ResourceExistsError
    from azure.storage.blob import BlobServiceClient, ContentSettings

    if not settings.use_azure_storage:
        raise AppError("storage_misconfigured", "Azure storage is not configured", 500)

    service = BlobServiceClient.from_connection_string(
        settings.azure_storage_connection_string
    )
    container = service.get_container_client(settings.azure_storage_container_name)
    try:
        container.create_container()
    except ResourceExistsError:
        pass
    except Exception:
        # Container may already exist or account may disallow create; continue.
        logger.debug("azure_container_ensure_skipped", exc_info=True)
    return container, ContentSettings


def save_asset_bytes(
    settings: Settings,
    user_id: UUID,
    original_filename: str,
    data: bytes,
    declared_content_type: str | None = None,
) -> dict:
    if not data:
        raise ValidationError("Empty file upload")
    if len(data) > settings.max_asset_bytes:
        raise ValidationError(
            f"File exceeds max size of {settings.max_asset_bytes} bytes"
        )

    mime = _detect_mime(data, declared_content_type or original_filename)
    if mime not in settings.allowed_asset_mimes:
        raise ValidationError(f"File type not allowed: {mime}")

    stored_filename = build_stored_filename(original_filename)
    checksum = hashlib.sha256(data).hexdigest()
    kind = kind_for_mime(mime)
    prefix = "asset_img" if kind == AssetKind.IMAGE.value else "asset_link"
    placeholder_key = f"{prefix}_{uuid4().hex[:16]}"

    if settings.use_azure_storage:
        container, ContentSettings = _azure_container(settings)
        key = blob_key(user_id, stored_filename)
        blob = container.get_blob_client(key)
        blob.upload_blob(
            data,
            overwrite=True,
            content_settings=ContentSettings(content_type=mime),
        )
        logger.info(
            "asset_uploaded_azure",
            extra={"event": "asset_uploaded_azure", "blob": key, "bytes": len(data)},
        )
        return {
            "original_filename": sanitize_filename(original_filename),
            "stored_filename": stored_filename,
            "content_type": mime,
            "kind": kind,
            "size_bytes": len(data),
            "checksum_sha256": checksum,
            "placeholder_key": placeholder_key,
            "storage": "azure",
            "blob_key": key,
        }

    dest = user_dir(settings, user_id) / stored_filename
    dest = dest.resolve()
    if not str(dest).startswith(str(user_dir(settings, user_id).resolve())):
        raise AppError("invalid_path", "Invalid storage path", 400)
    dest.write_bytes(data)
    return {
        "original_filename": sanitize_filename(original_filename),
        "stored_filename": stored_filename,
        "content_type": mime,
        "kind": kind,
        "size_bytes": len(data),
        "checksum_sha256": checksum,
        "placeholder_key": placeholder_key,
        "storage": "local",
        "absolute_path": dest,
    }


def _read_local_bytes(
    settings: Settings, user_id: UUID, stored_filename: str
) -> tuple[bytes, str] | None:
    try:
        path = resolve_asset_path(settings, user_id, stored_filename)
    except NotFoundError:
        return None
    guessed, _ = mimetypes.guess_type(stored_filename)
    return path.read_bytes(), guessed or "application/octet-stream"


def _promote_local_to_azure(
    settings: Settings, user_id: UUID, stored_filename: str, data: bytes, content_type: str
) -> None:
    container, ContentSettings = _azure_container(settings)
    key = blob_key(user_id, stored_filename)
    blob = container.get_blob_client(key)
    blob.upload_blob(
        data,
        overwrite=True,
        content_settings=ContentSettings(content_type=content_type),
    )
    logger.info(
        "asset_promoted_to_azure",
        extra={"event": "asset_promoted_to_azure", "blob": key, "bytes": len(data)},
    )


def blob_preview_url(settings: Settings, user_id: UUID, stored_filename: str, content_type: str) -> str:
    """Browser-loadable Azure URL for template preview. Empty when Azure is off."""
    if not settings.use_azure_storage:
        return ""
    from datetime import datetime, timedelta, timezone

    from azure.storage.blob import BlobSasPermissions, BlobServiceClient, generate_blob_sas

    key = blob_key(user_id, stored_filename)
    container, ContentSettings = _azure_container(settings)
    blob = container.get_blob_client(key)
    if not blob.exists():
        local = _read_local_bytes(settings, user_id, stored_filename)
        if local is None:
            return ""
        data, mime = local
        blob.upload_blob(
            data,
            overwrite=True,
            content_settings=ContentSettings(content_type=content_type or mime),
        )
    service = BlobServiceClient.from_connection_string(settings.azure_storage_connection_string)
    account_key = getattr(service.credential, "account_key", None)
    account_name = service.account_name
    base = (
        f"https://{account_name}.blob.core.windows.net/"
        f"{settings.azure_storage_container_name}/{key}"
    )
    if not account_key:
        return base
    sas = generate_blob_sas(
        account_name=account_name,
        container_name=settings.azure_storage_container_name,
        blob_name=key,
        account_key=account_key,
        permission=BlobSasPermissions(read=True),
        expiry=datetime.now(timezone.utc) + timedelta(days=6),
    )
    return f"{base}?{sas}"


def load_asset_bytes(
    settings: Settings, user_id: UUID, stored_filename: str
) -> tuple[bytes, str]:
    """Return (bytes, content_type_hint_from_name)."""
    if settings.use_azure_storage:
        from azure.core.exceptions import ResourceNotFoundError

        container, _ = _azure_container(settings)
        key = blob_key(user_id, stored_filename)
        blob = container.get_blob_client(key)
        try:
            downloader = blob.download_blob()
            data = downloader.readall()
            content_type = (
                getattr(downloader.properties, "content_settings", None)
                and downloader.properties.content_settings.content_type
            ) or mimetypes.guess_type(stored_filename)[0] or "application/octet-stream"
            return data, content_type
        except ResourceNotFoundError:
            local = _read_local_bytes(settings, user_id, stored_filename)
            if local is None:
                raise NotFoundError("Asset file not found")
            data, content_type = local
            try:
                _promote_local_to_azure(
                    settings, user_id, stored_filename, data, content_type
                )
            except Exception:
                logger.warning("asset_promote_failed", exc_info=True)
            return data, content_type

    local = _read_local_bytes(settings, user_id, stored_filename)
    if local is None:
        raise NotFoundError("Asset file not found")
    return local


def resolve_asset_path(settings: Settings, user_id: UUID, stored_filename: str) -> Path:
    """Local-only helper (tests / local mode)."""
    safe_name = Path(stored_filename).name
    path = (user_dir(settings, user_id) / safe_name).resolve()
    root = user_dir(settings, user_id).resolve()
    if not str(path).startswith(str(root)) or not path.is_file():
        raise NotFoundError("Asset file not found")
    return path


def delete_asset_file(settings: Settings, user_id: UUID, stored_filename: str) -> None:
    if settings.use_azure_storage:
        from azure.core.exceptions import ResourceNotFoundError

        container, _ = _azure_container(settings)
        key = blob_key(user_id, stored_filename)
        blob = container.get_blob_client(key)
        try:
            blob.delete_blob()
        except ResourceNotFoundError:
            pass

    try:
        path = resolve_asset_path(settings, user_id, stored_filename)
    except NotFoundError:
        return
    path.unlink(missing_ok=True)
