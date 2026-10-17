"""Document Ingestion API Endpoints.

Provides endpoints for resume, job description, PDF, DOCX, and notes ingestion.
Enforces:
- Supabase JWT authentication
- Strict user ownership isolation
- Size limits and file content sniffing
- Asynchronous processing with background tasks
- Secure deletion from both storage and database
"""

import uuid
from typing import Optional
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)

from ...auth import AuthenticatedUser, get_current_user
from ...config import settings
from ...logger import logger
from ...schemas.document import (
    DocumentListResponse,
    DocumentResponse,
    DocumentStatusResponse,
    DocumentType,
    FileType,
    NotesIngestRequest,
    ProcessingStatus,
    SignedUrlResponse,
)
from ...services.document_repository import document_repository
from ...services.document_validator import (
    calculate_sha256,
    sanitize_and_validate_notes,
    sanitize_filename,
    sniff_and_validate_file,
    validate_file_size,
)
from ...services.ingestion_processor import ingestion_processor
from ...services.storage_service import storage_service

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post(
    "/upload",
    response_model=DocumentResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload PDF or DOCX file (Resume or Job Description)",
)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="PDF or DOCX file to upload"),
    title: str = Form(..., min_length=1, max_length=200, description="Title or label for document"),
    doc_type: DocumentType = Form(DocumentType.RESUME, description="Document type: resume or job_description"),
    user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Accepts untrusted PDF/DOCX file:
    1. Validates size limit and magic byte signatures
    2. Enforces sanitized storage path scoped to authenticated user: {user_id}/{doc_id}/{filename}
    3. Uploads to private Supabase Storage
    4. Creates database record with status PENDING
    5. Queues background asynchronous text extraction with retry support
    """
    content = await file.read()
    validate_file_size(content, max_bytes=settings.max_file_size_bytes)

    # Validate file type using magic byte content sniffing
    original_name = file.filename or "uploaded_file"
    file_type, detected_mime = sniff_and_validate_file(
        content=content,
        filename=original_name,
        declared_content_type=file.content_type,
    )

    clean_name = sanitize_filename(original_name)
    doc_id = str(uuid.uuid4())
    file_hash = calculate_sha256(content)

    # Scoped storage path in private bucket
    storage_path = storage_service.build_storage_path(user.id, doc_id, clean_name)

    # Upload to private storage
    await storage_service.upload_file(
        storage_path=storage_path,
        content=content,
        content_type=detected_mime,
    )

    # Initial metadata
    doc_meta = {
        "original_filename": original_name,
        "mime_type": detected_mime,
        "content_length": len(content),
    }

    # Create document record
    doc_record = {
        "id": doc_id,
        "user_id": user.id,
        "title": title.strip(),
        "doc_type": doc_type.value,
        "file_type": file_type.value,
        "original_filename": clean_name,
        "storage_path": storage_path,
        "file_size_bytes": len(content),
        "file_hash": file_hash,
        "status": ProcessingStatus.PENDING.value,
        "retry_count": 0,
        "max_retries": settings.ingestion_max_retries,
        "metadata": doc_meta,
    }

    created_doc = await document_repository.create(doc_record)

    # Queue async processing with retries
    background_tasks.add_task(ingestion_processor.process_document, doc_id)

    return created_doc


@router.post(
    "/notes",
    response_model=DocumentResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ingest plain text notes",
)
async def ingest_notes(
    request: NotesIngestRequest,
    background_tasks: BackgroundTasks,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Ingests plain notes text:
    1. Sanitizes untrusted text against control codes and null characters
    2. Stores notes text safely in private storage as a text artifact
    3. Queues background asynchronous processing
    """
    sanitized_content = sanitize_and_validate_notes(request.content)
    raw_bytes = sanitized_content.encode("utf-8")
    validate_file_size(raw_bytes, max_bytes=settings.max_file_size_bytes)

    doc_id = str(uuid.uuid4())
    file_hash = calculate_sha256(raw_bytes)
    storage_path = storage_service.build_storage_path(user.id, doc_id, "notes.txt")

    # Store notes in private storage
    await storage_service.upload_file(
        storage_path=storage_path,
        content=raw_bytes,
        content_type="text/plain; charset=utf-8",
    )

    doc_record = {
        "id": doc_id,
        "user_id": user.id,
        "title": request.title.strip(),
        "doc_type": request.doc_type.value,
        "file_type": FileType.NOTES.value,
        "original_filename": "notes.txt",
        "storage_path": storage_path,
        "file_size_bytes": len(raw_bytes),
        "file_hash": file_hash,
        "status": ProcessingStatus.PENDING.value,
        "retry_count": 0,
        "max_retries": settings.ingestion_max_retries,
        "metadata": {
            "mime_type": "text/plain",
            "content_length": len(raw_bytes),
        },
    }

    created_doc = await document_repository.create(doc_record)

    # Queue background task
    background_tasks.add_task(
        ingestion_processor.process_document, doc_id, sanitized_content
    )

    return created_doc


