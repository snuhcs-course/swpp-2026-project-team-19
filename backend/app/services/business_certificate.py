"""Read a business registration certificate photo to prefill an owner application (spec 3.11.12).

Order: one JPEG/PNG of at most 10 MB (`422`, `413`, `415`, as in the menu upload) → OCR configured
(`503`, not counted) → today's OCR count (`429`, 3.11.14) → one OCR call (`503` on failure,
counted) → fields found by fixed rules. Nothing is stored, and neither the photo nor any value
read from it is logged: the values are the applicant's personal data.

The rules follow the National Tax Service certificate form: each value follows its label
(등록번호, 상호 or 법인명, 대표자 or 성명, 개업연월일, 사업장소재지), on the same line or, when OCR
breaks the row, on the line to its right or just below. Labels may be letter-spaced and may
share a row with another label (성 명 : ... 생 년 월 일 : ...).
"""

import logging
import re
import statistics
from dataclasses import dataclass
from datetime import date, datetime
from typing import BinaryIO

from app.adapters.certificate_ocr import CertificateImageError, CertificateOcr, CertificateOcrError, OcrLine
from app.core.business_number import normalize_business_number
from app.core.errors import ApiError, validation_failed
from app.services.menu_import_upload import MAX_IMAGE_BYTES, check_image_type
from app.services.request_limits import BUSINESS_CERTIFICATE_OCR, DailyRequestLimiter, acquire_or_raise, kst_date

logger = logging.getLogger(__name__)

RATE_LIMITED_MESSAGE = "오늘 사업자등록증 사진 읽기 횟수를 모두 사용했습니다. 값을 직접 입력해 주세요."
OCR_UNAVAILABLE_MESSAGE = "지금은 사업자등록증 사진을 읽을 수 없습니다. 값을 직접 입력해 주세요."

# The owner application limits (3.11.2): a longer value is a misread, not something to prefill.
MAX_REPRESENTATIVE_NAME = 100
MAX_BUSINESS_NAME = 150
MAX_ADDRESS = 500
MIN_OPENING_YEAR = 1900
MAX_ADDRESS_CONTINUATION_LINES = 2


@dataclass
class CertificateUpload:
    filename: str | None
    content_type: str | None
    stream: BinaryIO


@dataclass(frozen=True)
class CertificateFields:
    business_registration_number: str | None = None
    representative_name: str | None = None
    opening_date: date | None = None
    business_name: str | None = None
    address: str | None = None


# ---- the request ----


def check_certificate_image(uploads: list[CertificateUpload]) -> tuple[bytes, str]:
    """(bytes, detected MIME type) of the one photo, or 422 / 413 / 415 like the menu upload (4.1)."""
    if len(uploads) != 1:
        raise validation_failed("image", "TOO_LONG", "List should have at most 1 item after validation")
    upload = uploads[0]
    # Read one byte past the limit to tell "exactly at the limit" from "over it".
    data = upload.stream.read(MAX_IMAGE_BYTES + 1)
    if len(data) > MAX_IMAGE_BYTES:
        raise ApiError(413, "UPLOAD_TOO_LARGE", "사진 크기가 너무 큽니다.", details={"maxImageBytes": MAX_IMAGE_BYTES})
    detected = check_image_type(data, upload.content_type)
    if detected is None:
        raise ApiError(415, "UNSUPPORTED_IMAGE_TYPE", "JPEG, PNG 사진만 올릴 수 있습니다.")
    return data, detected[1]


def ocr_unavailable() -> ApiError:
    return ApiError(503, "OCR_UNAVAILABLE", OCR_UNAVAILABLE_MESSAGE)


def read_business_certificate(
    uploads: list[CertificateUpload],
    *,
    subject: str,
    ocr: CertificateOcr | None,
    limiter: DailyRequestLimiter,
    now: datetime,
) -> CertificateFields:
    data, content_type = check_certificate_image(uploads)
    if ocr is None:
        raise ocr_unavailable()
    day = acquire_or_raise(limiter, subject, BUSINESS_CERTIFICATE_OCR, now, RATE_LIMITED_MESSAGE)
    try:
        lines = ocr.read_lines(data, content_type)
    except CertificateImageError as error:
        # Nothing was sent to the OCR service, so the request is not counted.
        limiter.release(subject, BUSINESS_CERTIFICATE_OCR, day)
        raise ApiError(415, "UNSUPPORTED_IMAGE_TYPE", "사진 파일을 읽을 수 없습니다. JPEG로 바꿔 다시 올려 주세요.") from error
    except CertificateOcrError as error:
        # The message names only the HTTP status or error type, never the photo or its text.
        logger.warning("Business certificate OCR failed: %s", error)
        raise ocr_unavailable() from error
    return parse_certificate(lines, today=kst_date(now))


# ---- labels ----


def _spaced(word: str) -> str:
    """A label that OCR may read with spaces between its letters: 상호 also matches "상   호"."""
    return r"\s*".join(re.escape(c) for c in word)


