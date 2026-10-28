"""Synthetic CLOVA General OCR responses for business registration certificates.

Every value here is made up; no real certificate is used. The layout follows the National Tax
Service form: a title, letter-spaced labels with values after a colon, and noise lines such as
the issue date and the tax office at the bottom. The business number 123-45-67891 has a valid
check digit; 123-45-67890 does not.
"""

import io

from PIL import Image

VALID_NUMBER = "123-45-67891"
INVALID_NUMBER = "123-45-67890"
CHAR_WIDTH = 22
HEIGHT = 30
GAP = 12


def field(text: str, x0: float, y0: float, x1: float, y1: float, line_break: bool) -> dict:
    return {
        "valueType": "ALL",
        "inferText": text,
        "inferConfidence": 0.99,
        "type": "NORMAL",
        "lineBreak": line_break,
        "boundingPoly": {"vertices": [{"x": x0, "y": y0}, {"x": x1, "y": y0}, {"x": x1, "y": y1}, {"x": x0, "y": y1}]},
    }


def row(y: float, *words: str | tuple[float, str]) -> list[dict]:
    """One OCR line at height `y`: words left to right; `(x, word)` starts a word at x."""
    fields, x = [], 50.0
    for word in words:
        if isinstance(word, tuple):
            x, word = word
        width = CHAR_WIDTH * len(word)
        fields.append(field(word, x, y, x + width, y + HEIGHT, False))
        x += width + GAP
    fields[-1]["lineBreak"] = True
    return fields


def response(*rows: list[dict]) -> dict:
    return {
        "version": "V2",
        "requestId": "test",
        "timestamp": 0,
        "images": [
            {
                "uid": "test",
                "name": "menu",
                "inferResult": "SUCCESS",
                "message": "SUCCESS",
                "convertedImageInfo": {"width": 1240, "height": 1754},
                "fields": [f for r in rows for f in r],
            }
        ],
    }


TITLE = row(40, "사", "업", "자", "등", "록", "증")
KIND = row(90, "(일반과세자)")
FOOTER = [
    row(700, "2020", "년", "03", "월", "05", "일"),  # issue date: not the opening date
    row(760, "관악세무서장"),
]


def individual_certificate(number: str = VALID_NUMBER) -> dict:
    """An individual business: 성명 shares its row with 생년월일, the address wraps to a second line."""
    return response(
        TITLE,
        KIND,
        row(150, "등", "록", "번", "호", ":", number),
        row(200, "상", (120, "호"), ":", "신림", "몰트", "하우스"),
        row(250, "성", (120, "명"), ":", "김사장", (600, "생"), "년", "월", "일", ":", "1980", "년", "01", "월", "01", "일"),
        row(300, "개", "업", "연", "월", "일", ":", "2020", "년", "03", "월", "02", "일"),
        row(350, "사업장", "소재지", ":", "서울특별시", "관악구", "신림로", "2"),
        row(390, (262, "3층")),
        row(440, "사", "업", "의", "종", "류", ":", "업태", "음식점업", "종목", "주점"),
        row(490, "발", "급", "사", "유", ":", "신규"),
        *FOOTER,
    )


def corporate_certificate() -> dict:
    """A corporation: 법인명(단체명), 대표자, 법인등록번호 (13 digits) and 본점소재지 lines."""
    return response(
        row(40, "사업자등록증"),
        row(90, "(법인사업자)"),
        row(150, "등록번호", ":", "123", "-", "45", "-", "67891"),
        row(200, "법인명(단체명)", ":", "주식회사", "몰트앤코"),
        row(250, "대", "표", "자", ":", "이대표"),
        row(300, "개업연월일", ":", "2019.11.04", (600, "법인등록번호"), ":", "110111-1234567"),
        row(350, "사업장", "소재지", ":", "부산광역시", "해운대구", "우동", "1"),
        row(400, "본점소재지", ":", "서울특별시", "중구", "세종대로", "1"),
        *FOOTER,
    )


def jpeg(size: tuple[int, int] = (120, 160)) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size, "white").save(out, format="JPEG")
    return out.getvalue()


def png(size: tuple[int, int] = (120, 160)) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size, "white").save(out, format="PNG")
    return out.getvalue()
