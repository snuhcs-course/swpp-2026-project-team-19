# AI-generated with ChatGPT (Haeul Yang, 2026-10-06, PR #11, #16). Reviewed by Haeul Yang.
"""Accept a menu photo upload: validate, deduplicate retries, store images, and create the import rows.

Order of checks: bar → image count, size and type → idempotency key → one unfinished import
per bar (with the bar row locked) → store images → insert rows. Processing is scheduled by
the caller after the commit.
"""

import hashlib
import json
import logging
from dataclasses import dataclass
from typing import BinaryIO
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.adapters.extraction import MenuExtractor
from app.adapters.storage import ImageStorage
from app.core.errors import ApiError
from app.models import (
    Bar,
    BarStatus,
    ExtractionRun,
    ImportMode,
    ImportStatus,
    MenuImage,
    MenuImport,
)
from app.services.bar_menu import bar_not_found

logger = logging.getLogger(__name__)

MAX_IMAGES = 5
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_TOTAL_BYTES = 30 * 1024 * 1024
UNFINISHED_STATUSES = (ImportStatus.UPLOADED, ImportStatus.PROCESSING, ImportStatus.READY_FOR_REVIEW)
# Declared types that say nothing about the format, so only the detected type counts.
_GENERIC_CONTENT_TYPES = {None, "", "application/octet-stream"}


@dataclass
class ImageUpload:
    filename: str | None
    content_type: str | None
    stream: BinaryIO


@dataclass
class _CheckedImage:
    filename: str | None
    data: bytes
    extension: str
    content_type: str


def detect_image_type(data: bytes) -> tuple[str, str] | None:
    """(file extension, MIME type) from the file signature, or None if not JPEG or PNG.

    HEIC is not accepted because extraction sends only JPEG and PNG to the model; the app
    converts other formats to JPEG before uploading.
    """
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg", "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png", "image/png"
    return None


def request_fingerprint(bar_id: UUID, mode: ImportMode, owner_note: str | None, images: list[bytes]) -> str:
    """SHA-256 of the canonical request: bar, mode, note, and each image's hash in upload order.

    Values that differ between retries of the same request (multipart boundary, file names,
    upload time) are left out.
    """
    canonical = {
        "barId": str(bar_id),
        "mode": mode.value,
        "ownerNote": owner_note,
        "images": [hashlib.sha256(data).hexdigest() for data in images],
    }
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _too_large(message: str) -> ApiError:
    details = {"maxImages": MAX_IMAGES, "maxImageBytes": MAX_IMAGE_BYTES, "maxTotalBytes": MAX_TOTAL_BYTES}
    return ApiError(413, "UPLOAD_TOO_LARGE", message, details=details)


def _check_images(uploads: list[ImageUpload]) -> list[_CheckedImage]:
    if len(uploads) > MAX_IMAGES:
        raise _too_large(f"사진은 최대 {MAX_IMAGES}장까지 올릴 수 있습니다.")
    checked = []
    total = 0
    for order, upload in enumerate(uploads, start=1):
        # Read one byte past the limit to tell "exactly at the limit" from "over it".
        data = upload.stream.read(MAX_IMAGE_BYTES + 1)
        if len(data) > MAX_IMAGE_BYTES:
            raise _too_large("사진 한 장의 크기가 너무 큽니다.")
        total += len(data)
        if total > MAX_TOTAL_BYTES:
            raise _too_large("사진 전체 크기가 너무 큽니다.")
        detected = detect_image_type(data)
        declared = (upload.content_type or "").lower() or None
        if detected is None or (declared not in _GENERIC_CONTENT_TYPES and declared != detected[1]):
            raise ApiError(
                415,
                "UNSUPPORTED_IMAGE_TYPE",
                "JPEG, PNG 사진만 올릴 수 있습니다.",
                details={"imageOrder": order, "filename": upload.filename, "contentType": upload.content_type},
            )
        checked.append(_CheckedImage(upload.filename, data, detected[0], detected[1]))
    return checked