@router.get(
    "",
    response_model=DocumentListResponse,
    summary="List all documents owned by current authenticated user",
)
async def list_documents(
    doc_type: Optional[DocumentType] = Query(None, description="Filter by document type"),
    status_filter: Optional[ProcessingStatus] = Query(None, alias="status", description="Filter by status"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: AuthenticatedUser = Depends(get_current_user),
):
    """Lists documents owned exclusively by the caller."""
    docs = await document_repository.list_for_user(
        user_id=user.id,
        doc_type=doc_type.value if doc_type else None,
        status=status_filter.value if status_filter else None,
        limit=limit,
        offset=offset,
    )
    total = await document_repository.count_for_user(user.id)
    return DocumentListResponse(documents=docs, total=total)


@router.get(
    "/{document_id}",
    response_model=DocumentResponse,
    summary="Get document details, status, and extracted text",
)
async def get_document(
    document_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """Enforces strict ownership: users cannot read another user's document."""
    doc = await document_repository.get_by_id(document_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    if doc.user_id != user.id:
        logger.warning(f"Unauthorized document access attempt: User {user.id} requested {document_id}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: you do not own this document",
        )

    return doc


@router.get(
    "/{document_id}/status",
    response_model=DocumentStatusResponse,
    summary="Check processing status of a document",
)
async def get_document_status(
    document_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """Status polling endpoint with ownership check."""
    doc = await get_document(document_id, user)
    return DocumentStatusResponse(
        id=doc.id,
        status=doc.status,
        retry_count=doc.retry_count,
        max_retries=doc.max_retries,
        error_message=doc.error_message,
        updated_at=doc.updated_at,
    )


@router.get(
    "/{document_id}/download",
    response_model=SignedUrlResponse,
    summary="Get secure signed URL for private bucket download",
)
async def get_document_download_url(
    document_id: str,
    expires_in: int = Query(3600, ge=60, le=86400, description="Expiration time in seconds"),
    user: AuthenticatedUser = Depends(get_current_user),
):
    """Generates time-limited signed URL for private storage object."""
    doc = await get_document(document_id, user)
    if not doc.storage_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No storage file associated with this document",
        )

    signed_url = await storage_service.create_signed_url(doc.storage_path, expires_in=expires_in)
    return SignedUrlResponse(signed_url=signed_url, expires_in=expires_in)


@router.post(
    "/{document_id}/retry",
    response_model=DocumentResponse,
    summary="Manually retry failed document ingestion",
)
async def retry_document_ingestion(
    document_id: str,
    background_tasks: BackgroundTasks,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """Allows owners to trigger reprocessing of failed documents."""
    doc = await get_document(document_id, user)

    # Reset retry count and status
    updated = await document_repository.update(
        document_id,
        {
            "status": ProcessingStatus.PENDING.value,
            "retry_count": 0,
            "error_message": None,
        },
    )

    background_tasks.add_task(ingestion_processor.process_document, document_id)
    return updated or doc


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete document from database and private storage",
)
async def delete_document(
    document_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Secure deletion:
    1. Enforces ownership
    2. Deletes from private Supabase Storage bucket
    3. Deletes record and metadata from database
    """
    doc = await get_document(document_id, user)

    # 1. Delete physical object from storage
    if doc.storage_path:
        await storage_service.delete_file(doc.storage_path)

    # 2. Delete database record
    await document_repository.delete(document_id)

    logger.info(f"Successfully deleted document {document_id} and storage for user {user.id}")
    return {
        "message": "Document and associated storage deleted successfully",
        "id": document_id,
    }
