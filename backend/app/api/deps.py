"""Shared dependencies for adapters, chosen by environment variables. Tests override them."""

import os
from collections.abc import Callable
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path

import boto3
from botocore.config import Config

from app.adapters.certificate_ocr import CertificateOcr
from app.adapters.extraction import MenuExtractor, MockMenuExtractor
from app.adapters.storage import ImageStorage, LocalImageStorage, S3ImageStorage
from app.services.request_limits import DailyRequestLimiter, InMemoryDailyLimiter, utc_now

BACKEND_DIR = Path(__file__).resolve().parents[2]
DEFAULT_IMAGE_STORAGE_DIR = BACKEND_DIR / "var" / "images"


def s3_client(region: str):
    """A boto3 S3 client for presigned URLs that open right away.

    Credentials come from the default chain: the EC2 instance role, or AWS_* variables
    locally. The regional virtual-hosted endpoint avoids the redirect a new bucket gets
    through the global endpoint, and SigV4 is the only signature newer regions accept.
    """
    return boto3.client(
        "s3",
        region_name=region,
        endpoint_url=f"https://s3.{region}.amazonaws.com",
        config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}),
    )


@lru_cache(maxsize=1)
def get_image_storage() -> ImageStorage:
    kind = os.getenv("IMAGE_STORAGE", "local")
    if kind == "local":
        return LocalImageStorage(Path(os.getenv("IMAGE_STORAGE_DIR", str(DEFAULT_IMAGE_STORAGE_DIR))))
    if kind == "s3":
        bucket = os.getenv("S3_BUCKET")
        if not bucket:
            raise RuntimeError("IMAGE_STORAGE=s3 needs S3_BUCKET")
        client = s3_client(os.getenv("AWS_REGION", "ap-northeast-2"))
        ttl = timedelta(seconds=int(os.getenv("S3_URL_TTL_SECONDS", "900")))
        return S3ImageStorage(client, bucket, url_ttl=ttl)
    raise RuntimeError(f"Unsupported IMAGE_STORAGE: {kind!r} (supported: local, s3)")


@lru_cache(maxsize=1)
def get_menu_extractor() -> MenuExtractor:
    kind = os.getenv("MENU_EXTRACTOR", "mock")
    if kind == "mock":
        return MockMenuExtractor()
    if kind == "gemini":
        # Imported here so the mock does not load the Gemini SDK.
        from app.adapters.gemini_extraction import GeminiMenuExtractor
        from app.extraction import ExtractionConfigError

        # P35: EXTRACTION_MODE=hybrid adds CLOVA OCR lines to the Gemini call; gemini (default) is unchanged.
        mode = os.getenv("EXTRACTION_MODE", "gemini")
        if mode not in ("gemini", "hybrid"):
            raise RuntimeError(f"Unsupported EXTRACTION_MODE: {mode!r} (supported: gemini, hybrid)")
        setting = "MENU_EXTRACTOR=gemini" + (" with EXTRACTION_MODE=hybrid" if mode == "hybrid" else "")
        try:
            if mode == "hybrid":
                from app.adapters.hybrid_extraction import HybridMenuExtractor

                return HybridMenuExtractor()
            return GeminiMenuExtractor()
        except ExtractionConfigError as error:
            raise RuntimeError(f"{setting} is not configured: {error}") from error
    raise RuntimeError(f"Unsupported MENU_EXTRACTOR: {kind!r} (supported: mock, gemini)")


def get_certificate_ocr() -> CertificateOcr | None:
    """CLOVA OCR for business certificates (spec 3.11.12), or None when CLOVA_OCR_* is not set.

    Read on each request: the endpoint answers `503 OCR_UNAVAILABLE` without the settings
    instead of stopping the server, since the OCR is optional.
    """
    # Imported here, like the Gemini extractor, so start-up does not load the extraction SDKs.
    from app.adapters.clova_certificate_ocr import ClovaCertificateOcr
    from app.extraction.clova import load_clova_settings
    from app.extraction.errors import ExtractionConfigError

    try:
        return ClovaCertificateOcr(load_clova_settings())
    except ExtractionConfigError:
        return None


@lru_cache(maxsize=1)
def get_request_limiter() -> DailyRequestLimiter:
    """The one per-process limiter of spec 3.11.14 (the API runs as a single process)."""
    return InMemoryDailyLimiter()


def get_clock() -> Callable[[], datetime]:
    """The current time (aware, UTC). Tests override it to move across midnight KST."""
    return utc_now
