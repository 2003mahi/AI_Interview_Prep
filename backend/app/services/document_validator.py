"""Secure Document Validation Service.

Validates uploaded files and content treating all inputs as untrusted:
- Enforces strict file size limits
- Sanitizes file names against path traversal and malicious characters
- Inspects magic bytes (content sniffing) rather than trusting client MIME types
- Prevents zip-bomb attacks and verifies internal DOCX XML structures
- Sanitizes raw notes text against control characters and null bytes
"""

import hashlib
import os
import re
import zipfile
from io import BytesIO
from typing import Optional, Tuple
from fastapi import HTTPException, status

from ..config import settings
from ..schemas.document import FileType

# Security thresholds
MAX_DOCX_UNCOMPRESSED_BYTES = 50 * 1024 * 1024  # 50 MB
MAX_DOCX_ENTRIES = 1000
MAX_COMPRESSION_RATIO = 100  # uncompressed / compressed ratio limit


class DocumentValidationError(HTTPException):
    def __init__(self, detail: str, status_code: int = status.HTTP_400_BAD_REQUEST):
        super().__init__(status_code=status_code, detail=detail)


class MalformedFileError(DocumentValidationError):
    def __init__(self, detail: str):
        super().__init__(detail=f"Malformed file: {detail}", status_code=422)


class FileSizeLimitExceededError(DocumentValidationError):
    def __init__(self, size_bytes: int, max_bytes: int):
        detail = f"File size ({size_bytes} bytes) exceeds the maximum allowed limit of {max_bytes} bytes"
        super().__init__(detail=detail, status_code=413)


def sanitize_filename(filename: Optional[str]) -> str:
    """Sanitizes user-provided filename to prevent path traversal and injection."""
    if not filename:
        return "unnamed_document"
    # Take basename only to strip any path directory traversal
    base = os.path.basename(filename.strip().replace("\\", "/"))
    # Remove null bytes
    base = base.replace("\x00", "")
    # Keep only safe alphanumeric characters, underscores, hyphens, and dots
    clean = re.sub(r"[^a-zA-Z0-9_.-]", "_", base)
    # Strip leading dots to prevent hidden files
    clean = clean.lstrip(".")
    if not clean:
        clean = "document"
    # Limit length to 120 chars
    return clean[:120]


def calculate_sha256(content: bytes) -> str:
    """Calculates SHA-256 hex digest for cryptographic integrity."""
    return hashlib.sha256(content).hexdigest()


def validate_file_size(content: bytes, max_bytes: Optional[int] = None) -> None:
    """Verifies file does not exceed maximum allowable size."""
    limit = max_bytes if max_bytes is not None else settings.max_file_size_bytes
    if len(content) > limit:
        raise FileSizeLimitExceededError(size_bytes=len(content), max_bytes=limit)
    if len(content) == 0:
        raise DocumentValidationError("Uploaded file is empty (0 bytes)")


def validate_pdf(content: bytes) -> None:
    """
    Validates PDF format using magic bytes and structural checks.
    Treats input as untrusted.
    """
    if len(content) < 5:
        raise MalformedFileError("File is too short to be a valid PDF")
    
    # PDF magic byte signature
    if not content.startswith(b"%PDF-"):
        raise MalformedFileError("Missing valid PDF header (%PDF- magic bytes)")

    # Ensure EOF marker exists somewhere near the end of the file
    tail = content[-1024:] if len(content) >= 1024 else content
    if b"%%EOF" not in tail and b"%EOF" not in tail:
        # Some linearized or truncated PDFs lack EOF
        # We verify if at least one xref or trailer exists
        if b"xref" not in content and b"obj" not in content:
            raise MalformedFileError("PDF structure is truncated or corrupted (no valid object catalog)")


def validate_docx(content: bytes) -> None:
    """
    Validates DOCX format:
    - Verifies PK zip magic bytes
    - Verifies zip structure safely (zip-bomb guard)
    - Verifies presence of [Content_Types].xml and word/document.xml
    """
    if len(content) < 4:
        raise MalformedFileError("File is too short to be a valid DOCX")

    # ZIP magic signature
    if not content.startswith(b"PK\x03\x04"):
        raise MalformedFileError("Missing valid DOCX/ZIP signature (PK header)")

    try:
        with zipfile.ZipFile(BytesIO(content)) as zf:
            infolist = zf.infolist()
            if len(infolist) > MAX_DOCX_ENTRIES:
                raise MalformedFileError("DOCX archive contains too many files (possible zip-bomb)")

            total_uncompressed = 0
            has_content_types = False
            has_word_document = False

            for info in infolist:
                # Path traversal check inside zip
                if info.filename.startswith("/") or ".." in info.filename:
                    raise MalformedFileError("Malicious archive structure detected (path traversal)")

                total_uncompressed += info.file_size
                if total_uncompressed > MAX_DOCX_UNCOMPRESSED_BYTES:
                    raise MalformedFileError("DOCX uncompressed size exceeds safe threshold (possible zip-bomb)")

                if info.filename == "[Content_Types].xml":
                    has_content_types = True
                if info.filename == "word/document.xml" or info.filename.startswith("word/"):
                    has_word_document = True

            compressed_len = max(len(content), 1)
            if (total_uncompressed / compressed_len) > MAX_COMPRESSION_RATIO:
                raise MalformedFileError("Abnormal compression ratio detected (potential zip-bomb)")

            if not has_content_types or not has_word_document:
                raise MalformedFileError("DOCX package missing required [Content_Types].xml or word components")

    except zipfile.BadZipFile as e:
        raise MalformedFileError(f"Corrupt or invalid ZIP archive: {str(e)}")


def sanitize_and_validate_notes(text: str) -> str:
    """
    Sanitizes raw text notes:
    - Removes null bytes
    - Removes dangerous ASCII control codes while preserving newlines and tabs
    - Checks content length
    """
    if not text or not text.strip():
        raise DocumentValidationError("Notes content cannot be empty")

    # Strip null characters
    sanitized = text.replace("\x00", "")

    # Strip non-printable ASCII control characters except \t (0x09), \n (0x0A), \r (0x0D)
    sanitized = re.sub(r"[\x01-\x08\x0B\x0C\x0E-\x1F\x7F]", "", sanitized)

    if not sanitized.strip():
        raise DocumentValidationError("Notes content contains only unprintable control characters")

    return sanitized


def sniff_and_validate_file(
    content: bytes,
    filename: str,
    declared_content_type: Optional[str] = None
) -> Tuple[FileType, str]:
    """
    Detects file type, validates magic bytes, and returns (FileType, mime_type).
    Never trusts client declared content type blindly.
    """
    validate_file_size(content)

    sanitized_name = sanitize_filename(filename)
    lower_name = sanitized_name.lower()

    if content.startswith(b"%PDF-"):
        validate_pdf(content)
        return FileType.PDF, "application/pdf"

    if content.startswith(b"PK\x03\x04") and (lower_name.endswith(".docx") or "officedocument" in (declared_content_type or "").lower()):
        validate_docx(content)
        return FileType.DOCX, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    # If it ends with .docx or .pdf but magic bytes failed
    if lower_name.endswith(".pdf"):
        # Header check failed
        raise MalformedFileError("File has .pdf extension but lacks valid PDF signature")

    if lower_name.endswith(".docx"):
        raise MalformedFileError("File has .docx extension but lacks valid PK ZIP signature")

    raise DocumentValidationError(
        f"Unsupported file type. Only PDF and DOCX files are accepted for file upload (received: '{sanitized_name}')."
    )
