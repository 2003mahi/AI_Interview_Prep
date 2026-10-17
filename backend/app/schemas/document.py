"""Pydantic schemas for Document Ingestion API."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class DocumentType(str, Enum):
    RESUME = "resume"
    JOB_DESCRIPTION = "job_description"
    NOTES = "notes"


class FileType(str, Enum):
    PDF = "pdf"
    DOCX = "docx"
    NOTES = "notes"


class ProcessingStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class NotesIngestRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200, description="Title of the notes document")
    content: str = Field(..., min_length=1, max_length=500_000, description="Raw notes text content")
    doc_type: DocumentType = Field(default=DocumentType.NOTES, description="Category of document")


class DocumentResponse(BaseModel):
    id: str
    user_id: str
    title: str
    doc_type: DocumentType
    file_type: FileType
    original_filename: Optional[str] = None
    storage_path: Optional[str] = None
    file_size_bytes: int
    file_hash: Optional[str] = None
    status: ProcessingStatus
    retry_count: int = 0
    max_retries: int = 3
    error_message: Optional[str] = None
    extracted_text: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class DocumentStatusResponse(BaseModel):
    id: str
    status: ProcessingStatus
    retry_count: int
    max_retries: int
    error_message: Optional[str] = None
    updated_at: datetime


class DocumentListResponse(BaseModel):
    documents: List[DocumentResponse]
    total: int


class SignedUrlResponse(BaseModel):
    signed_url: str
    expires_in: int = 3600
