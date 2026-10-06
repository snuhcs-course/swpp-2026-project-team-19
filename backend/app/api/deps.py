"""Shared dependencies for adapters, chosen by environment variables. Tests override them."""

import os
from datetime import timedelta
from functools import lru_cache
from pathlib import Path

import boto3
from botocore.config import Config

from app.adapters.extraction import MenuExtractor, MockMenuExtractor
from app.adapters.storage import ImageStorage, LocalImageStorage, S3ImageStorage

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

        try:
            return GeminiMenuExtractor()
        except ExtractionConfigError as error:
            raise RuntimeError(f"MENU_EXTRACTOR=gemini is not configured: {error}") from error
    raise RuntimeError(f"Unsupported MENU_EXTRACTOR: {kind!r} (supported: mock, gemini)")