# (field, label words). Labels that are not wanted are listed too, so a value stops where the
# next label starts and a label line is never taken as another label's value.
_LABELS: list[tuple[str, tuple[str, ...]]] = [
    ("number", ("사업자등록번호", "등록번호")),
    ("other", ("법인등록번호", "주민등록번호")),
    ("business_name", ("상호명", "상호", "법인명", "단체명")),
    ("representative", ("대표자성명", "대표자명", "대표자", "성명")),
    ("opening_date", ("개업연월일", "개업년월일")),
    ("other", ("생년월일",)),
    ("address", ("사업장소재지", "사업장주소")),
    (
        "other",
        (
            "본점소재지",
            "사업의종류",
            "업태",
            "종목",
            "발급사유",
            "공동사업자",
            "사업자단위과세적용사업자여부",
            "전자세금계산서전용전자우편주소",
        ),
    ),
]
_LABEL_FIELD: dict[str, str] = {word: name for name, words in _LABELS for word in words}
# Longest first, so 법인등록번호 wins over 등록번호 and 대표자성명 over 대표자.
_LABEL_WORDS = sorted(_LABEL_FIELD, key=len, reverse=True)
_LABEL_RE = re.compile(
    "|".join(f"(?P<l{i}>{_spaced(word)})" for i, word in enumerate(_LABEL_WORDS))
)
# After a label: an optional note such as (법인명) or (성명), then a colon (optional in _AFTER_LABEL).
_AFTER_LABEL = re.compile(r"\s*(?:[(（][^)）]{0,12}[)）])?\s*[:：;]?")
_COLON_AFTER = re.compile(r"\s*(?:[(（][^)）]{0,12}[)）])?\s*[:：;]")
_HANGUL_OR_ALNUM = re.compile(r"[0-9A-Za-z가-힣]")
_LONG_LABEL = 4  # letters; shorter labels (상호, 성명, 업태, ...) need a colon or the start of a line


@dataclass(frozen=True)
class _Label:
    field: str
    start: int  # where the label starts in the line text
    value_start: int  # after the label, its note and colon


def _find_labels(text: str) -> list[_Label]:
    labels = []
    for match in _LABEL_RE.finditer(text):
        word = _LABEL_WORDS[int(match.lastgroup[1:])]
        start, end = match.span()
        # Not inside a word: 등록번호 in 사업자등록번호 is matched as the longer label instead.
        if start > 0 and _HANGUL_OR_ALNUM.match(text[start - 1]):
            continue
        at_line_start = not _HANGUL_OR_ALNUM.search(text[:start])
        if len(word) < _LONG_LABEL and not at_line_start and not _COLON_AFTER.match(text, end):
            continue
        after = _AFTER_LABEL.match(text, end)
        labels.append(_Label(_LABEL_FIELD[word], start, after.end()))
    return labels


@dataclass(frozen=True)
class _Line:
    """An OCR line with its labels and where each word starts in its text."""

    line: OcrLine
    labels: list[_Label]
    offsets: list[int]

    @property
    def text(self) -> str:
        return self.line.text

    @property
    def box(self) -> tuple[float, float, float, float]:
        return self.line.box

    @property
    def starts_with_label(self) -> bool:
        return bool(self.labels) and not _HANGUL_OR_ALNUM.search(self.text[: self.labels[0].start])

    def text_before_label(self, start: int = 0) -> str:
        """From `start` to the next label after it."""
        end = next((label.start for label in self.labels if label.start >= start), len(self.text))
        return self.text[start:end]

    def x_at(self, offset: int) -> float:
        """Left edge of the word holding the character at `offset` (or the first word after it)."""
        ends = (start + len(word.text) for word, start in zip(self.line.words, self.offsets))
        return next((word.box[0] for word, end in zip(self.line.words, ends) if end > offset), self.box[2])


def _prepare(lines: list[OcrLine]) -> list[_Line]:
    prepared = []
    for line in lines:
        offsets, position = [], 0
        for word in line.words:
            offsets.append(position)
            position += len(word.text) + 1
        prepared.append(_Line(line, _find_labels(line.text), offsets))
    return prepared


def _height(line: _Line) -> float:
    return max(1.0, statistics.median(w.box[3] - w.box[1] for w in line.line.words))


def _same_row(a: _Line, b: _Line) -> bool:
    ay0, ay1 = a.box[1], a.box[3]
    by0, by1 = b.box[1], b.box[3]
    overlap = min(ay1, by1) - max(ay0, by0)
    return overlap >= 0.5 * min(ay1 - ay0, by1 - by0) and overlap > 0


# ---- values ----


@dataclass(frozen=True)
class _Value:
    text: str
    line_index: int
    x0: float  # left edge of the value, for address continuation lines


def _values_for(lines: list[_Line], field: str) -> list[_Value]:
    """Every value written after a label of `field`, in reading order."""
    values = []
    for index, line in enumerate(lines):
        for position, label in enumerate(line.labels):
            if label.field != field:
                continue
            text = line.text_before_label(label.value_start)
            if _clean(text):
                values.append(_Value(text, index, line.x_at(label.value_start)))
                continue
            # Nothing after the label on this line. If it is the last label of the line, the value
            # is on another OCR line: to its right on the same row, or else just below.
            if position == len(line.labels) - 1:
                found = _value_beside(lines, index) or _value_below(lines, index)
                if found is not None:
                    values.append(found)
    return values


