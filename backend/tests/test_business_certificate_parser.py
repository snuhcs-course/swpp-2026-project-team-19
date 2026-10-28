"""Reading certificate fields from synthetic CLOVA OCR responses (spec 3.11.12). No OCR is called."""

from datetime import date

import pytest

from app.adapters import clova_certificate_ocr
from app.adapters.certificate_ocr import OcrLine, OcrWord
from app.adapters.clova_certificate_ocr import ClovaCertificateOcr
from app.core.business_number import check_digit, is_valid_business_number, normalize_business_number
from app.extraction.clova import ClovaSettings
from app.services.business_certificate import CertificateFields, parse_certificate, parse_date
from tests.certificate_support import (
    FOOTER,
    INVALID_NUMBER,
    KIND,
    TITLE,
    corporate_certificate,
    individual_certificate,
    jpeg,
    response,
    row,
)

TODAY = date(2026, 10, 28)
SETTINGS = ClovaSettings(invoke_url="https://ocr.example.test/general", secret="clova-secret")


def lines_of(ocr_response: dict, monkeypatch) -> list[OcrLine]:
    """The lines the CLOVA adapter makes from a response, with the HTTP call replaced."""
    monkeypatch.setattr(
        clova_certificate_ocr, "call_ocr", lambda settings, image, mime_type: {"response": ocr_response, "attempts": 1}
    )
    return ClovaCertificateOcr(SETTINGS).read_lines(jpeg(), "image/jpeg")


@pytest.fixture
def read(monkeypatch):
    return lambda ocr_response: parse_certificate(lines_of(ocr_response, monkeypatch), today=TODAY)


# ---- business number check digit ----


@pytest.mark.parametrize("first_nine", ["123456789", "000000000", "999999999", "220816251", "101010101"])
def test_check_digit_completes_a_valid_number(first_nine):
    digit = check_digit(first_nine)
    assert is_valid_business_number(first_nine + str(digit))
    assert not is_valid_business_number(first_nine + str((digit + 1) % 10))


def test_check_digit_by_hand():
    # 1x1 + 2x3 + 3x7 + 4x1 + 5x3 + 6x7 + 7x1 + 8x3 + 9x5 = 165, + (9x5)//10 = 4 -> 169 -> 1
    assert check_digit("123456789") == 1
    # The tens digit of 9th x 5 matters: 0..0 then 8 -> 8x5 = 40 + 4 = 44 -> 6
    assert check_digit("000000008") == 6


@pytest.mark.parametrize("digits", ["123456789", "12345678911", "12345678a1", "１２３４５６７８９１", ""])
def test_only_ten_ascii_digits_are_valid(digits):
    assert not is_valid_business_number(digits)


@pytest.mark.parametrize("text", ["123-45-67891", "123 45 67891", "1234567891", " 123 - 45 - 67891 "])
def test_normalize_removes_hyphens_and_spaces(text):
    assert normalize_business_number(text) == "1234567891"


def test_normalize_rejects_a_wrong_check_digit():
    assert normalize_business_number(INVALID_NUMBER) is None


# ---- whole certificates ----


def test_individual_certificate_reads_every_field(read):
    assert read(individual_certificate()) == CertificateFields(
        business_registration_number="1234567891",
        representative_name="김사장",
        opening_date=date(2020, 3, 2),
        business_name="신림 몰트 하우스",
        address="서울특별시 관악구 신림로 2 3층",
    )


def test_corporate_certificate_reads_every_field(read):
    assert read(corporate_certificate()) == CertificateFields(
        business_registration_number="1234567891",
        representative_name="이대표",
        opening_date=date(2019, 11, 4),
        business_name="주식회사 몰트앤코",
        address="부산광역시 해운대구 우동 1",  # 본점소재지 is a different label
    )


def test_wrong_check_digit_gives_null_number_and_keeps_the_rest(read):
    fields = read(individual_certificate(INVALID_NUMBER))
    assert fields.business_registration_number is None
    assert fields.representative_name == "김사장"


def test_nothing_readable_gives_all_null(read):
    assert read(response(row(100, "흐릿한", "사진"), row(200, "%%%"))) == CertificateFields()
    assert read({"images": [{"inferResult": "SUCCESS", "fields": []}]}) == CertificateFields()


