"""Job Readiness Repository Service.

Handles persistence, retrieval, and queries for Job Readiness analyses
via live Supabase PostgreSQL DB or in-memory fallback for offline/testing.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid
from supabase import Client, create_client

from ..config import settings
from ..logger import logger
from ..schemas.readiness import JobReadinessAnalysisResult, JobReadinessRecord


class JobReadinessRepository:
    def __init__(self):
        self._is_live_client = False
        self._supabase: Optional[Client] = None
        self._in_memory_records: Dict[str, Dict[str, Any]] = {}

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
                logger.info("Initialized live Supabase DB client for Job Readiness repository")
            except Exception as e:
                logger.warning(f"Could not connect to live Supabase DB: {e}. Using repository store.")

    def _to_record(self, data: Dict[str, Any]) -> JobReadinessRecord:
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

        raw_analysis = data.get("analysis", {})
        if isinstance(raw_analysis, str):
            import json
            try:
                raw_analysis = json.loads(raw_analysis)
            except Exception:
                raw_analysis = {}

        analysis_obj = JobReadinessAnalysisResult.model_validate(raw_analysis)

        return JobReadinessRecord(
            id=str(data["id"]),
            user_id=str(data["user_id"]),
            job_title=data.get("job_title"),
            overall_score=float(data.get("overall_score", 0.0)),
            analysis=analysis_obj,
            created_at=created_at,
            updated_at=updated_at,
        )

    async def save_analysis(
        self,
        user_id: str,
        analysis: JobReadinessAnalysisResult,
        job_title: Optional[str] = None,
        record_id: Optional[str] = None,
    ) -> JobReadinessRecord:
        now = datetime.now(timezone.utc)
        rid = record_id or str(uuid.uuid4())

        record_data = {
            "id": rid,
            "user_id": str(user_id),
            "job_title": job_title or analysis.job_title or "Target Role",
            "overall_score": analysis.readiness_score.overall_score,
            "analysis": analysis.model_dump(),
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        if self._is_live_client and self._supabase:
            try:
                res = self._supabase.table("job_readiness_analyses").insert(record_data).execute()
                res_data: Any = res.data
                if isinstance(res_data, list) and res_data and isinstance(res_data[0], dict):
                    data: Dict[str, Any] = res_data[0]
                    self._in_memory_records[str(data["id"])] = data
                    return self._to_record(data)
            except Exception as e:
                logger.warning(f"Live Supabase insert failed for job readiness: {e}. Falling back to memory store.")

        self._in_memory_records[rid] = record_data
        return self._to_record(record_data)

    async def get_by_id(self, analysis_id: str) -> Optional[JobReadinessRecord]:
        if self._is_live_client and self._supabase:
            try:
                res = self._supabase.table("job_readiness_analyses").select("*").eq("id", analysis_id).execute()
                res_data: Any = res.data
                if isinstance(res_data, list) and res_data and isinstance(res_data[0], dict):
                    return self._to_record(res_data[0])
            except Exception as e:
                logger.warning(f"Live Supabase select failed: {e}")

        data = self._in_memory_records.get(analysis_id)
        if data:
            return self._to_record(data)
        return None

    async def list_for_user(
        self,
        user_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> List[JobReadinessRecord]:
        if self._is_live_client and self._supabase:
            try:
                res = (
                    self._supabase.table("job_readiness_analyses")
                    .select("*")
                    .eq("user_id", user_id)
                    .order("created_at", desc=True)
                    .range(offset, offset + limit - 1)
                    .execute()
                )
                res_data: Any = res.data
                if isinstance(res_data, list):
                    return [self._to_record(item) for item in res_data if isinstance(item, dict)]
            except Exception as e:
                logger.warning(f"Live Supabase list failed: {e}")

        matched = [
            rec for rec in self._in_memory_records.values()
            if str(rec.get("user_id")) == str(user_id)
        ]
        matched.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        paginated = matched[offset : offset + limit]
        return [self._to_record(item) for item in paginated]

    async def delete(self, analysis_id: str) -> bool:
        if self._is_live_client and self._supabase:
            try:
                self._supabase.table("job_readiness_analyses").delete().eq("id", analysis_id).execute()
            except Exception as e:
                logger.warning(f"Live Supabase delete failed: {e}")

        if analysis_id in self._in_memory_records:
            del self._in_memory_records[analysis_id]
            return True
        return False


job_readiness_repository = JobReadinessRepository()
