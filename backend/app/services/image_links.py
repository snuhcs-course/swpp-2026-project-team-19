"""URLs for viewing stored photos in API responses."""

from dataclasses import dataclass
from datetime import datetime

from app.adapters.storage import ImageStorage


@dataclass(frozen=True)
class ImageLinks:
    storage: ImageStorage
    base_url: str

    def url(self, key: str) -> tuple[str, datetime | None]:
        """The viewing URL of a stored photo and when it expires (None when it does not)."""
        url, expires_at = self.storage.url(key)
        # Object storage returns full signed URLs; local storage returns a path on this server.
        if not url.startswith(("http://", "https://")):
            url = self.base_url.rstrip("/") + url
        return url, expires_at
