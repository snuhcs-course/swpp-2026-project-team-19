"""Checking and re-encoding a bar photo (API spec 3.16.2), without the database or the API."""

import hashlib
import io
import struct
import zlib

import pytest
from PIL import Image, ImageCms

from app.core.errors import ApiError
from app.services.bar_photo_image import MAX_PHOTO_BYTES, process_photo, single_upload
from app.services.menu_import_upload import ImageUpload

ORIENTATION = 0x0112
GPS_INFO = 0x8825


def encode(image: Image.Image, format: str, **params) -> bytes:
    out = io.BytesIO()
    image.save(out, format=format, **params)
    return out.getvalue()


def jpeg(size=(64, 48), color="red", **params) -> bytes:
    return encode(Image.new("RGB", size, color), "JPEG", **params)


def _chunk(kind: bytes, body: bytes) -> bytes:
    return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))


def png_without_pixels(width: int, height: int) -> bytes:
    """A PNG claiming the size whose pixel data is empty: it opens, but does not decode."""
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", b"") + _chunk(b"IEND", b"")


def upload(data: bytes, content_type: str | None = "image/jpeg") -> ImageUpload:
    return ImageUpload("photo", content_type, io.BytesIO(data))


def decoded(data: bytes) -> Image.Image:
    image = Image.open(io.BytesIO(data))
    image.load()
    return image


def error_of(data: bytes, content_type: str | None = "image/jpeg") -> ApiError:
    with pytest.raises(ApiError) as caught:
        process_photo(upload(data, content_type))
    return caught.value


# ---- re-encoding ----


def test_a_jpeg_is_re_encoded_at_its_size_with_the_hash_of_the_upload():
    data = jpeg((300, 200))

    photo = process_photo(upload(data))

    assert photo.content_sha256 == hashlib.sha256(data).hexdigest()
    assert photo.image != data
    image = decoded(photo.image)
    assert (image.format, image.mode, image.size) == ("JPEG", "RGB", (300, 200))


def test_metadata_is_removed():
    exif = Image.Exif()
    exif[0x010F] = "Phone maker"
    exif[GPS_INFO] = {1: "N", 2: (37.0, 28.0, 41.0)}
    icc = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    data = jpeg(exif=exif.tobytes(), icc_profile=icc, xmp=b"<x:xmpmeta>taken at home</x:xmpmeta>")
    assert {"exif", "icc_profile", "xmp"} <= decoded(data).info.keys()

    photo = process_photo(upload(data))

    for stored in (photo.image, photo.thumbnail):
        image = decoded(stored)
        assert not {"exif", "icc_profile", "xmp"} & image.info.keys()
        assert dict(image.getexif()) == {}
        assert b"taken at home" not in stored and b"Phone maker" not in stored


def test_the_exif_orientation_is_applied():
    exif = Image.Exif()
    exif[ORIENTATION] = 6  # rotate 90 degrees clockwise to view
    data = jpeg((80, 40), exif=exif.tobytes())

    photo = process_photo(upload(data))

    assert decoded(photo.image).size == (40, 80)
    assert decoded(photo.thumbnail).size == (40, 80)


@pytest.mark.parametrize(
    "image",
    [
        pytest.param(Image.new("RGBA", (20, 10), (0, 0, 0, 0)), id="RGBA"),
        pytest.param(Image.new("LA", (20, 10), (0, 0)), id="LA"),
        pytest.param(Image.new("RGBA", (20, 10), (0, 0, 0, 0)).convert("P"), id="palette with transparency"),
    ],
)
def test_transparent_areas_become_white(image):
    photo = process_photo(upload(encode(image, "PNG"), "image/png"))

    result = decoded(photo.image)
    assert result.mode == "RGB"
    assert all(channel >= 250 for channel in result.getpixel((5, 5)))


@pytest.mark.parametrize(
    ("image", "format"),
    [
        pytest.param(Image.new("I;16", (20, 10), 30000), "PNG", id="16-bit grayscale PNG"),
        pytest.param(Image.new("L", (20, 10), 128), "PNG", id="grayscale PNG"),
        pytest.param(Image.new("CMYK", (20, 10), (0, 255, 255, 0)), "JPEG", id="CMYK JPEG"),
    ],
)
def test_other_modes_become_rgb(image, format):
    content_type = "image/png" if format == "PNG" else "image/jpeg"

    photo = process_photo(upload(encode(image, format), content_type))

    assert decoded(photo.image).mode == "RGB"


