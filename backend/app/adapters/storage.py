"""Storage for uploaded menu photos.

The database keeps only the storage key. `LocalImageStorage` writes to disk for local
development and tests; deployment can add an object-storage implementation (P21)
without changing the callers.
"""

from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Protocol
from urllib.parse import quote

MEDIA_PATH_PREFIX = "/media"


class ImageStorage(Protocol):
    def save(self, key: str, data: bytes, content_type: str) -> None: ...

    def read(self, key: str) -> bytes:
        """Raises FileNotFoundError when nothing is stored under the key."""
        ...

    def delete(self, key: str) -> None:
        """Does nothing when the key does not exist, so compensation never fails halfway."""
        ...

    def url(self, key: str) -> tuple[str, datetime | None]:
        """URL for viewing the image and when it expires (None when it does not)."""
        ...


class LocalImageStorage:
    """Files under `root`, served by the development-only `/media` route."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def path_for(self, key: str) -> Path:
        """Raises ValueError for keys that are absolute or would leave `root`."""
        parts = PurePosixPath(key).parts
        if not key or key.startswith("/") or "\\" in key or ".." in parts:
            raise ValueError(f"Invalid storage key: {key!r}")
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError(f"Invalid storage key: {key!r}")
        return path

    def save(self, key: str, data: bytes, content_type: str) -> None:
        path = self.path_for(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def read(self, key: str) -> bytes:
        return self.path_for(key).read_bytes()

    def delete(self, key: str) -> None:
        self.path_for(key).unlink(missing_ok=True)

    def url(self, key: str) -> tuple[str, datetime | None]:
        # A path, not an absolute URL: the API joins it with the request's base URL,
        # which differs between a phone, an emulator (10.0.2.2) and localhost.
        return f"{MEDIA_PATH_PREFIX}/{quote(key)}", None
