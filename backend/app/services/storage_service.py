"""
Vitar v13 — Storage Service
============================
Unified file storage abstraction that supports two backends:

  STORAGE_BACKEND=s3    → AWS S3 (required for multi-replica / 500-user scale)
  STORAGE_BACKEND=local → Local filesystem (single-node dev/test only)

Why this matters at scale
--------------------------
When running 2+ API replicas (docker-compose.scale.yml), each container has
its own filesystem. A file uploaded to replica-A is invisible to replica-B
and nginx may route the next request to either one. Local storage is also
ephemeral — files vanish on container restart.

S3 (or any shared object store) solves both problems: every replica reads and
writes to the same bucket, and files survive container restarts indefinitely.

Usage
------
    from app.services.storage_service import storage

    url  = await storage.upload(file_bytes, filename, content_type)
    ok   = await storage.delete(url)          # best-effort
    path = storage.url_to_key(url)            # S3 key or local path

Switching backends
------------------
Set STORAGE_BACKEND=s3 in .env (or the environment) and provide:
    AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_S3_BUCKET, AWS_REGION

The local backend stores files under UPLOAD_DIR (/app/uploads) and serves
them via the /uploads static mount registered in main.py.
"""

import io
import os
import uuid
import logging
import mimetypes
from pathlib import Path
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

# ── Allowed upload types ──────────────────────────────────────────────────────
ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
}
MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB


def _safe_filename(original: str, content_type: str) -> str:
    """Return a UUID-based filename with the correct extension."""
    ext_map = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
    }
    ext = ext_map.get(content_type) or Path(original).suffix or ".bin"
    return f"{uuid.uuid4().hex}{ext}"


# ─────────────────────────────────────────────────────────────────────────────
# S3 Backend
# ─────────────────────────────────────────────────────────────────────────────

class S3StorageBackend:
    """
    Uploads files to AWS S3 and returns a public (or presigned) URL.

    Bucket policy should allow public GetObject if you want direct CDN URLs.
    For private buckets, swap _build_url() to generate a presigned URL.
    """

    def __init__(self):
        try:
            import boto3
            from botocore.exceptions import BotoCoreError, ClientError
            self._BotoCoreError = BotoCoreError
            self._ClientError = ClientError
            self._s3 = boto3.client(
                "s3",
                region_name=settings.AWS_REGION,
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            )
            self._bucket = settings.AWS_S3_BUCKET
            logger.info(
                f"[storage] S3 backend initialised (bucket={self._bucket}, "
                f"region={settings.AWS_REGION})"
            )
        except ImportError:
            raise RuntimeError(
                "boto3 is not installed. Add boto3==1.35.0 to requirements.txt "
                "or switch STORAGE_BACKEND=local for development."
            )

    def _build_url(self, key: str) -> str:
        """Return the public S3 URL for a given object key."""
        return (
            f"https://{self._bucket}.s3.{settings.AWS_REGION}.amazonaws.com/{key}"
        )

    async def upload(
        self,
        data: bytes,
        original_filename: str,
        content_type: str,
        folder: str = "uploads",
    ) -> str:
        """Upload bytes to S3 and return the public URL."""
        filename = _safe_filename(original_filename, content_type)
        key = f"{folder}/{filename}"
        try:
            self._s3.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
                # CacheControl is important — browsers / CDNs will cache images
                CacheControl="public, max-age=31536000, immutable",
            )
            url = self._build_url(key)
            logger.info(f"[storage] Uploaded to S3: {key}")
            return url
        except (self._BotoCoreError, self._ClientError) as exc:
            logger.error(f"[storage] S3 upload failed: {exc}")
            raise RuntimeError(f"File upload failed: {exc}") from exc

    async def delete(self, url: str) -> bool:
        """Delete an object from S3 given its public URL. Best-effort."""
        try:
            key = self.url_to_key(url)
            if not key:
                return False
            self._s3.delete_object(Bucket=self._bucket, Key=key)
            logger.info(f"[storage] Deleted from S3: {key}")
            return True
        except Exception as exc:
            logger.warning(f"[storage] S3 delete failed (non-fatal): {exc}")
            return False

    def url_to_key(self, url: str) -> Optional[str]:
        """Extract S3 object key from a public URL."""
        prefix = f"https://{self._bucket}.s3.{settings.AWS_REGION}.amazonaws.com/"
        if url.startswith(prefix):
            return url[len(prefix):]
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Local Backend (dev / single-node only)
# ─────────────────────────────────────────────────────────────────────────────

class LocalStorageBackend:
    """
    Stores files on the local filesystem under UPLOAD_DIR.

    ⚠️  NOT suitable for multi-replica deployments.
        Each replica has its own filesystem; files uploaded to one replica
        are invisible to others. Use S3 in production.
    """

    def __init__(self):
        self._upload_dir = Path(settings.UPLOAD_DIR)
        self._upload_dir.mkdir(parents=True, exist_ok=True)
        logger.warning(
            "[storage] Using LOCAL storage backend. "
            "This is NOT safe for multi-replica / production deployments. "
            "Set STORAGE_BACKEND=s3 in .env for production."
        )

    def _build_url(self, relative_path: str) -> str:
        """Build a URL served by the /uploads static mount in main.py."""
        return f"{settings.FRONTEND_URL.rstrip('/')}/uploads/{relative_path}"

    async def upload(
        self,
        data: bytes,
        original_filename: str,
        content_type: str,
        folder: str = "uploads",
    ) -> str:
        """Write bytes to UPLOAD_DIR and return a URL."""
        folder_path = self._upload_dir / folder
        folder_path.mkdir(parents=True, exist_ok=True)
        filename = _safe_filename(original_filename, content_type)
        dest = folder_path / filename
        dest.write_bytes(data)
        logger.info(f"[storage] Saved locally: {dest}")
        return self._build_url(f"{folder}/{filename}")

    async def delete(self, url: str) -> bool:
        """Delete a locally stored file. Best-effort."""
        try:
            key = self.url_to_key(url)
            if not key:
                return False
            target = self._upload_dir / key
            if target.exists():
                target.unlink()
                logger.info(f"[storage] Deleted local file: {target}")
            return True
        except Exception as exc:
            logger.warning(f"[storage] Local delete failed (non-fatal): {exc}")
            return False

    def url_to_key(self, url: str) -> Optional[str]:
        """Extract relative file path from a local URL."""
        marker = "/uploads/"
        idx = url.find(marker)
        if idx == -1:
            return None
        return url[idx + len(marker):]


# ─────────────────────────────────────────────────────────────────────────────
# Factory — picks backend from STORAGE_BACKEND env var
# ─────────────────────────────────────────────────────────────────────────────

def _make_storage():
    backend = getattr(settings, "STORAGE_BACKEND", "local").lower()
    if backend == "s3":
        return S3StorageBackend()
    if backend == "local":
        return LocalStorageBackend()
    raise ValueError(
        f"Unknown STORAGE_BACKEND={backend!r}. Valid values: 's3', 'local'."
    )


# Module-level singleton — imported by endpoints
storage = _make_storage()