@pytest.mark.parametrize(
    ("size", "thumbnail"),
    [
        pytest.param((1000, 500), (480, 240), id="landscape"),
        pytest.param((300, 2048), (70, 480), id="portrait at the limit"),
        pytest.param((100, 50), (100, 50), id="smaller than the thumbnail"),
    ],
)
def test_the_thumbnail_is_480_on_the_long_edge_without_enlarging(size, thumbnail):
    photo = process_photo(upload(jpeg(size)))

    image = decoded(photo.thumbnail)
    assert (image.format, image.size) == ("JPEG", thumbnail)


# ---- checks ----


def test_a_photo_at_the_size_limit_is_accepted():
    # Bytes after the end of the JPEG are ignored by decoders.
    data = jpeg()
    data += b"\0" * (MAX_PHOTO_BYTES - len(data))

    assert process_photo(upload(data)).content_sha256 == hashlib.sha256(data).hexdigest()


def test_a_photo_over_the_size_limit_is_too_large():
    data = jpeg()
    data += b"\0" * (MAX_PHOTO_BYTES + 1 - len(data))

    error = error_of(data)

    assert (error.status_code, error.code, error.details) == (413, "UPLOAD_TOO_LARGE", {"maxImageBytes": 2097152})


def test_the_size_is_checked_before_the_type():
    assert error_of(b"GIF89a" + b"\0" * MAX_PHOTO_BYTES).code == "UPLOAD_TOO_LARGE"


@pytest.mark.parametrize(
    ("data", "content_type"),
    [
        pytest.param(encode(Image.new("RGB", (8, 8)), "GIF"), "image/gif", id="GIF"),
        pytest.param(b"\x00\x00\x00\x18ftypheic" + b"heic-body", "image/heic", id="HEIC"),
        pytest.param(jpeg(), "image/png", id="declared PNG, JPEG content"),
        pytest.param(b"\xff\xd8\xff\xe0" + b"not a jpeg", "image/jpeg", id="JPEG signature only"),
        pytest.param(jpeg((200, 200), "blue", quality=100)[:-300], "image/jpeg", id="truncated JPEG"),
        pytest.param(png_without_pixels(20, 10), "image/png", id="PNG without pixel data"),
    ],
)
def test_a_file_that_is_not_a_whole_jpeg_or_png_is_unsupported(data, content_type):
    error = error_of(data, content_type)

    assert (error.status_code, error.code) == (415, "UNSUPPORTED_IMAGE_TYPE")


@pytest.mark.parametrize("content_type", [None, "", "application/octet-stream"])
def test_a_generic_declared_type_goes_by_the_content(content_type):
    assert decoded(process_photo(upload(jpeg(), content_type)).image).format == "JPEG"


@pytest.mark.parametrize(
    "data",
    [
        pytest.param(png_without_pixels(2049, 10), id="wide"),
        pytest.param(png_without_pixels(10, 2049), id="tall"),
        # Large enough that Pillow refuses to open it before the size can be read.
        pytest.param(png_without_pixels(30000, 30000), id="decompression bomb"),
    ],
)
def test_a_long_edge_over_2048_is_rejected_before_decoding(data):
    error = error_of(data, "image/png")

    assert (error.status_code, error.code) == (422, "VALIDATION_FAILED")
    assert [(e["path"], e["code"]) for e in error.field_errors] == [("image", "IMAGE_DIMENSIONS_TOO_LARGE")]


def test_a_long_edge_of_2048_is_accepted():
    photo = process_photo(upload(jpeg((2048, 16))))

    assert decoded(photo.image).size == (2048, 16)


def test_only_one_image_is_taken():
    one = upload(jpeg())
    assert single_upload([one]) is one

    with pytest.raises(ApiError) as caught:
        single_upload([one, upload(jpeg())])

    assert [(e["path"], e["code"]) for e in caught.value.field_errors] == [("image", "TOO_LONG")]
