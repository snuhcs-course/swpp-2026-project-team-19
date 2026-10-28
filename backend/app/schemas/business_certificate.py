from datetime import date

from pydantic import BaseModel, Field


class BusinessCertificateOcrResponse(BaseModel):
    businessRegistrationNumber: str | None = Field(
        description="10 digits without hyphens; null when not read or when the NTS check digit is wrong",
        examples=["1234567891"],
    )
    representativeName: str | None = Field(description="대표자 성명; null when not read", examples=["김사장"])
    openingDate: date | None = Field(
        description="개업연월일; null when not read, not a date, or after today (KST)", examples=["2020-03-02"]
    )
    businessName: str | None = Field(
        description="상호; can prefill proposedBar.name of a new_bar application", examples=["신림 몰트 하우스"]
    )
    address: str | None = Field(
        description="사업장 소재지; can prefill proposedBar.address of a new_bar application",
        examples=["서울특별시 관악구 신림로 2 3층"],
    )
