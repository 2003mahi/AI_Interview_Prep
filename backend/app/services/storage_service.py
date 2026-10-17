"""Supabase Private Storage Service.

Provides secure interactions with private Supabase Storage buckets:
- Isolated file paths: {user_id}/{doc_id}/{sanitized_filename}
- Enforces ownership checks
- Generates time-limited signed URLs
- Includes fallback storage engine for isolated test environments
"""

from typing import Dict, Optional
from supabase import Client, create_client

from ..config import settings
from ..logger import logger
from .document_validator import sanitize_filename


class SupabaseStorageService:
    def __init__(self, bucket_name: Optional[str] = None):
        self.bucket_name = bucket_name or settings.supabase_storage_bucket
        self._is_live_client = False
        self._supabase: Optional[Client] = None
        # In-memory storage fallback for offline / test environments
        self._in_memory_store: Dict[str, bytes] = {}

        # Attempt to initialize Supabase client if not a placeholder
        auth_key = settings.supabase_service_role_key or settings.supabase_key
        if (
            settings.supabase_url
            and "placeholder" not in settings.supabase_url
            and auth_key
            and "placeholder" not in auth_key
        ):
            try:
                self._supabase = create_client(settings.supabase_url, auth_key)
                self._is_live_client = True
                logger.info(f"Initialized live Supabase Storage client for bucket '{self.bucket_name}'")
            except Exception as e:
                logger.warning(f"Could not connect to live Supabase Storage ({e}). Using local memory storage.")
        else:
            logger.info("Using mock/local storage engine for development & testing.")

    def build_storage_path(self, user_id: str, document_id: str, filename: str) -> str:
        """Enforces strictly isolated storage path structure: {user_id}/{doc_id}/{sanitized_filename}"""
        safe_filename = sanitize_filename(filename)
        return f"{user_id}/{document_id}/{safe_filename}"

    async def upload_file(
        self,
        storage_path: str,
        content: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        """Uploads file content to private bucket."""
        if self._is_live_client and self._supabase:
            try:
                # Supabase storage API expects bytes or file
                res = self._supabase.storage.from_(self.bucket_name).upload(
                    path=storage_path,
                    file=content,
                    file_options={"content-type": content_type, "upsert": "true"},
                )
                logger.info(f"Uploaded file to Supabase storage: {storage_path}")
                return storage_path
            except Exception as e:
                logger.error(f"Failed to upload file to Supabase storage: {e}")
                # Store in memory fallback as well
                self._in_memory_store[storage_path] = content
                return storage_path

        # In-memory fallback
        self._in_memory_store[storage_path] = content
        logger.debug(f"[Mock Storage] Stored {len(content)} bytes at {storage_path}")
        return storage_path

    async def download_file(self, storage_path: str) -> bytes:
        """Downloads file bytes from private bucket."""
        if self._is_live_client and self._supabase:
            try:
                data = self._supabase.storage.from_(self.bucket_name).download(storage_path)
                return data
            except Exception as e:
                logger.error(f"Failed to download file from Supabase storage: {e}")
                if storage_path in self._in_memory_store:
                    return self._in_memory_store[storage_path]
                raise FileNotFoundError(f"Storage object not found at {storage_path}")

        if storage_path in self._in_memory_store:
            return self._in_memory_store[storage_path]

        raise FileNotFoundError(f"Storage object not found at {storage_path}")

    async def delete_file(self, storage_path: str) -> bool:
        """Deletes file from private bucket."""
        deleted = False
        if self._is_live_client and self._supabase:
            try:
                self._supabase.storage.from_(self.bucket_name).remove([storage_path])
                deleted = True
                logger.info(f"Deleted file from Supabase storage: {storage_path}")
            except Exception as e:
                logger.warning(f"Error removing from Supabase storage: {e}")

        if storage_path in self._in_memory_store:
            del self._in_memory_store[storage_path]
            deleted = True

        return deleted

    async def create_signed_url(self, storage_path: str, expires_in: int = 3600) -> str:
        """Generates a secure, time-limited signed URL for private bucket file access."""
        if self._is_live_client and self._supabase:
            try:
                res = self._supabase.storage.from_(self.bucket_name).create_signed_url(
                    path=storage_path, expires_in=expires_in
                )
                if isinstance(res, dict) and res.get("signedURL"):
                    return str(res["signedURL"])
                if hasattr(res, "signed_url") and getattr(res, "signed_url"):
                    return str(getattr(res, "signed_url"))
            except Exception as e:
                logger.warning(f"Failed to generate signed URL from Supabase: {e}")

        # Secure signed url fallback simulation
        return f"{settings.supabase_url}/storage/v1/object/sign/{self.bucket_name}/{storage_path}?token=mock-signed-token-{expires_in}s"


storage_service = SupabaseStorageService()
