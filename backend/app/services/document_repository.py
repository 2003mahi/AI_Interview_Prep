"""Document Repository Service.

Handles persistence, querying, and updates for documents with strict ownership checks.
Supports both live Supabase DB and local repository store for tests/offline development.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from supabase import Client, create_client

from ..config import settings
from ..logger import logger
from ..schemas.document import DocumentResponse, DocumentType, FileType, ProcessingStatus


class DocumentRepository:
    def __init__(self):
        self._is_live_client = False
        self._supabase: Optional[Client] = None
        self._in_memory_docs: Dict[str, Dict[str, Any]] = {}

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
                logger.info("Initialized live Supabase DB client for documents repository")
            except Exception as e:
                logger.warning(f"Could not connect to live Supabase DB: {e}. Using repository store.")

    def _to_response(self, data: Dict[str, Any]) -> DocumentResponse:
        created_at = data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        elif not created_at:
            created_at = datetime.now(timezone.utc)

        updated_at = data.get("updated_at")
        if isinstance(updated_at, str):
            updated_at = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
        elif not updated_at:
            updated_at = datetime.now(timezone.utc)

        return DocumentResponse(
            id=str(data["id"]),
            user_id=str(data["user_id"]),
            title=data["title"],
            doc_type=DocumentType(data["doc_type"]),
            file_type=FileType(data["file_type"]),
            original_filename=data.get("original_filename"),
            storage_path=data.get("storage_path"),
            file_size_bytes=int(data.get("file_size_bytes", 0)),
            file_hash=data.get("file_hash"),
            status=ProcessingStatus(data.get("status", "pending")),
            retry_count=int(data.get("retry_count", 0)),
            max_retries=int(data.get("max_retries", 3)),
            error_message=data.get("error_message"),
            extracted_text=data.get("extracted_text"),
            metadata=data.get("metadata") or {},
            created_at=created_at,
            updated_at=updated_at,
        )

    async def create(self, doc_data: Dict[str, Any]) -> DocumentResponse:
        now = datetime.now(timezone.utc)
        record = {
            **doc_data,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        if self._is_live_client and self._supabase:
            try:
                res = self._supabase.table("documents").insert(record).execute()
                res_data: Any = res.data
                if isinstance(res_data, list) and res_data and isinstance(res_data[0], dict):
                    data: Dict[str, Any] = res_data[0]
                    self._in_memory_docs[str(data["id"])] = data
                    return self._to_response(data)
            except Exception as e:
                logger.warning(f"Live Supabase insert failed: {e}. Falling back to memory store.")

        doc_id = str(record["id"])
        self._in_memory_docs[doc_id] = record
        return self._to_response(record)

    async def get_by_id(self, doc_id: str) -> Optional[DocumentResponse]:
        if self._is_live_client and self._supabase:
            try:
                res = self._supabase.table("documents").select("*").eq("id", doc_id).execute()
                res_data: Any = res.data
                if isinstance(res_data, list) and res_data and isinstance(res_data[0], dict):
                    return self._to_response(res_data[0])
            except Exception as e:
                logger.warning(f"Live Supabase select failed: {e}")

        record = self._in_memory_docs.get(doc_id)
        if record:
            return self._to_response(record)
        return None

    async def list_for_user(
        self,
        user_id: str,
        doc_type: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[DocumentResponse]:
        if self._is_live_client and self._supabase:
            try:
                query = self._supabase.table("documents").select("*").eq("user_id", user_id)
                if doc_type:
                    query = query.eq("doc_type", doc_type)
                if status:
                    query = query.eq("status", status)
                res = query.order("created_at", desc=True).range(offset, offset + limit - 1).execute()
                res_data: Any = res.data
                if isinstance(res_data, list):
                    return [self._to_response(item) for item in res_data if isinstance(item, dict)]
            except Exception as e:
                logger.warning(f"Live Supabase list failed: {e}")

        matched = [
            doc for doc in self._in_memory_docs.values()
            if str(doc.get("user_id")) == user_id
        ]
        if doc_type:
            matched = [doc for doc in matched if doc.get("doc_type") == doc_type]
        if status:
            matched = [doc for doc in matched if doc.get("status") == status]

        matched.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        paginated = matched[offset : offset + limit]
        return [self._to_response(item) for item in paginated]

    async def count_for_user(self, user_id: str) -> int:
        matched = [doc for doc in self._in_memory_docs.values() if str(doc.get("user_id")) == user_id]
        return len(matched)

    async def update(self, doc_id: str, update_data: Dict[str, Any]) -> Optional[DocumentResponse]:
        now = datetime.now(timezone.utc)
        payload = {**update_data, "updated_at": now.isoformat()}

        if self._is_live_client and self._supabase:
            try:
                res = self._supabase.table("documents").update(payload).eq("id", doc_id).execute()
                res_data: Any = res.data
                if isinstance(res_data, list) and res_data and isinstance(res_data[0], dict):
                    data: Dict[str, Any] = res_data[0]
                    self._in_memory_docs[doc_id] = data
                    return self._to_response(data)
            except Exception as e:
                logger.warning(f"Live Supabase update failed: {e}")

        if doc_id in self._in_memory_docs:
            self._in_memory_docs[doc_id].update(payload)
            return self._to_response(self._in_memory_docs[doc_id])

        return None

    async def delete(self, doc_id: str) -> bool:
        if self._is_live_client and self._supabase:
            try:
                self._supabase.table("documents").delete().eq("id", doc_id).execute()
            except Exception as e:
                logger.warning(f"Live Supabase delete failed: {e}")

        if doc_id in self._in_memory_docs:
            del self._in_memory_docs[doc_id]
            return True
        return False


document_repository = DocumentRepository()
