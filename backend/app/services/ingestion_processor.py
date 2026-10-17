"""Asynchronous Document Ingestion Processor with Retries and Status Tracking."""

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from ..config import settings
from ..logger import logger
from ..schemas.document import FileType, ProcessingStatus
from .document_repository import document_repository
from .storage_service import storage_service
from .text_extractor import extract_text


class DocumentIngestionProcessor:
    def __init__(
        self,
        max_retries: Optional[int] = None,
        base_retry_delay: Optional[float] = None,
    ):
        self.max_retries = max_retries
        self.base_retry_delay = base_retry_delay

    @property
    def current_base_delay(self) -> float:
        if self.base_retry_delay is not None:
            return self.base_retry_delay
        return settings.ingestion_retry_delay_seconds

    @property
    def current_max_retries(self) -> int:
        if self.max_retries is not None:
            return self.max_retries
        return settings.ingestion_max_retries

    async def process_document(
        self,
        document_id: str,
        raw_notes_content: Optional[str] = None,
    ) -> None:
        """
        Executes document parsing asynchronously with exponential backoff retries.
        Tracks progress via status updates: pending -> processing -> completed / failed.
        """
        doc = await document_repository.get_by_id(document_id)
        if not doc:
            logger.error(f"Cannot process document {document_id}: not found in repository")
            return

        # Mark as processing
        await document_repository.update(
            document_id,
            {"status": ProcessingStatus.PROCESSING.value, "error_message": None},
        )
        logger.info(f"Started ingestion processing for document {document_id} ({doc.file_type})")

        current_retries = doc.retry_count
        success = False
        last_error = ""

        max_retries = self.current_max_retries
        base_delay = self.current_base_delay

        while current_retries <= max_retries and not success:
            try:
                # 1. Fetch content
                if doc.file_type == FileType.NOTES:
                    content_to_extract: Any = raw_notes_content or doc.extracted_text or ""
                else:
                    if not doc.storage_path:
                        raise ValueError("Missing storage path for uploaded file")
                    content_to_extract = await storage_service.download_file(doc.storage_path)

                # 2. Extract text & structural metadata
                extracted_text, extraction_meta = extract_text(doc.file_type, content_to_extract)

                # 3. Preserve and merge comprehensive source metadata
                merged_metadata: Dict[str, Any] = {
                    **doc.metadata,
                    **extraction_meta,
                    "processed_at": datetime.now(timezone.utc).isoformat(),
                    "file_size_bytes": doc.file_size_bytes,
                    "file_hash": doc.file_hash,
                    "original_filename": doc.original_filename,
                }

                # 4. Mark completed
                await document_repository.update(
                    document_id,
                    {
                        "status": ProcessingStatus.COMPLETED.value,
                        "extracted_text": extracted_text,
                        "metadata": merged_metadata,
                        "retry_count": current_retries,
                        "error_message": None,
                    },
                )
                success = True
                logger.info(
                    f"Successfully processed document {document_id} with {extraction_meta.get('word_count', 0)} words"
                )
                break

            except Exception as e:
                last_error = str(e)
                current_retries += 1
                logger.warning(
                    f"Processing attempt {current_retries} failed for document {document_id}: {last_error}"
                )

                if current_retries <= max_retries:
                    # Exponential backoff
                    delay = base_delay * (2 ** (current_retries - 1))
                    await document_repository.update(
                        document_id,
                        {
                            "retry_count": current_retries,
                            "error_message": f"Retry {current_retries}/{max_retries}: {last_error}",
                        },
                    )
                    await asyncio.sleep(delay)
                else:
                    # Exhausted retries -> mark as failed
                    await document_repository.update(
                        document_id,
                        {
                            "status": ProcessingStatus.FAILED.value,
                            "retry_count": current_retries - 1,
                            "error_message": f"Processing failed after {max_retries} retries: {last_error}",
                        },
                    )
                    logger.error(
                        f"Document {document_id} marked as FAILED after {max_retries} retries"
                    )


ingestion_processor = DocumentIngestionProcessor()
