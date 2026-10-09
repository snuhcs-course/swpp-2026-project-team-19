# AI-generated with Claude Code/Claude Opus 5.5 (Jinwoo Park, 2026-10-06, PR #10). Reviewed by Jinwoo Park.
"""Image preprocessing, the same as ai/extract/extract.py prepare_image but in memory.

EXIF orientation present (!= 1): rotate, drop EXIF, re-encode as JPEG q95.
Otherwise the original bytes are sent unchanged. Pixel size is never changed.
"""

import io

from PIL import Image, ImageOps, UnidentifiedImageError

from app.extraction.errors import UnsupportedImageError

JPEG_QUALITY = 95
# P14 sent only these two types. PIL format names for each MIME type
# (phone cameras often write multi-picture JPEGs, which PIL reports as MPO):
SUPPORTED_MIME_TYPES = {"image/jpeg": ("JPEG", "MPO"), "image/png": ("PNG",)}


def prepare_image(data: bytes, mime_type: str) -> tuple[bytes, str]:
    """Return (bytes, MIME type) to send to the model."""
    mime_type = mime_type.strip().lower()
    if mime_type == "image/jpg":
        mime_type = "image/jpeg"
    expected_formats = SUPPORTED_MIME_TYPES.get(mime_type)
    if expected_formats is None:
        raise UnsupportedImageError(
            f"Unsupported MIME type {mime_type!r}; expected one of {', '.join(SUPPORTED_MIME_TYPES)}"
        )
    if not data:
        raise UnsupportedImageError("Image is empty")

    try:
        with Image.open(io.BytesIO(data)) as im:
            if im.format not in expected_formats:
                raise UnsupportedImageError(f"Image data is {im.format}, but MIME type is {mime_type}")
            orientation = im.getexif().get(0x0112)
            if orientation in (None, 1):
                return data, mime_type
            out = io.BytesIO()
            ImageOps.exif_transpose(im).convert("RGB").save(out, format="JPEG", quality=JPEG_QUALITY)
            return out.getvalue(), "image/jpeg"
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise UnsupportedImageError(f"Cannot read image: {exc}") from exc
