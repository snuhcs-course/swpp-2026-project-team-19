"""Owner applications (API spec, section 3.11): the requests of applying, approving and rejecting,
and the `OwnerApplication` response every application API returns.

The request is one of two shapes picked by `applicationType`; a field of the other shape is
rejected (`EXTRA_FORBIDDEN`), e.g. `proposedBar` on an `existing_bar` application.
"""

import re
from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_core import PydanticCustomError

from app.core.business_number import normalize_business_number
from app.core.errors import register_union_tags
from app.schemas.common import UtcDateTime

DATE_TEXT = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")

ApplicationType = Literal["existing_bar", "new_bar"]
ApplicationStatus = Literal["pending", "approved", "rejected", "canceled"]
VerificationResult = Literal["matched", "not_matched", "unavailable"]
BusinessStatusValue = Literal["active", "suspended", "closed"]


class _Strict(BaseModel):
    # Values are stored as sent, so surrounding spaces are dropped; a blank value then fails min_length.
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ProposedBarInput(_Strict):
    name: str = Field(min_length=1, max_length=150)
    address: str = Field(min_length=1, max_length=500)
    phone: str | None = Field(default=None, max_length=30)


class _ApplicationInput(_Strict):
    businessRegistrationNumber: str = Field(
        description="10 digits; hyphens and spaces are removed. The last digit must be the NTS check digit"
    )
    representativeName: str = Field(min_length=1, max_length=100, description="As on the certificate")
    openingDate: date = Field(description="`YYYY-MM-DD`, as on the certificate; not after today (KST)")
    contactPhone: str = Field(min_length=1, max_length=30, description="For the operator to reach the applicant")
    applicantNote: str | None = Field(default=None, max_length=500, description="Blank is stored as null")

    @field_validator("businessRegistrationNumber")
    @classmethod
    def _business_number(cls, value: str) -> str:
        digits = normalize_business_number(value)
        if digits is None:
            raise PydanticCustomError("invalid_business_number", "사업자등록번호를 확인해 주세요.")
        return digits

    @field_validator("openingDate", mode="before")
    @classmethod
    def _date_text(cls, value: object) -> object:
        # Only `YYYY-MM-DD` text: Pydantic would otherwise read a number as a Unix timestamp and accept
        # a midnight datetime such as "2020-03-02T00:00:00". A day that does not exist still fails below.
        if not isinstance(value, str):
            raise PydanticCustomError("date_type", "Input should be a valid date in YYYY-MM-DD format")
        if not DATE_TEXT.fullmatch(value):
            raise PydanticCustomError("date_from_datetime_parsing", "Input should be a valid date in YYYY-MM-DD format")
        return value

    @field_validator("applicantNote")
    @classmethod
    def _blank_note(cls, value: str | None) -> str | None:
        return value or None


class ExistingBarApplicationInput(_ApplicationInput):
    applicationType: Literal["existing_bar"]
    # Not a UUID type: a malformed id is 404 BAR_NOT_FOUND (spec 3.11.2), not a validation error.
    barId: str = Field(description="An active bar, found with GET /api/search/bar-names")


class NewBarApplicationInput(_ApplicationInput):
    applicationType: Literal["new_bar"]
    proposedBar: ProposedBarInput


class BarInput(_Strict):
    """A bar's details as an operator confirms them; the field rules of spec 3.5, 3.7 and 3.11.7."""

    name: str = Field(min_length=1, max_length=150)
    address: str = Field(min_length=1, max_length=500, description="Display address with floor or unit")
    latitude: float = Field(ge=-90, le=90, description="Stored to 6 decimal places")
    longitude: float = Field(ge=-180, le=180, description="Stored to 6 decimal places")
    phone: str | None = Field(default=None, max_length=30, description="Blank is stored as null")

    @field_validator("phone")
    @classmethod
    def _blank_phone(cls, value: str | None) -> str | None:
        return value or None


class ApproveInput(_Strict):
    bar: BarInput | None = Field(
        default=None, description="new_bar only: the confirmed bar, prefilled from `proposedBar` with coordinates added"
    )


class RejectInput(_Strict):
    reason: str = Field(max_length=500, description="Shown to the applicant as it is")

    @field_validator("reason")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value:
            raise PydanticCustomError("blank", "거절 사유를 입력해 주세요.")
        return value


# The route declares the discriminator on Body(): FastAPI drops one set inside an Annotated union here.
OwnerApplicationInput = ExistingBarApplicationInput | NewBarApplicationInput
register_union_tags("existing_bar", "new_bar")


class Applicant(BaseModel):
    userId: UUID
    email: str | None
    displayName: str | None


class ApplicationBar(BaseModel):
    barId: UUID
    name: str
    address: str


class ProposedBar(BaseModel):
    name: str
    address: str
    phone: str | None


class BusinessVerification(BaseModel):
    result: VerificationResult
    checkedAt: UtcDateTime = Field(description="When `result` was obtained")


class ApplicationMenuPhoto(BaseModel):
    imageOrder: int = Field(description="1-based display order")
    imageUrl: str = Field(description="Short-lived signed URL; fetch the application again when it expires")
    imageUrlExpiresAt: UtcDateTime | None = Field(description="Null when the URL does not expire (local storage)")


class OwnerApplicationResponse(BaseModel):
    applicationId: UUID
    applicationType: ApplicationType
    status: ApplicationStatus
    applicant: Applicant
    bar: ApplicationBar | None = Field(
        description="existing_bar: the claimed bar. new_bar: the bar its approval created; null before that"
    )
    proposedBar: ProposedBar | None = Field(description="new_bar only")
    businessRegistrationNumber: str = Field(description="10 digits without hyphens")
    representativeName: str
    openingDate: date
    businessStatus: BusinessStatusValue | None = Field(
        description="From the latest NTS check; null unless it matched and NTS gave a status"
    )
    businessVerification: BusinessVerification | None = Field(
        description="Operators only; null for the applicant"
    )
    contactPhone: str
    applicantNote: str | None
    menuPhotos: list[ApplicationMenuPhoto] = Field(
        description="Menu photos in order (spec 3.11.15); empty when none were uploaded or after rejection or cancel"
    )
    rejectionReason: str | None = Field(description="Only when rejected")
    reviewedAt: UtcDateTime | None = Field(description="When approved or rejected")
    createdAt: UtcDateTime
    updatedAt: UtcDateTime


class OwnerApplicationListResponse(BaseModel):
    items: list[OwnerApplicationResponse] = Field(description="Newest first")


class OwnerApplicationPage(BaseModel):
    items: list[OwnerApplicationResponse] = Field(
        description="Oldest first for `status=pending` (processing order), newest first otherwise"
    )
    nextCursor: str | None = Field(description="Pass as `cursor` with the same filters; null on the last page")
