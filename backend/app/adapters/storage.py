# AI-generated with ChatGPT (Haeul Yang, 2026-10-06, PR #11, #16). Reviewed by Haeul Yang.
"""Storage for uploaded menu photos.

The database keeps only the storage key. `LocalImageStorage` writes to disk for local
development and tests; `S3ImageStorage` keeps the photos in a private S3 bucket for
deployment. Callers do not depend on which one is used.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Protocol
from urllib.parse import quote

from botocore.exceptions import ClientError

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


class S3ImageStorage:
    """Objects in a private S3 bucket, viewed through presigned GET URLs.

    `client` is a boto3 S3 client. On EC2 it takes its credentials from the instance's IAM
    role, so no keys are configured. A URL stops working after `url_ttl`; clients fetch
    the review data again for a fresh one.
    """

    def __init__(self, client: Any, bucket: str, url_ttl: timedelta = timedelta(minutes=15)) -> None:
        self.client = client
        self.bucket = bucket
        self.url_ttl = url_ttl

    def save(self, key: str, data: bytes, content_type: str) -> None:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)

    def read(self, key: str) -> bytes:
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") in {"NoSuchKey", "404"}:
                raise FileNotFoundError(key) from error
            raise
        return response["Body"].read()

    def delete(self, key: str) -> None:
        # S3 answers a delete of a missing key with success.
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def url(self, key: str) -> tuple[str, datetime | None]:
        expires_at = datetime.now(timezone.utc) + self.url_ttl
        url = self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=int(self.url_ttl.total_seconds()),
        )
        return url, expires_at
