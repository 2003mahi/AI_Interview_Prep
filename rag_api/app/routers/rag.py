from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from typing import List, Any
import os
import uuid

from ..config import Settings
from ..services.rag import retrieve_and_generate
from ..dependencies import get_user_id

router = APIRouter()

class QueryRequest(BaseModel):
    query: str = Field(..., description="User query")
    metadata_filter: dict | None = Field(default=None, description="Optional metadata filters for retrieval")

class AnswerResponse(BaseModel):
    answer: str
    citations: List[dict] = Field(..., description="List of source citations with document IDs and snippets")
    evidence_sufficient: bool = Field(..., description="Whether retrieved evidence met similarity threshold")

@router.post("/query", response_model=AnswerResponse)
async def query_endpoint(request: QueryRequest, user_id: str = Depends(get_user_id)):
    # Enforce user isolation: only retrieve documents belonging to this user
    result = await retrieve_and_generate(
        query=request.query,
        user_id=user_id,
        metadata_filter=request.metadata_filter,
        settings=Settings(),
    )
    if not result:
        raise HTTPException(status_code=500, detail="RAG generation failed")
    return AnswerResponse(
        answer=result["answer"],
        citations=result["citations"],
        evidence_sufficient=result["evidence_sufficient"],
    )
