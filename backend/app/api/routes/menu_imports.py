from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, Header, Path, Response, UploadFile
from sqlalchemy.orm import Session

from app.adapters.extraction import MenuExtractor
from app.adapters.storage import ImageStorage
from app.api.deps import get_image_storage, get_menu_extractor
from app.core.security import require_operator
from app.db.session import get_session
from app.models import ImportMode
from app.schemas.errors import error_responses
from app.schemas.menu_import import MenuImportAcceptedResponse
from app.services import menu_import_upload as upload
from app.services.menu_import_upload import ImageUpload, create_menu_import

router = APIRouter(prefix="/api", tags=["menu imports"])

POLL_AFTER_SECONDS = 3


@router.post(
    "/bars/{barId}/menu-imports",
    status_code=202,
    response_model=MenuImportAcceptedResponse,
    summary="Upload menu photos and start extraction",
    description=(
        "Operator only. Stores the photos, creates the import, and returns `202` without waiting for AI. "
        "Poll `statusUrl` until the status is `ready_for_review` or `failed`.\n\n"
        f"- Up to {upload.MAX_IMAGES} JPEG, PNG or HEIC photos in display order, "
        f"{upload.MAX_IMAGE_BYTES // 2**20} MB each and {upload.MAX_TOTAL_BYTES // 2**20} MB in total. "
        "The type is read from the file content; a declared image type that disagrees is rejected.\n"
        "- `Idempotency-Key`: retrying with the same key and the same content returns the existing import "
        "(still `202`); the same key with different content is `409 IDEMPOTENCY_KEY_REUSED`. "
        "The content is the bar, mode, owner note, and the bytes of each photo in order.\n"
        "- A bar can have only one unfinished import (`uploaded`, `processing`, `ready_for_review`).\n"
        "- An empty `ownerNote` is stored as null."
    ),
    responses=error_responses(
        (401, "`UNAUTHENTICATED`: missing, invalid or expired token."),
        (403, "`FORBIDDEN`: the caller is not an operator."),
        (404, "`BAR_NOT_FOUND`: no such bar, a malformed id, or an inactive bar."),
        (
            409,
            "`IDEMPOTENCY_KEY_REUSED` (same key, different content) or `ACTIVE_IMPORT_EXISTS` "
            "(`details.menuImportId` is the unfinished import to continue).",
        ),
        (413, "`UPLOAD_TOO_LARGE`: too many photos, or a photo or the total is too large; limits in `details`."),
        (415, "`UNSUPPORTED_IMAGE_TYPE`: not JPEG, PNG or HEIC; `details.imageOrder` names the photo."),
        (422, "`VALIDATION_FAILED`: e.g. `Idempotency-Key` or `images` `MISSING`, or an unknown `mode`."),
    ),
)
def upload_menu_import(
    response: Response,
    bar_id: Annotated[str, Path(alias="barId", description="Bar id (UUID)")],
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=1, max_length=255, description="Client-generated UUID, reused on retry"),
    ],
    mode: Annotated[ImportMode, Form(description="`full_replace` or `partial_update`")],
    images: Annotated[list[UploadFile], File(description="Menu photos in display order")],
    owner_note: Annotated[str | None, Form(alias="ownerNote", max_length=1000, description="Optional memo")] = None,
    session: Session = Depends(get_session),
    storage: ImageStorage = Depends(get_image_storage),
    extractor: MenuExtractor = Depends(get_menu_extractor),
    _operator: dict[str, Any] = Depends(require_operator),
) -> MenuImportAcceptedResponse:
    menu_import, _created = create_menu_import(
        session,
        storage,
        extractor,
        bar_id=bar_id,
        idempotency_key=idempotency_key,
        mode=mode,
        owner_note=owner_note,
        uploads=[ImageUpload(image.filename, image.content_type, image.file) for image in images],
    )
    status_url = f"/api/menu-imports/{menu_import.id}"
    response.headers["Location"] = status_url
    response.headers["Retry-After"] = str(POLL_AFTER_SECONDS)
    return MenuImportAcceptedResponse(
        menuImportId=menu_import.id,
        status=menu_import.status,
        imageCount=len(menu_import.images),
        statusUrl=status_url,
        pollAfterMs=POLL_AFTER_SECONDS * 1000,
    )