def test_missing_fields_are_null(read):
    fields = read(response(TITLE, row(150, "상", "호", ":", "몰트", "바"), row(200, "대표자", ":"), *FOOTER))
    assert fields == CertificateFields(business_name="몰트 바")  # the footer date is not the opening date


# ---- number variants ----


@pytest.mark.parametrize(
    "words",
    [
        ("등록번호", ":", "123-45-67891"),
        ("등록번호", ":", "123", "-", "45", "-", "67891"),
        ("등록번호", "1234567891"),
        ("등록번호:", "123-45-", "67891"),
        ("사업자등록번호", ":", "123 45 67891"),
        ("등", "록", "번", "호", "：", "123-45-67891"),
    ],
)
def test_number_variants(read, words):
    assert read(response(row(150, *words))).business_registration_number == "1234567891"


def test_number_without_a_label_needs_hyphens(read):
    assert read(response(row(150, "123-45-67891"))).business_registration_number == "1234567891"
    assert read(response(row(150, "1234567891"))).business_registration_number is None


def test_corporate_and_resident_numbers_are_not_the_business_number(read):
    fields = read(response(row(150, "법인등록번호", ":", "110111-1234567"), row(200, "주민등록번호", ":", "800101-1234567")))
    assert fields.business_registration_number is None


def test_labelled_misread_number_is_null_even_if_another_number_is_valid(read):
    fields = read(response(row(150, "등록번호", ":", INVALID_NUMBER), row(600, "참고", "123-45-67891")))
    assert fields.business_registration_number is None


# ---- dates ----


@pytest.mark.parametrize(
    "text, expected",
    [
        ("2020 년 03 월 02 일", date(2020, 3, 2)),
        ("2020년3월2일", date(2020, 3, 2)),
        ("2020.03.02", date(2020, 3, 2)),
        ("2020. 03. 02.", date(2020, 3, 2)),
        ("2020-03-02", date(2020, 3, 2)),
        ("2020/3/2", date(2020, 3, 2)),
        ("20200302", date(2020, 3, 2)),
        ("2026 년 10 월 28 일", TODAY),
    ],
)
def test_date_forms(text, expected):
    assert parse_date(text, TODAY) == expected


@pytest.mark.parametrize(
    "text", ["2026 년 10 월 29 일", "2030.01.01", "2020 년 13 월 02 일", "2021.02.30", "1899.12.31", "2020 년", "미상", ""]
)
def test_future_impossible_or_unreadable_dates_are_null(text):
    assert parse_date(text, TODAY) is None


def test_future_opening_date_is_null_in_a_certificate(read):
    fields = read(response(row(300, "개업연월일", ":", "2027", "년", "01", "월", "01", "일")))
    assert fields.opening_date is None


def test_birth_date_is_not_the_opening_date(read):
    assert read(response(row(250, "생", "년", "월", "일", ":", "1980.01.01"))).opening_date is None


# ---- layouts ----


def test_label_and_value_split_into_two_ocr_lines_on_one_row(read):
    """CLOVA breaks the row after the label: the value is the line to its right."""
    fields = read(
        response(
            row(150, "등록번호", ":"),
            row(150, (300, "123-45-67891")),
            row(200, "상", "호", ":"),
            row(200, (300, "신림"), "몰트", "하우스"),
            row(250, "대표자", ":"),
            row(252, (300, "김사장")),
        )
    )
    assert (fields.business_registration_number, fields.business_name, fields.representative_name) == (
        "1234567891",
        "신림 몰트 하우스",
        "김사장",
    )


def test_two_column_layout_read_column_by_column(read):
    """All labels first, then all values: each value is matched by its row, not by order."""
    fields = read(
        response(
            row(150, "등록번호", ":"),
            row(200, "상호", ":"),
            row(250, "대표자", ":"),
            row(300, "개업연월일", ":"),
            row(350, "사업장소재지", ":"),
            row(150, (400, "123-45-67891")),
            row(200, (400, "신림"), "몰트", "하우스"),
            row(250, (400, "김사장")),
            row(300, (400, "2020.03.02")),
            row(350, (400, "서울특별시"), "관악구", "신림로", "2"),
        )
    )
    assert fields == CertificateFields("1234567891", "김사장", date(2020, 3, 2), "신림 몰트 하우스", "서울특별시 관악구 신림로 2")