def _value_beside(lines: list[_Line], index: int) -> _Value | None:
    anchor = lines[index]
    tolerance = _height(anchor)
    beside = [
        (other.box[0], i)
        for i, other in enumerate(lines)
        if i != index
        and not other.starts_with_label
        and _same_row(anchor, other)
        and other.box[0] >= anchor.box[2] - tolerance
    ]
    if not beside:
        return None
    _, i = min(beside)
    return _Value(lines[i].text_before_label(), i, lines[i].box[0])


def _value_below(lines: list[_Line], index: int) -> _Value | None:
    if index + 1 >= len(lines):
        return None
    anchor, below = lines[index], lines[index + 1]
    if below.starts_with_label or _same_row(anchor, below) or below.box[1] < anchor.box[1]:
        return None
    if below.box[1] - anchor.box[3] > 2 * _height(anchor):
        return None
    return _Value(below.text_before_label(), index + 1, below.box[0])


def _clean(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text.strip(" :：;,.·-|")


def _first(values: list[_Value], parse) -> object | None:
    for value in values:
        parsed = parse(value)
        if parsed is not None:
            return parsed
    return None


# ---- fields ----

_NUMBER_IN_TEXT = re.compile(r"(?<!\d)\d{3}\s*-?\s*\d{2}\s*-?\s*\d{5}(?!\d)")
_HYPHENATED_NUMBER = re.compile(r"(?<!\d)\d{3}\s*-\s*\d{2}\s*-\s*\d{5}(?!\d)")
_DATE_WITH_SEPARATORS = re.compile(
    r"(?<!\d)(\d{4})\s*(?:년|[.\-/])\s*(\d{1,2})\s*(?:월|[.\-/])\s*(\d{1,2})(?!\d)"
)
_DATE_DIGITS = re.compile(r"(?<!\d)(\d{4})(\d{2})(\d{2})(?!\d)")


def _business_number(lines: list[_Line]) -> str | None:
    """The labelled number; without a label, a hyphenated 3-2-5 number anywhere. Null if the check digit fails."""
    labelled = [match.group() for value in _values_for(lines, "number") for match in _NUMBER_IN_TEXT.finditer(value.text)]
    if labelled:
        return normalize_business_number(labelled[0])
    for line in lines:
        match = _HYPHENATED_NUMBER.search(line.text)
        if match:
            return normalize_business_number(match.group())
    return None


def parse_date(text: str, today: date) -> date | None:
    """2020 년 03 월 02 일, 2020.03.02, 2020-3-2 or 20200302; null if unreadable or after `today`."""
    match = _DATE_WITH_SEPARATORS.search(text) or _DATE_DIGITS.search(text)
    if match is None:
        return None
    try:
        parsed = date(*(int(part) for part in match.groups()))
    except ValueError:
        return None
    if parsed.year < MIN_OPENING_YEAR or parsed > today:
        return None
    return parsed


def _text_value(value: _Value, max_length: int) -> str | None:
    text = _clean(value.text)
    return text if 0 < len(text) <= max_length else None


def _representative(value: _Value) -> str | None:
    text = _text_value(value, MAX_REPRESENTATIVE_NAME)
    if text is None:
        return None
    parts = text.split(" ")
    # A letter-spaced Korean name ("김 사 장") is one name.
    if 2 <= len(parts) <= 5 and all(re.fullmatch(r"[가-힣]", part) for part in parts):
        return "".join(parts)
    return text


def _address(lines: list[_Line], value: _Value) -> str | None:
    """The address and up to two wrapped lines below it that start under the value, not under the labels."""
    parts = [_clean(value.text)]
    previous = lines[value.line_index]
    for index in range(value.line_index + 1, min(len(lines), value.line_index + 1 + MAX_ADDRESS_CONTINUATION_LINES)):
        line = lines[index]
        height = _height(previous)
        if (
            line.starts_with_label
            or _same_row(previous, line)
            or line.box[1] - previous.box[3] > height
            or line.box[0] < value.x0 - height
        ):
            break
        parts.append(_clean(line.text_before_label()))
        previous = line
    text = " ".join(part for part in parts if part)
    return text if 0 < len(text) <= MAX_ADDRESS else None


def parse_certificate(ocr_lines: list[OcrLine], *, today: date) -> CertificateFields:
    """The fields read from OCR lines of a certificate; each is None when not found or not valid."""
    lines = _prepare(ocr_lines)
    return CertificateFields(
        business_registration_number=_business_number(lines),
        representative_name=_first(_values_for(lines, "representative"), _representative),
        opening_date=_first(_values_for(lines, "opening_date"), lambda value: parse_date(value.text, today)),
        business_name=_first(_values_for(lines, "business_name"), lambda value: _text_value(value, MAX_BUSINESS_NAME)),
        address=_first(_values_for(lines, "address"), lambda value: _address(lines, value)),
    )
