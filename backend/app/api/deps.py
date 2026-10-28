"""Shared dependencies for adapters, chosen by environment variables. Tests override them."""

import logging
import os
from datetime import timedelta
from functools import lru_cache
from pathlib import Path

import boto3
from botocore.config import Config

from app.adapters.extraction import MenuExtractor, MockMenuExtractor
from app.adapters.matching_llm import load_matching_llm_settings
from app.adapters.storage import ImageStorage, LocalImageStorage, S3ImageStorage
from app.matching.llm_layer import LLMLayerConfig

logger = logging.getLogger(__name__)

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


@lru_cache(maxsize=1)
def get_matching_llm_layer() -> LLMLayerConfig | None:
    """The LLM matching layer for menu import, or None when it is off (the default).

    MATCHING_LLM_ENABLED=true turns it on with GEMINI_API_KEY; MATCHING_LLM_MAX_CALLS caps the
    model requests per import (default 30) and MATCHING_LLM_M3B_ENABLED=true adds M3b. Without
    a key the layer stays off with a warning instead of stopping the server: imports then keep
    the rule results, as they would after a failed call.
    """
    settings = load_matching_llm_settings()  # RuntimeError for an invalid cap stops the server
    if not settings.enabled:
        return None
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.warning("MATCHING_LLM_ENABLED=true but GEMINI_API_KEY is not set; the LLM matching layer is off")
        return None
    # Imported here so a server with the layer off does not load the Gemini SDK for it.
    from app.adapters.gemini_matching_llm import GeminiMatchingLLM

    return LLMLayerConfig(llm=GeminiMatchingLLM(api_key), max_calls=settings.max_calls, use_m3b=settings.m3b_enabled)
