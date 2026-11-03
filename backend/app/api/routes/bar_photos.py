"""The public bar photo files (API spec 3.16.5), behind the fixed URLs in the bar responses.

The storage bucket stays private; these routes read the re-encoded files and serve them. They never
read the Authorization header, so they work for guests and during a Supabase outage.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.adapters.storage import ImageStorage
from app.api.deps import get_image_storage
from app.db.session import get_session
from app.schemas.errors import error_responses
from app.services.bar_photo_image import MAX_LONG_EDGE, THUMBNAIL_LONG_EDGE
from app.services.bar_photos import PHOTO_CONTENT_TYPE, read_photo_file

router = APIRouter(prefix="/api/bar-photos", tags=["bars"])

# A photo's content never changes; one day keeps a deleted photo from lingering long on devices and caches.
CACHE_CONTROL = "public, max-age=86400"
PhotoId = Annotated[str, Path(alias="photoId", description="Photo id (UUID) from `photos` of a bar response")]

_FILE_RULES = (
    "Public; the Authorization header is not read. The body is the file itself, always `image/jpeg`, with "
    "`Cache-Control: public, max-age=86400`. The URL does not expire, and the same `photoId` always has the "
    "same content, so image caches may key on the URL. Photos of inactive bars are served too. A deleted "
    "photo answers `404` at once; the app shows no photo missing from the bar's `photos`, even if cached."
)
_RESPONSES = {
    **error_responses((404, "`PHOTO_NOT_FOUND`: no such photo, a deleted one, or a malformed id; `details.photoId`.")),
    200: {"content": {"image/jpeg": {"schema": {"type": "string", "format": "binary"}}}, "description": "The JPEG"},
}


def _jpeg(data: bytes) -> Response:
    return Response(content=data, media_type=PHOTO_CONTENT_TYPE, headers={"Cache-Control": CACHE_CONTROL})


@router.get(
    "/{photoId}",
    response_class=Response,
    summary="A bar photo file",
    description=(
        _FILE_RULES
        + f"\n\nThe photo, at most {MAX_LONG_EDGE} px on the long edge, for the full-screen view and the gallery."
    ),
    responses=_RESPONSES,
)
def read_bar_photo(
    photo_id: PhotoId,
    session: Session = Depends(get_session),
    storage: ImageStorage = Depends(get_image_storage),
) -> Response:
    return _jpeg(read_photo_file(session, storage, photo_id, thumbnail=False))


@router.get(
    "/{photoId}/thumbnail",
    response_class=Response,
    summary="A bar photo thumbnail file",
    description=(
        _FILE_RULES
        + f"\n\nThe thumbnail, {THUMBNAIL_LONG_EDGE} px on the long edge, for lists, grids and small cards."
    ),
    responses=_RESPONSES,
)
def read_bar_photo_thumbnail(
    photo_id: PhotoId,
    session: Session = Depends(get_session),
    storage: ImageStorage = Depends(get_image_storage),
) -> Response:
    return _jpeg(read_photo_file(session, storage, photo_id, thumbnail=True))
