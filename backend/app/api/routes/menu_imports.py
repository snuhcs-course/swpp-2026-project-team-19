from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Header, Path, Request, Response, UploadFile
from pydantic import WithJsonSchema
from sqlalchemy.orm import Session

from app.adapters.extraction import MenuExtractor
from app.adapters.storage import ImageStorage
from app.api.deps import get_image_storage, get_menu_extractor
from app.core.security import require_operator
from app.db.session import get_serializable_session_factory, get_session, get_session_factory
from app.models import ImportMode
from app.schemas.errors import error_responses
from app.schemas.menu_import import MenuImportAcceptedResponse, MenuImportStatusResponse
from app.schemas.menu_review import ReviewAndApplyRequest, ReviewAppliedResponse
from app.services import menu_import_upload as upload
from app.services.menu_import_processing import SessionFactory, start_processing
from app.services.menu_import_review import POLL_AFTER_MS, get_menu_import_status
from app.services.menu_import_upload import ImageUpload, create_menu_import
from app.services.menu_review_apply import review_and_apply

router = APIRouter(prefix="/api", tags=["menu imports"])

# OpenAPI 3.1 describes files with contentMediaType, which Swagger UI shows as text inputs;
# format: binary makes it render file pickers. The request itself is unaffected.
UploadedImage = Annotated[UploadFile, WithJsonSchema({"type": "string", "format": "binary"})]


