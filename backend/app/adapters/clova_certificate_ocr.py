"""Business certificate OCR with CLOVA General OCR, behind `CertificateOcr`.

Reuses the General OCR client of the hybrid menu extractor (app/extraction/clova.py) and returns
the text lines as CLOVA breaks them, with word boxes, without splitting wide gaps: certificate
labels are often letter-spaced ("상       호"), and splitting would tear them apart. The photo
and the text are never stored or logged here.
"""

from dataclasses import replace

from PIL import Image

from app.adapters.certificate_ocr import CertificateImageError, CertificateOcrError, OcrLine, OcrWord
from app.extraction.clova import ClovaOCRError, ClovaSettings, build_lines, call_ocr, ocr_image

# The app waits 60 s for a response (OkHttp read timeout): two attempts of at most 20 s plus
# the 5 s pause between them stay under it.
CERTIFICATE_OCR_TIMEOUT_S = 20.0
CERTIFICATE_OCR_MAX_ATTEMPTS = 2


class ClovaCertificateOcr:
    """One CLOVA General OCR call per photo, with a shorter timeout than menu extraction."""

    def __init__(self, settings: ClovaSettings) -> None:
        self.settings = replace(
            settings, timeout_s=CERTIFICATE_OCR_TIMEOUT_S, max_attempts=CERTIFICATE_OCR_MAX_ATTEMPTS
        )

    def read_lines(self, image: bytes, content_type: str) -> list[OcrLine]:
        try:
            # Decode before the call so an undecodable file is not sent (and not counted, 3.11.14).
            data, fmt, _ = ocr_image(image, content_type)
        except (OSError, ValueError, Image.DecompressionBombError) as error:
            raise CertificateImageError(type(error).__name__) from error
        try:
            result = call_ocr(self.settings, data, "image/jpeg" if fmt == "jpg" else "image/png")
        except ClovaOCRError as error:
            raise CertificateOcrError(str(error)) from error
        return [
            OcrLine(tuple(OcrWord(w.text, (w.x0, w.y0, w.x1, w.y1)) for w in line.words))
            for line in build_lines(result["response"], gap_factor=float("inf"))
            if line.words
        ]
