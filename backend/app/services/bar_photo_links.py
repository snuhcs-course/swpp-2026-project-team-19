"""The bar photo URLs in API responses (spec 3.16.5): `photos` of the bar responses and
`coverThumbnailUrl` of the bar lists, without a query per bar.

The URLs are absolute, on the address the request came in on, and point to the public file routes,
never to storage: the bucket stays private.
"""

from collections import defaultdict
from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import ScalarSelect, select
from sqlalchemy.orm import Session

from app.models import Bar, BarPhoto
from app.schemas.bar import BarPhotoResponse


def photo_response(photo_id: UUID, base_url: str) -> BarPhotoResponse:
    """The fixed URLs of spec 3.16.5, on the address the request came in on."""
    image_url = f"{base_url.rstrip('/')}/api/bar-photos/{photo_id}"
    return BarPhotoResponse(photoId=photo_id, imageUrl=image_url, thumbnailUrl=f"{image_url}/thumbnail")


def photos_by_bar(session: Session, bar_ids: Sequence[UUID], base_url: str) -> dict[UUID, list[BarPhotoResponse]]:
    """Each bar's photos in display order, with one query; a bar without photos maps to []."""
    photos: dict[UUID, list[BarPhotoResponse]] = defaultdict(list)
    for bar_id, photo_id in session.execute(
        select(BarPhoto.bar_id, BarPhoto.id).where(BarPhoto.bar_id.in_(bar_ids)).order_by(BarPhoto.sort_order)
    ):
        photos[bar_id].append(photo_response(photo_id, base_url))
    return photos


def cover_photo_id() -> ScalarSelect[UUID]:
    """A column for bar list queries: the id of the bar's cover photo (position 1), null without photos.
    Found per bar on the (bar, position) index, so a list stays one query however many bars it has."""
    return (
        select(BarPhoto.id)
        .where(BarPhoto.bar_id == Bar.id, BarPhoto.sort_order == 1)
        .correlate(Bar)
        .scalar_subquery()
    )


def cover_thumbnail_url(photo_id: UUID | None, base_url: str) -> str | None:
    """`coverThumbnailUrl` of the bar lists from `cover_photo_id()`."""
    return photo_response(photo_id, base_url).thumbnailUrl if photo_id is not None else None
