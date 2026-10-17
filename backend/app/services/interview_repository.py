"""Interview Persistence Repository Service.

Manages persistence and retrieval of adaptive interview sessions and interactions
using Supabase PostgreSQL with safe in-memory fallback for local development & testing.
"""

from datetime import datetime, timezone
import json
from typing import Any, Dict, List, Optional
import uuid
from supabase import Client, create_client

from ..config import settings
from ..logger import logger
from ..schemas.interview import (
    InteractionTurn,
    InterviewSessionState,
    SessionStatus,
)


class InterviewRepository:
    def __init__(self):
        self._is_live_client = False
        self._supabase: Optional[Client] = None
        self._in_memory_sessions: Dict[str, Dict[str, Any]] = {}
        self._in_memory_interactions: Dict[str, List[Dict[str, Any]]] = {}

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
                logger.info("Initialized live Supabase DB client for Interview repository")
            except Exception as e:
                logger.warning(f"Could not connect to live Supabase DB: {e}. Using in-memory interview repository.")

    def _state_to_db_payload(self, state: InterviewSessionState) -> Dict[str, Any]:
        """Convert InterviewSessionState to Supabase interview_sessions row payload."""
        now = datetime.now(timezone.utc).isoformat()
        topics_str = state.target_topics[0].value if state.target_topics else "general"

        state_dict = state.model_dump()
        return {
            "id": state.session_id,
            "user_id": state.user_id,
            "role": state.role,
            "experience_years": state.experience_years,
            "topic": topics_str,
            "status": state.status,
            "score": state.average_score,
            "summary_feedback": state.summary_feedback,
            "state_metadata": state_dict,
            "updated_at": now,
        }

    async def save_session(self, state: InterviewSessionState) -> InterviewSessionState:
        """Persist or update interview session state."""
        payload = self._state_to_db_payload(state)
        now = datetime.now(timezone.utc).isoformat()

        # Update in-memory store
        self._in_memory_sessions[state.session_id] = payload

        if self._is_live_client and self._supabase:
            try:
                # Upsert into interview_sessions
                # We attempt update first, if 0 rows modified then insert
                update_res = (
                    self._supabase.table("interview_sessions")
                    .update({
                        "status": payload["status"],
                        "score": payload["score"],
                        "summary_feedback": payload["summary_feedback"],
                        "updated_at": payload["updated_at"],
                    })
                    .eq("id", state.session_id)
                    .execute()
                )

                if not update_res.data:
                    # Session not in DB yet, insert new record
                    insert_payload = {
                        "id": payload["id"],
                        "user_id": payload["user_id"],
                        "role": payload["role"],
                        "experience_years": payload["experience_years"],
                        "topic": payload["topic"],
                        "status": payload["status"],
                        "score": payload["score"],
                        "summary_feedback": payload["summary_feedback"],
                        "created_at": now,
                        "updated_at": now,
                    }
                    self._supabase.table("interview_sessions").insert(insert_payload).execute()
            except Exception as e:
                logger.warning(f"Live Supabase save_session failed: {e}. Maintained in memory.")

        return state

    async def get_session_by_id(self, session_id: str) -> Optional[InterviewSessionState]:
        """Retrieve interview session by ID, reconstructing full state from metadata or interactions."""
        # Check live Supabase
        if self._is_live_client and self._supabase:
            try:
                res = self._supabase.table("interview_sessions").select("*").eq("id", session_id).execute()
                res_data: Any = res.data
                if isinstance(res_data, list) and res_data and isinstance(res_data[0], dict):
                    row = res_data[0]
                    # Check if rich state_metadata is stored in row or fallback memory
                    metadata = row.get("state_metadata")
                    if isinstance(metadata, str):
                        try:
                            metadata = json.loads(metadata)
                        except Exception:
                            metadata = None
                    if isinstance(metadata, dict) and "session_id" in metadata:
                        return InterviewSessionState.model_validate(metadata)

                    # Alternatively, check memory for cached full state
                    if session_id in self._in_memory_sessions:
                        mem_data = self._in_memory_sessions[session_id].get("state_metadata")
                        if mem_data:
                            return InterviewSessionState.model_validate(mem_data)

                    # Minimal fallback reconstruction from base columns
                    return InterviewSessionState(
                        session_id=str(row["id"]),
                        user_id=str(row["user_id"]),
                        role=row.get("role", "AI Engineer"),
                        experience_years=int(row.get("experience_years", 3)),
                        status=row.get("status", SessionStatus.IN_PROGRESS.value),
                        average_score=float(row["score"]) if row.get("score") is not None else None,
                        summary_feedback=row.get("summary_feedback"),
                    )
            except Exception as e:
                logger.warning(f"Live Supabase get_session_by_id failed: {e}")

        # In-memory retrieval
        mem_row = self._in_memory_sessions.get(session_id)
        if mem_row:
            state_meta = mem_row.get("state_metadata")
            if state_meta:
                return InterviewSessionState.model_validate(state_meta)

        return None

    async def list_user_sessions(
        self,
        user_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> List[InterviewSessionState]:
        """List all interview sessions owned by a specific user."""
        results: List[InterviewSessionState] = []

        if self._is_live_client and self._supabase:
            try:
                res = (
                    self._supabase.table("interview_sessions")
                    .select("*")
                    .eq("user_id", user_id)
                    .order("created_at", desc=True)
                    .range(offset, offset + limit - 1)
                    .execute()
                )
                res_data: Any = res.data
                if isinstance(res_data, list):
                    for row in res_data:
                        if isinstance(row, dict):
                            sid = str(row["id"])
                            cached = await self.get_session_by_id(sid)
                            if cached:
                                results.append(cached)
                    return results
            except Exception as e:
                logger.warning(f"Live Supabase list_user_sessions failed: {e}")

        # In-memory list
        user_matches = [
            InterviewSessionState.model_validate(data["state_metadata"])
            for sid, data in self._in_memory_sessions.items()
            if data.get("user_id") == user_id and "state_metadata" in data
        ]
        return user_matches[offset : offset + limit]

    async def record_interaction(
        self,
        session_id: str,
        turn: InteractionTurn,
    ) -> None:
        """Persist an individual question-answer turn in Supabase interview_interactions table."""
        now = datetime.now(timezone.utc).isoformat()
        interaction_data = {
            "id": turn.id or str(uuid.uuid4()),
            "session_id": session_id,
            "question": turn.question,
            "user_answer": turn.user_answer,
            "feedback": turn.feedback,
            "score": turn.score,
            "created_at": now,
        }

        # Save to memory
        if session_id not in self._in_memory_interactions:
            self._in_memory_interactions[session_id] = []
        self._in_memory_interactions[session_id].append(interaction_data)

        # Save to Supabase
        if self._is_live_client and self._supabase:
            try:
                self._supabase.table("interview_interactions").insert(interaction_data).execute()
            except Exception as e:
                logger.warning(f"Live Supabase record_interaction failed: {e}. Saved in memory.")

    async def delete_session(self, session_id: str) -> bool:
        """Delete an interview session and its child interactions."""
        self._in_memory_sessions.pop(session_id, None)
        self._in_memory_interactions.pop(session_id, None)

        if self._is_live_client and self._supabase:
            try:
                self._supabase.table("interview_sessions").delete().eq("id", session_id).execute()
                return True
            except Exception as e:
                logger.warning(f"Live Supabase delete_session failed: {e}")
                return False

        return True


interview_repository = InterviewRepository()
