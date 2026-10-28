from collections.abc import Callable
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File

from app.adapters.certificate_ocr import CertificateOcr
from app.api.deps import get_certificate_ocr, get_clock, get_request_limiter
from app.api.routes.menu_imports import UploadedImage
from app.core.security import Principal, get_current_user
from app.schemas.business_certificate import BusinessCertificateOcrResponse
from app.schemas.errors import AUTH_UNAVAILABLE_DESCRIPTION, error_responses
from app.services.business_certificate import CertificateUpload, read_business_certificate
from app.services.menu_import_upload import MAX_IMAGE_BYTES
from app.services.request_limits import DAILY_LIMIT, DailyRequestLimiter

router = APIRouter(prefix="/api", tags=["owner applications"])


@router.post(
    "/owner-applications/business-certificate-ocr",
    response_model=BusinessCertificateOcrResponse,
    summary="Read a business registration certificate photo to prefill an owner application",
    description=(
        "Any signed-in user; no `users` row is needed. Reads one photo of a business registration "
        "certificate with CLOVA OCR and returns the values found by fixed rules, to prefill the owner "
        "application form. The applicant must check them before applying; this API does not verify them "
        "(that happens in `POST /api/owner-applications`).\n\n"
        f"- `image`: exactly one JPEG or PNG of at most {MAX_IMAGE_BYTES // 2**20} MB, checked like menu uploads.\n"
        "- Fields that were not read are null; reading nothing is still `200` with every field null.\n"
        f"- At most {DAILY_LIMIT} OCR calls per user (token `sub`) per day, reset at midnight KST. A request is "
        "counted when it passes the `413`/`415`/`422` checks and the OCR is called, even if the call fails.\n"
        "- The photo and the values are not stored and not logged."
    ),
    responses=error_responses(
        (401, "`UNAUTHENTICATED`: missing, invalid or expired token."),
        (413, "`UPLOAD_TOO_LARGE`: the photo is larger than `details.maxImageBytes`."),
        (415, "`UNSUPPORTED_IMAGE_TYPE`: not JPEG or PNG, or the declared type disagrees with the content."),
        (422, "`VALIDATION_FAILED`: `image` `MISSING`, or more than one image (`TOO_LONG`)."),
        (429, "`RATE_LIMITED`: today's OCR calls are used up; `details.retryAfter` is the next reset (UTC)."),
        (
            503,
            "`OCR_UNAVAILABLE`: OCR is not configured on the server, or the call failed after a retry; "
            "enter the values by hand. " + AUTH_UNAVAILABLE_DESCRIPTION,
        ),
    ),
)
def read_certificate(
    image: Annotated[list[UploadedImage], File(description="One photo of the business registration certificate")],
    principal: Principal = Depends(get_current_user),
    ocr: CertificateOcr | None = Depends(get_certificate_ocr),
    limiter: DailyRequestLimiter = Depends(get_request_limiter),
    clock: Callable[[], datetime] = Depends(get_clock),
) -> BusinessCertificateOcrResponse:
    fields = read_business_certificate(
        [CertificateUpload(upload.filename, upload.content_type, upload.file) for upload in image],
        subject=principal.subject,
        ocr=ocr,
        limiter=limiter,
        now=clock(),
    )
    return BusinessCertificateOcrResponse(
        businessRegistrationNumber=fields.business_registration_number,
        representativeName=fields.representative_name,
        openingDate=fields.opening_date,
        businessName=fields.business_name,
        address=fields.address,
    )
