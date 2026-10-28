"""OCR for business registration certificate photos (spec 3.11.12): the interface and its types.

The CLOVA implementation is in app/adapters/clova_certificate_ocr.py, imported on the first OCR
request rather than at start-up (as the Gemini extractor is).
"""

from dataclasses import dataclass
from typing import Protocol


class CertificateOcrError(Exception):
    """The OCR service could not be reached or failed after retries. Messages carry no OCR text."""


class CertificateImageError(Exception):
    """The image could not be decoded, so nothing was sent to the OCR service."""


class CertificateImageTooLarge(Exception):
    """The image has more pixels than may be decoded, so it was not decoded or sent."""


@dataclass(frozen=True)
class PreparedImage:
    """A fully decoded and checked photo, as it will be sent to the OCR service."""

    data: bytes
    content_type: str


@dataclass(frozen=True)
class OcrWord:
    text: str
    box: tuple[float, float, float, float]  # x0, y0, x1, y1 in image pixels


@dataclass(frozen=True)
class OcrLine:
    words: tuple[OcrWord, ...]

    @property
    def text(self) -> str:
        return " ".join(word.text for word in self.words)

    @property
    def box(self) -> tuple[float, float, float, float]:
        return (
            min(w.box[0] for w in self.words),
            min(w.box[1] for w in self.words),
            max(w.box[2] for w in self.words),
            max(w.box[3] for w in self.words),
        )


class CertificateOcr(Protocol):
    def prepare(self, image: bytes, content_type: str) -> PreparedImage:
        """Decode the whole image without calling OCR. Raises CertificateImageTooLarge or CertificateImageError."""
        ...

    def read_lines(self, image: PreparedImage) -> list[OcrLine]:
        """Text lines in reading order, from one OCR call. Raises CertificateOcrError."""
        ...
