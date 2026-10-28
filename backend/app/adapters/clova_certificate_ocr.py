"""Business certificate OCR with CLOVA General OCR, behind `CertificateOcr`.

Reuses the General OCR client of the hybrid menu extractor (app/extraction/clova.py) and returns
the text lines as CLOVA breaks them, with word boxes, without splitting wide gaps: certificate
labels are often letter-spaced ("상       호"), and splitting would tear them apart. The photo
and the text are never stored or logged here.
"""

import io
import threading
from dataclasses import replace

from PIL import Image

from app.adapters.certificate_ocr import (
    CertificateImageError,
    CertificateImageTooLarge,
    CertificateOcrError,
    OcrLine,
    OcrWord,
    PreparedImage,
)
from app.extraction.clova import ClovaOCRError, ClovaSettings, build_lines, call_ocr, ocr_image

# The app waits 60 s for a response (OkHttp read timeout). The whole OCR call, retries included,
# stops at 35 s of wall-clock time; a socket operation already under way can add at most its
# 15 s timeout, so the worst case is 50 s.
CERTIFICATE_OCR_DEADLINE_S = 35.0
CERTIFICATE_OCR_TIMEOUT_S = 15.0
CERTIFICATE_OCR_MAX_ATTEMPTS = 2
# Decoding is bounded twice: by size (40 MP, e.g. 8000 x 5000; Pillow itself only warns up to
# about 179 MP) and by count (two photos decoded at a time, at most a few hundred MB together).
MAX_IMAGE_PIXELS = 40_000_000
DECODE_SLOTS = threading.BoundedSemaphore(2)


class ClovaCertificateOcr:
    """One CLOVA General OCR call per photo, with a wall-clock deadline (menu extraction has none)."""

    def __init__(self, settings: ClovaSettings) -> None:
        self.settings = replace(
            settings,
            timeout_s=CERTIFICATE_OCR_TIMEOUT_S,
            max_attempts=CERTIFICATE_OCR_MAX_ATTEMPTS,
            deadline_s=CERTIFICATE_OCR_DEADLINE_S,
        )

    def prepare(self, image: bytes, content_type: str) -> PreparedImage:
        """Check the size in the header, then decode every pixel, so a bomb is never decoded and a
        truncated file is not sent (and not counted, 3.11.14). Also downscales for CLOVA if needed."""
        with DECODE_SLOTS:
            try:
                with Image.open(io.BytesIO(image), formats=["JPEG", "PNG"]) as im:
                    width, height = im.size
                    if width * height > MAX_IMAGE_PIXELS:
                        raise CertificateImageTooLarge(f"{width}x{height}")
                    im.load()
                data, fmt, _ = ocr_image(image, content_type)
            except Image.DecompressionBombError as error:
                raise CertificateImageTooLarge(type(error).__name__) from error
            # SyntaxError is how Pillow reports some broken PNG files.
            except (OSError, ValueError, SyntaxError, EOFError) as error:
                raise CertificateImageError(type(error).__name__) from error
        return PreparedImage(data, "image/jpeg" if fmt == "jpg" else "image/png")

    def read_lines(self, image: PreparedImage) -> list[OcrLine]:
        try:
            result = call_ocr(self.settings, image.data, image.content_type)
        except ClovaOCRError as error:
            raise CertificateOcrError(str(error)) from error
        return [
            OcrLine(tuple(OcrWord(w.text, (w.x0, w.y0, w.x1, w.y1)) for w in line.words))
            for line in build_lines(result["response"], gap_factor=float("inf"))
            if line.words
        ]
