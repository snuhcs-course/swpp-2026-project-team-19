"""Check an uploaded bar photo and re-encode it with its thumbnail (API spec 3.16.2).

The uploaded file is never stored or served. Every photo is decoded, turned upright from its EXIF
orientation and saved again as a JPEG without metadata (EXIF, XMP, GPS, ICC), so nothing the camera
wrote reaches the public photo URLs. Transparent PNG areas become white.
"""

import hashlib
import io
from dataclasses import dataclass

from PIL import Image, ImageOps

from app.core.errors import ApiError, validation_failed
from app.services.menu_import_upload import ImageUpload, check_image_type

MAX_PHOTO_BYTES = 2 * 1024 * 1024
MAX_LONG_EDGE = 2048
THUMBNAIL_LONG_EDGE = 480
JPEG_QUALITY = 85
_WHITE = (255, 255, 255)


@dataclass(frozen=True)
class ProcessedPhoto:
    content_sha256: str  # of the uploaded bytes, before re-encoding
    image: bytes
    thumbnail: bytes


def single_upload(uploads: list[ImageUpload]) -> ImageUpload:
    """The one `image` of the request; 422 for more, like the certificate OCR (spec 3.11.12)."""
    if len(uploads) != 1:
        raise validation_failed("image", "TOO_LONG", "List should have at most 1 item after validation")
    return uploads[0]


def _unsupported() -> ApiError:
    return ApiError(415, "UNSUPPORTED_IMAGE_TYPE", "JPEG, PNG 사진만 올릴 수 있습니다.")


def _too_many_pixels() -> ApiError:
    return validation_failed(
        "image", "IMAGE_DIMENSIONS_TOO_LARGE", f"사진의 긴 변은 {MAX_LONG_EDGE}px 이하여야 합니다."
    )


def _decode(data: bytes) -> Image.Image:
    """The decoded photo; 422 for a long edge over the limit, read from the header before decoding,
    and 415 for a file that does not decode to the end."""
    try:
        image = Image.open(io.BytesIO(data))
    except Image.DecompressionBombError:
        # Raised only far above MAX_LONG_EDGE (about 13,000 px square), before the size can be read.
        raise _too_many_pixels() from None
    except (OSError, SyntaxError, ValueError):
        raise _unsupported() from None
    if max(image.size) > MAX_LONG_EDGE:
        raise _too_many_pixels()
    try:
        image.load()
    except (OSError, SyntaxError, ValueError, EOFError):
        raise _unsupported() from None
    return image


def _upright_rgb(image: Image.Image) -> Image.Image:
    image = ImageOps.exif_transpose(image)
    if image.mode in ("RGBA", "LA", "PA") or "transparency" in image.info:
        rgba = image.convert("RGBA")
        image = Image.new("RGB", rgba.size, _WHITE)
        image.paste(rgba, mask=rgba.getchannel("A"))
    else:
        image = image.convert("RGB")
    # convert() copies the source's info (EXIF, XMP, ICC); drop it so no save can write it back.
    image.info.clear()
    return image


def _jpeg(image: Image.Image) -> bytes:
    out = io.BytesIO()
    image.save(out, format="JPEG", quality=JPEG_QUALITY)
    return out.getvalue()


def process_photo(upload: ImageUpload) -> ProcessedPhoto:
    """Check the photo in the spec's order, size (413) and type (415), then dimensions (422) and
    decoding (415), and return it re-encoded with its thumbnail."""
    # Read one byte past the limit to tell "exactly at the limit" from "over it".
    data = upload.stream.read(MAX_PHOTO_BYTES + 1)
    if len(data) > MAX_PHOTO_BYTES:
        raise ApiError(
            413, "UPLOAD_TOO_LARGE", "사진 크기가 너무 큽니다.", details={"maxImageBytes": MAX_PHOTO_BYTES}
        )
    if check_image_type(data, upload.content_type) is None:
        raise _unsupported()
    with _decode(data) as decoded:
        image = _upright_rgb(decoded)
    thumbnail = image.copy()
    # Shrinks only: a photo smaller than the thumbnail keeps its size.
    thumbnail.thumbnail((THUMBNAIL_LONG_EDGE, THUMBNAIL_LONG_EDGE), Image.Resampling.LANCZOS)
    return ProcessedPhoto(hashlib.sha256(data).hexdigest(), _jpeg(image), _jpeg(thumbnail))
