"""A bar's gallery photos (API spec 3.16): add, delete, reorder, and the files behind the public URLs.

Adding, deleting and reordering lock the bar row, so the changes to one bar take turns and the count
and positions hold. Positions run from 1 without gaps; the first photo is the cover. Each photo is two
stored files, the re-encoded JPEG and its thumbnail. Storage and the database share no transaction:
an add stores the files first and removes them if the database write fails; a delete removes them
only after the commit, and a file that cannot be removed is only logged.
"""

import logging
from uuid import UUID, uuid4

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.adapters.storage import ImageStorage
from app.core.errors import ApiError, validation_failed_fields
from app.core.security import Principal
from app.models import BarPhoto
from app.schemas.bar import BarPhotoResponse
from app.services.bar_access import lock_bar_for_manager
from app.services.bar_photo_image import process_photo
from app.services.bar_photo_links import photos_by_bar
from app.services.menu_import_upload import ImageUpload
from app.services.users import caller_user_id

logger = logging.getLogger(__name__)

MAX_PHOTOS = 15
PHOTO_CONTENT_TYPE = "image/jpeg"


def photo_not_found(photo_id: str) -> ApiError:
    return ApiError(404, "PHOTO_NOT_FOUND", "사진을 찾을 수 없습니다.", details={"photoId": photo_id})


def _photos_of(session: Session, bar_id: UUID, base_url: str) -> list[BarPhotoResponse]:
    return photos_by_bar(session, [bar_id], base_url)[bar_id]


def _delete_files(storage: ImageStorage, keys: list[str], reason: str) -> None:
    for key in keys:
        try:
            storage.delete(key)
        except Exception:
            # An orphaned file is only wasted space; nothing points to it any more.
            logger.warning("Could not delete %s %s", key, reason, exc_info=True)


def add_photo(
    session: Session, storage: ImageStorage, principal: Principal, bar_id: UUID, upload: ImageUpload, base_url: str
) -> list[BarPhotoResponse]:
    """Add the photo at the end (3.16.2) and return the bar's photos. The route has checked the bar and
    the caller; the photo is checked and re-encoded before the lock, so the lock is held only briefly."""
    processed = process_photo(upload)
    uploader_id = caller_user_id(session, principal)
    lock_bar_for_manager(session, principal, bar_id)
    # Before the count, so a retried request for the 15th photo still gets PHOTO_EXISTS.
    existing = session.scalar(
        select(BarPhoto.id).where(BarPhoto.bar_id == bar_id, BarPhoto.content_sha256 == processed.content_sha256)
    )
    if existing is not None:
        raise ApiError(409, "PHOTO_EXISTS", "이미 등록된 사진입니다.", details={"photoId": str(existing)})
    count = session.scalar(select(func.count()).select_from(BarPhoto).where(BarPhoto.bar_id == bar_id))
    if count >= MAX_PHOTOS:
        raise ApiError(
            409,
            "PHOTO_LIMIT_REACHED",
            f"사진은 최대 {MAX_PHOTOS}장까지 올릴 수 있습니다.",
            details={"maxPhotos": MAX_PHOTOS},
        )

    photo_id = uuid4()
    image_key = f"bars/{bar_id}/photos/{photo_id}.jpg"
    thumbnail_key = f"bars/{bar_id}/photos/{photo_id}-thumb.jpg"
    saved: list[str] = []
    try:
        for key, data in ((image_key, processed.image), (thumbnail_key, processed.thumbnail)):
            # Before the save: a save that fails may still have written the file.
            saved.append(key)
            storage.save(key, data, PHOTO_CONTENT_TYPE)
        session.add(
            BarPhoto(
                id=photo_id,
                bar_id=bar_id,
                storage_key=image_key,
                thumbnail_storage_key=thumbnail_key,
                content_sha256=processed.content_sha256,
                sort_order=count + 1,
                uploaded_by_user_id=uploader_id,
            )
        )
        session.commit()
    except Exception:
        session.rollback()
        _delete_files(storage, saved, "after a failed photo upload")
        raise
    return _photos_of(session, bar_id, base_url)


def delete_photo(
    session: Session, storage: ImageStorage, principal: Principal, bar_id: UUID, photo_id: str, base_url: str
) -> list[BarPhotoResponse]:
    """Delete the photo and move the ones after it forward (3.16.3); the bar's photos."""
    try:
        parsed_id = UUID(photo_id)
    except ValueError:
        raise photo_not_found(photo_id) from None
    lock_bar_for_manager(session, principal, bar_id)
    photo = session.scalar(select(BarPhoto).where(BarPhoto.id == parsed_id, BarPhoto.bar_id == bar_id))
    if photo is None:
        raise photo_not_found(photo_id)
    keys = [photo.storage_key, photo.thumbnail_storage_key]
    session.delete(photo)
    session.execute(
        update(BarPhoto)
        .where(BarPhoto.bar_id == bar_id, BarPhoto.sort_order > photo.sort_order)
        .values(sort_order=BarPhoto.sort_order - 1)
    )
    session.commit()
    _delete_files(storage, keys, "of a deleted photo")
    return _photos_of(session, bar_id, base_url)


def check_photo_order(photo_ids: list[UUID]) -> None:
    """422 DUPLICATE_ITEM for each id sent again."""
    seen: set[UUID] = set()
    errors = []
    for index, photo_id in enumerate(photo_ids):
        if photo_id in seen:
            errors.append({"path": f"photoIds[{index}]", "code": "DUPLICATE_ITEM", "message": "같은 사진이 두 번 있습니다."})
        seen.add(photo_id)
    if errors:
        raise validation_failed_fields(errors)


def reorder_photos(
    session: Session, principal: Principal, bar_id: UUID, photo_ids: list[UUID], base_url: str
) -> list[BarPhotoResponse]:
    """Put the bar's photos in the order sent (3.16.4); the first becomes the cover. The ids must be
    exactly the bar's photos (checked by the route for duplicates)."""
    lock_bar_for_manager(session, principal, bar_id)
    photos = {photo.id: photo for photo in session.scalars(select(BarPhoto).where(BarPhoto.bar_id == bar_id))}
    if set(photo_ids) != photos.keys():
        current = _photos_of(session, bar_id, base_url)
        raise ApiError(
            409,
            "PHOTOS_OUTDATED",
            "사진 목록이 바뀌었습니다. 다시 정렬해 주세요.",
            details={"photos": [photo.model_dump(mode="json") for photo in current]},
        )
    # Positions may swap: the unique position constraint is checked at commit.
    for order, photo_id in enumerate(photo_ids, start=1):
        photos[photo_id].sort_order = order
    session.commit()
    return _photos_of(session, bar_id, base_url)


def read_photo_file(session: Session, storage: ImageStorage, photo_id: str, *, thumbnail: bool) -> bytes:
    """The stored JPEG of a photo or its thumbnail (3.16.5). A deleted photo is 404 at once, even while
    its files are still being removed."""
    try:
        photo = session.get(BarPhoto, UUID(photo_id))
    except ValueError:
        photo = None
    if photo is None:
        raise photo_not_found(photo_id)
    key = photo.thumbnail_storage_key if thumbnail else photo.storage_key
    try:
        return storage.read(key)
    except FileNotFoundError:
        logger.warning("Bar photo %s has no file at %s", photo_id, key)
        raise photo_not_found(photo_id) from None