def test_value_on_the_line_below_the_label(read):
    fields = read(response(row(150, "상호(법인명)", ":"), row(190, "신림", "몰트", "하우스"), row(240, "대표자(성명)", ":", "김사장")))
    assert (fields.business_name, fields.representative_name) == ("신림 몰트 하우스", "김사장")


def test_a_label_line_below_is_not_taken_as_the_value(read):
    fields = read(response(row(200, "상", "호", ":"), row(240, "성", "명", ":", "김사장")))
    assert (fields.business_name, fields.representative_name) == (None, "김사장")


def test_a_far_line_below_is_not_taken_as_the_value(read):
    assert read(response(row(200, "상호", ":"), row(400, "몰트", "바"))).business_name is None


def test_a_label_in_the_middle_of_a_row_with_nothing_after_it(read):
    fields = read(response(row(250, "성명", ":", (600, "생년월일"), ":", "1980.01.01")))
    assert fields.representative_name is None


def test_two_labels_on_one_row(read):
    fields = read(response(row(250, "상호", ":", "몰트", "바", (600, "성명"), ":", "김사장")))
    assert (fields.business_name, fields.representative_name) == ("몰트 바", "김사장")


def test_label_letters_inside_a_word_are_not_a_label(read):
    assert read(response(row(200, "대상호텔", ":", "몰트"))).business_name is None


def test_label_on_the_last_line_with_no_value(read):
    assert read(response(row(250, "대표자", ":"))).representative_name is None


def test_letter_spaced_name_is_joined(read):
    assert read(response(row(250, "대표자", ":", "김", "사", "장"))).representative_name == "김사장"


def test_short_label_inside_a_value_does_not_cut_it(read):
    fields = read(response(row(200, "상호", ":", "업태", "종목", "상호", "바")))
    assert fields.business_name == "업태 종목 상호 바"


def test_address_stops_before_a_line_under_the_labels(read):
    fields = read(response(row(350, "사업장소재지", ":", "서울특별시", "관악구"), row(390, "(전화번호", "없음)")))
    assert fields.address == "서울특별시 관악구"


def test_address_takes_at_most_two_wrapped_lines(read):
    fields = read(
        response(
            row(350, "사업장소재지", ":", "서울특별시"),
            row(390, (220, "관악구")),
            row(430, (220, "신림로"), "2"),
            row(470, (220, "3층")),
        )
    )
    assert fields.address == "서울특별시 관악구 신림로 2"


def test_address_does_not_take_the_next_fields_value_in_a_column_layout(read):
    """Codex review: labels first, values after; 발급 사유's value sits right under the address value."""
    fields = read(
        response(
            row(350, "사업장소재지", ":"),
            row(390, "발급", "사유", ":"),
            row(350, (400, "서울특별시"), "관악구", "신림로", "2"),
            row(390, (400, "신규")),
        )
    )
    assert fields.address == "서울특별시 관악구 신림로 2"


def test_address_wrap_in_a_column_layout_is_still_joined(read):
    fields = read(
        response(
            row(350, "사업장소재지", ":"),
            row(440, "사업의", "종류", ":"),
            row(350, (400, "서울특별시"), "관악구"),
            row(390, (400, "신림로"), "2"),
            row(440, (400, "업태"), "음식점업"),
        )
    )
    assert fields.address == "서울특별시 관악구 신림로 2"


def test_values_over_the_application_limits_are_null(read):
    long_name = "가" * 151
    fields = read(response(row(200, "상호", ":", long_name), row(250, "대표자", ":", "나" * 101)))
    assert (fields.business_name, fields.representative_name) == (None, None)


def test_kind_line_and_title_are_ignored(read):
    assert read(response(TITLE, KIND)) == CertificateFields()


def test_lines_without_boxes():
    words = [OcrWord(text, (0, 0, 0, 0)) for text in ("상호", ":")]
    lines = [OcrLine(tuple(words)), OcrLine((OcrWord("몰트바", (0, 0, 0, 0)),))]
    assert parse_certificate(lines, today=TODAY).business_name == "몰트바"
