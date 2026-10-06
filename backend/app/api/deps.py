"""Shared dependencies for adapters, chosen by environment variables. Tests override them."""

import os
from functools import lru_cache
from pathlib import Path

from app.adapters.extraction import MenuExtractor, MockMenuExtractor
from app.adapters.storage import ImageStorage, LocalImageStorage

BACKEND_DIR = Path(__file__).resolve().parents[2]
DEFAULT_IMAGE_STORAGE_DIR = BACKEND_DIR / "var" / "images"


@lru_cache(maxsize=1)
def get_image_storage() -> ImageStorage:
    kind = os.getenv("IMAGE_STORAGE", "local")
    if kind == "local":
        return LocalImageStorage(Path(os.getenv("IMAGE_STORAGE_DIR", str(DEFAULT_IMAGE_STORAGE_DIR))))
    raise RuntimeError(f"Unsupported IMAGE_STORAGE: {kind!r} (supported: local)")


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