@router.post(
    "/bars/{barId}/menu-imports",
    status_code=202,
    response_model=MenuImportAcceptedResponse,
    summary="Upload menu photos and start extraction",
    description=(
        "Operator only. Stores the photos, creates the import, schedules extraction and matching in the "
        "background, and returns `202` with `status: processing` without waiting for them. "
        "Poll `statusUrl` until the status is `ready_for_review` or `failed`.\n\n"
        f"- Up to {upload.MAX_IMAGES} JPEG or PNG photos in display order, "
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
        (415, "`UNSUPPORTED_IMAGE_TYPE`: not JPEG or PNG (HEIC included); `details.imageOrder` names the photo."),
        (422, "`VALIDATION_FAILED`: e.g. `Idempotency-Key` or `images` `MISSING`, or an unknown `mode`."),
    ),
)
def upload_menu_import(
    response: Response,
    background_tasks: BackgroundTasks,
    bar_id: Annotated[str, Path(alias="barId", description="Bar id (UUID)")],
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=1, max_length=255, description="Client-generated UUID, reused on retry"),
    ],
    mode: Annotated[ImportMode, Form(description="`full_replace` or `partial_update`")],
    images: Annotated[list[UploadedImage], File(description="Menu photos in display order")],
    owner_note: Annotated[str | None, Form(alias="ownerNote", max_length=1000, description="Optional memo")] = None,
    session: Session = Depends(get_session),
    storage: ImageStorage = Depends(get_image_storage),
    extractor: MenuExtractor = Depends(get_menu_extractor),
    session_factory: SessionFactory = Depends(get_session_factory),
    _operator: dict[str, Any] = Depends(require_operator),
) -> MenuImportAcceptedResponse:
    menu_import, created = create_menu_import(
        session,
        storage,
        extractor,
        bar_id=bar_id,
        idempotency_key=idempotency_key,
        mode=mode,
        owner_note=owner_note,
        uploads=[ImageUpload(image.filename, image.content_type, image.file) for image in images],
    )
    if created:
        start_processing(
            session,
            background_tasks,
            menu_import,
            session_factory=session_factory,
            storage=storage,
            extractor=extractor,
        )
    status_url = f"/api/menu-imports/{menu_import.id}"
    response.headers["Location"] = status_url
    response.headers["Retry-After"] = str(POLL_AFTER_MS // 1000)
    return MenuImportAcceptedResponse(
        menuImportId=menu_import.id,
        status=menu_import.status,
        imageCount=len(menu_import.images),
        statusUrl=status_url,
        pollAfterMs=POLL_AFTER_MS,
    )


@router.get(
    "/menu-imports/{menuImportId}",
    response_model=MenuImportStatusResponse,
    summary="Import status, or the full review data when ready",
    description=(
        "Operator only. Poll every `pollAfterMs` after uploading. The body depends on `status`:\n\n"
        "- `uploaded` / `processing`: `progress` and `pollAfterMs`. Keep polling.\n"
        "- `failed`: `progress` and `failure` (`IMAGE_EXTRACTION_FAILED` or `PROCESSING_FAILED`). "
        "Stop polling; a failed import is not resumed, so start a new upload.\n"
        "- `ready_for_review`: everything the review screen needs in one response: images with URLs, "
        "every extracted item (non-products too) with options, candidates and `proposedProductId`, "
        "and the draft `proposedChanges` against the current menu. Stop polling.\n"
        "- `applied`: when it was applied and the resulting menu board.\n\n"
        "Proposed products and changes are suggestions; nothing is published until the review is submitted."
    ),
    responses=error_responses(
        (401, "`UNAUTHENTICATED`: missing, invalid or expired token."),
        (403, "`FORBIDDEN`: the caller is not an operator."),
        (404, "`MENU_IMPORT_NOT_FOUND`: no such import or a malformed id."),
    ),
)
def read_menu_import(
    request: Request,
    menu_import_id: Annotated[str, Path(alias="menuImportId", description="Menu import id (UUID)")],
    session: Session = Depends(get_session),
    storage: ImageStorage = Depends(get_image_storage),
    _operator: dict[str, Any] = Depends(require_operator),
) -> MenuImportStatusResponse:
    return get_menu_import_status(session, menu_import_id, storage, str(request.base_url))


@router.post(
    "/menu-imports/{menuImportId}/review-and-apply",
    response_model=ReviewAppliedResponse,
    summary="Submit the review and publish the menu",
    description=(
        "Operator only. Submits every decision of the review screen at once. Catalog changes, the "
        "decisions and the new menu board are saved in one transaction; on any error nothing is saved "
        "and the import stays `ready_for_review`.\n\n"
        "**Decisions.** `itemDecisions` has exactly one entry per extracted item and `changeDecisions` "
        "one per proposed change. Option corrections that are null or left out keep the extracted value. "
        "Options without a price are not published; a published product needs at least one.\n\n"
        "**What gets published.** The reviewer's decisions are final:\n"
        "- Each product line is published with its chosen product and options, unless its proposed "
        "change is `ignore`d. The first line of a product wins.\n"
        "- Against the current board that is an add, an update or nothing. Changes the draft did not "
        "show (an update from a price correction, an add after choosing another product) are applied "
        "too, as the reviewer's own decisions.\n"
        "- A board entry leaves the board only through an applied `remove`, and stays if a line "
        "publishes its product again.\n"
        "- `full_replace`: photo order, then kept entries in their old order. `partial_update`: old "
        "order with updates in place, adds at the end.\n\n"
        "**New brands and products** are checked again for duplicates first: a submitted name equal "
        "(after normalization) to an existing alias, or for products the same brand, category, age and "
        "edition, inactive products included. Similar-name search (flow doc 16.1) is not done. Two lines "
        "creating the same new brand or product in one submission share one row.\n\n"
        "**Retries.** Repeating the request after it was applied returns the stored result. "
        "A serialization conflict is retried up to three attempts, then `503`."
    ),
    responses=error_responses(
        (401, "`UNAUTHENTICATED`: missing, invalid or expired token."),
        (403, "`FORBIDDEN`: the caller is not an operator."),
        (404, "`MENU_IMPORT_NOT_FOUND`: no such import or a malformed id."),
        (
            409,
            "`INVALID_IMPORT_STATE` (not `ready_for_review`); `REVIEW_OUTDATED` (`reviewVersion` differs, or "
            "the board changed since the draft: the draft is rebuilt with a new version; fetch "
            "`details.reviewUrl` and submit again); `DUPLICATE_BRAND_FOUND` / `DUPLICATE_PRODUCT_FOUND` "
            "(`details.existingBrand` / `existingProduct` and `extractedItemId`; select the existing one).",
        ),
        (
            422,
            "`VALIDATION_FAILED`, every problem in `fieldErrors`. Besides shape errors: `UNKNOWN_ITEM`, "
            "`DUPLICATE_ITEM`, `MISSING_ITEM`, `UNKNOWN_CHANGE`, `DUPLICATE_CHANGE`, `MISSING_CHANGE`, "
            "`UNKNOWN_OPTION`, `DUPLICATE_OPTION`, `NO_PRICED_OPTION`, `DUPLICATE_OPTION_VALUES`, "
            "`PRODUCT_NOT_FOUND`, `PRODUCT_INACTIVE`, `BRAND_NOT_FOUND`, `NOT_NORMALIZABLE`, "
            "`CHANGE_WITHOUT_PRODUCT`.",
        ),
        (503, "`TEMPORARY_WRITE_CONFLICT`: conflicted with concurrent writes three times; submit again."),
    ),
)
def submit_menu_review(
    body: ReviewAndApplyRequest,
    menu_import_id: Annotated[str, Path(alias="menuImportId", description="Menu import id (UUID)")],
    session_factory: SessionFactory = Depends(get_serializable_session_factory),
    _operator: dict[str, Any] = Depends(require_operator),
) -> ReviewAppliedResponse:
    return review_and_apply(session_factory, menu_import_id, body)
