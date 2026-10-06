"""Development-only file serving for LocalImageStorage, so review image URLs open locally.

With object storage (P21) the review API returns signed URLs instead and this route
answers 404. It is left out of the OpenAPI document.
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from app.adapters.storage import MEDIA_PATH_PREFIX, ImageStorage, LocalImageStorage
from app.api.deps import get_image_storage

router = APIRouter(prefix=MEDIA_PATH_PREFIX, include_in_schema=False)


@router.get("/{key:path}")
def read_media(key: str, storage: ImageStorage = Depends(get_image_storage)) -> FileResponse:
    if not isinstance(storage, LocalImageStorage):
        raise HTTPException(status_code=404, detail="Not found")
    try:
        path = storage.path_for(key)
    except ValueError:
        raise HTTPException(status_code=404, detail="Not found") from None
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(path)