def _replay_or_reject(existing: MenuImport, fingerprint: str) -> MenuImport:
    """Same key and content is a retry: return the existing import. Same key, other content: reject."""
    if existing.request_fingerprint != fingerprint:
        raise ApiError(
            409,
            "IDEMPOTENCY_KEY_REUSED",
            "같은 요청 키로 다른 내용을 보냈습니다. 새 키로 다시 요청해 주세요.",
            details={"menuImportId": str(existing.id)},
        )
    return existing


def _find_by_key(session: Session, idempotency_key: str) -> MenuImport | None:
    return session.scalar(select(MenuImport).where(MenuImport.idempotency_key == idempotency_key))


def create_menu_import(
    session: Session,
    storage: ImageStorage,
    extractor: MenuExtractor,
    *,
    bar_id: str,
    idempotency_key: str,
    mode: ImportMode,
    owner_note: str | None,
    uploads: list[ImageUpload],
) -> tuple[MenuImport, bool]:
    """Returns the import and whether it was created now (False for a retried request)."""
    try:
        bar = session.get(Bar, UUID(bar_id))
    except ValueError:
        bar = None
    if bar is None or bar.status != BarStatus.ACTIVE:
        raise bar_not_found(bar_id)

    # The API sends null, not an empty string, for "no value".
    if owner_note is not None:
        owner_note = owner_note.strip() or None
    images = _check_images(uploads)
    fingerprint = request_fingerprint(bar.id, mode, owner_note, [image.data for image in images])

    existing = _find_by_key(session, idempotency_key)
    if existing is not None:
        return _replay_or_reject(existing, fingerprint), False

    # Lock the bar so two uploads for it cannot both pass the unfinished-import check.
    session.execute(select(Bar.id).where(Bar.id == bar.id).with_for_update())
    unfinished = session.scalar(
        select(MenuImport)
        .where(MenuImport.bar_id == bar.id, MenuImport.status.in_(UNFINISHED_STATUSES))
        .order_by(MenuImport.created_at.desc())
        .limit(1)
    )
    if unfinished is not None:
        raise ApiError(
            409,
            "ACTIVE_IMPORT_EXISTS",
            "이 업장에 진행 중인 메뉴 등록 작업이 있습니다.",
            details={"menuImportId": str(unfinished.id), "status": unfinished.status.value},
        )

    import_id = uuid4()
    keys = [f"menus/{bar.id}/{import_id}/page-{order}.{image.extension}" for order, image in enumerate(images, start=1)]
    saved: list[str] = []
    try:
        for key, image in zip(keys, images):
            storage.save(key, image.data, image.content_type)
            saved.append(key)

        menu_import = MenuImport(
            id=import_id,
            idempotency_key=idempotency_key,
            request_fingerprint=fingerprint,
            bar_id=bar.id,
            mode=mode,
            status=ImportStatus.UPLOADED,
            owner_note=owner_note,
        )
        session.add(menu_import)
        for order, (key, image) in enumerate(zip(keys, images), start=1):
            menu_image = MenuImage(
                menu_import_id=import_id, storage_key=key, original_filename=image.filename, image_order=order
            )
            session.add(menu_image)
            session.flush()
            session.add(
                ExtractionRun(
                    menu_image_id=menu_image.id,
                    approach=extractor.approach,
                    provider=extractor.provider,
                    model_name=extractor.model_name,
                    pipeline_version=extractor.pipeline_version,
                )
            )
        session.commit()
    except Exception as error:
        # Storage and the database share no transaction: undo the stored images by hand.
        session.rollback()
        for key in saved:
            try:
                storage.delete(key)
            except Exception:
                # Keep the original error; an orphaned object is only wasted space.
                logger.warning("Could not delete %s after a failed upload", key, exc_info=True)
        if isinstance(error, IntegrityError):
            # A concurrent request with the same key committed first.
            existing = _find_by_key(session, idempotency_key)
            if existing is not None:
                return _replay_or_reject(existing, fingerprint), False
        raise
    return menu_import, True
