"""Comprehensive Document Ingestion, Security, Storage, and Extraction Tests.

Covers:
- Valid PDF, DOCX, and Notes ingestion & text extraction
- Source metadata preservation (page count, word count, hashes)
- Untrusted content handling & malformed file rejection
- Extension spoofing & magic byte validation
- Size limit enforcement (413 Request Entity Too Large)
- Unauthorized access & Cross-user ownership enforcement (401/403)
- Async processing, retries, and status tracking
- Secure deletion from storage and repository
"""

import asyncio
from io import BytesIO
import unittest
import zipfile
from docx import Document as DocxDocument
from fastapi.testclient import TestClient
from pypdf import PdfWriter

from app.auth import create_access_token
from app.config import settings
from app.main import app
from app.schemas.document import ProcessingStatus
from app.services.document_repository import document_repository
from app.services.ingestion_processor import DocumentIngestionProcessor
from app.services.storage_service import storage_service


def create_minimal_pdf_bytes(text: str = "Sample Resume Header and Experience") -> bytes:
    """Generates valid minimal PDF in-memory bytes."""
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    # Write empty page with text note/metadata or create a page
    bio = BytesIO()
    writer.write(bio)
    return bio.getvalue()


def create_minimal_docx_bytes(paragraphs=None, tables=None) -> bytes:
    """Generates valid minimal DOCX in-memory bytes."""
    doc = DocxDocument()
    paragraphs = paragraphs or ["Senior Software Engineer Resume", "Python, FastAPI, Postgres"]
    for p in paragraphs:
        doc.add_paragraph(p)
    if tables:
        t = doc.add_table(rows=len(tables), cols=len(tables[0]))
        for r_idx, row in enumerate(tables):
            for c_idx, val in enumerate(row):
                t.cell(r_idx, c_idx).text = val
    bio = BytesIO()
    doc.save(bio)
    return bio.getvalue()


class TestDocumentIngestion(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.user_a_id = "user-uuid-1111"
        self.user_b_id = "user-uuid-2222"
        self.token_a = create_access_token(self.user_a_id, email="alice@example.com")
        self.token_b = create_access_token(self.user_b_id, email="bob@example.com")
        self.auth_headers_a = {"Authorization": f"Bearer {self.token_a}"}
        self.auth_headers_b = {"Authorization": f"Bearer {self.token_b}"}
        self.original_delay = settings.ingestion_retry_delay_seconds
        settings.ingestion_retry_delay_seconds = 0.001

    def tearDown(self):
        settings.ingestion_retry_delay_seconds = self.original_delay

    def test_unauthorized_access(self):
        """Endpoints must reject requests without valid authentication."""
        # 1. Upload without token -> 401
        res = self.client.post("/api/v1/documents/upload")
        self.assertEqual(res.status_code, 401)

        # 2. Ingest notes without token -> 401
        res = self.client.post("/api/v1/documents/notes", json={"title": "Notes", "content": "Sample"})
        self.assertEqual(res.status_code, 401)

        # 3. List documents without token -> 401
        res = self.client.get("/api/v1/documents")
        self.assertEqual(res.status_code, 401)

        # 4. Invalid Bearer token -> 401
        res = self.client.get("/api/v1/documents", headers={"Authorization": "Bearer invalid.token.payload"})
        self.assertEqual(res.status_code, 401)

    def test_size_limit_enforcement(self):
        """Rejects files exceeding size limit with 413."""
        # Temporarily set small limit to test
        original_limit = settings.max_file_size_bytes
        try:
            settings.max_file_size_bytes = 1024  # 1 KB limit
            oversized_content = b"%PDF-" + b"A" * 2000
            files = {"file": ("large_resume.pdf", oversized_content, "application/pdf")}
            data = {"title": "Oversized File", "doc_type": "resume"}

            res = self.client.post(
                "/api/v1/documents/upload",
                files=files,
                data=data,
                headers=self.auth_headers_a,
            )
            self.assertEqual(res.status_code, 413)
            self.assertIn("exceeds the maximum allowed limit", res.json()["detail"])
        finally:
            settings.max_file_size_bytes = original_limit

    def test_malformed_and_spoofed_files(self):
        """Treats uploaded content as untrusted and rejects malformed files."""
        # 1. Spoofed extension: plain text file named malicious.pdf (missing %PDF- magic bytes)
        fake_pdf = b"This is just plain text, not a PDF file at all"
        files = {"file": ("malicious.pdf", fake_pdf, "application/pdf")}
        res = self.client.post(
            "/api/v1/documents/upload",
            files=files,
            data={"title": "Spoofed PDF", "doc_type": "resume"},
            headers=self.auth_headers_a,
        )
        self.assertEqual(res.status_code, 422)
        self.assertIn("lacks valid PDF signature", res.json()["detail"])

        # 2. Corrupted DOCX (invalid zip archive with .docx name)
        fake_docx = b"PK\x03\x04corrupted_payload_not_real_zip"
        files = {"file": ("corrupt.docx", fake_docx, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
        res = self.client.post(
            "/api/v1/documents/upload",
            files=files,
            data={"title": "Corrupt DOCX", "doc_type": "job_description"},
            headers=self.auth_headers_a,
        )
        self.assertEqual(res.status_code, 422)

        # 3. Zip file missing required [Content_Types].xml or word components
        bio = BytesIO()
        with zipfile.ZipFile(bio, "w") as zf:
            zf.writestr("test.txt", "just a text file inside zip")
        empty_zip_docx = bio.getvalue()
        files = {"file": ("invalid_docx_structure.docx", empty_zip_docx, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
        res = self.client.post(
            "/api/v1/documents/upload",
            files=files,
            data={"title": "Invalid DOCX package", "doc_type": "job_description"},
            headers=self.auth_headers_a,
        )
        self.assertEqual(res.status_code, 422)
        self.assertIn("missing required [Content_Types].xml", res.json()["detail"])

        # 4. Empty file upload (0 bytes) -> 400 Bad Request
        files = {"file": ("empty.pdf", b"", "application/pdf")}
        res = self.client.post(
            "/api/v1/documents/upload",
            files=files,
            data={"title": "Empty PDF", "doc_type": "resume"},
            headers=self.auth_headers_a,
        )
        self.assertEqual(res.status_code, 400)

    def test_notes_ingestion_and_sanitization(self):
        """Ingests raw text notes, sanitizes dangerous characters, and processes text."""
        # Content with untrusted control codes and null bytes
        untrusted_text = "Requirements:\n1. 5+ years Python\x00\x07 experience.\n2. Knowledge of RLS & Storage.\n"
        payload = {
            "title": "Interview Prep Notes",
            "content": untrusted_text,
            "doc_type": "notes",
        }

        res = self.client.post("/api/v1/documents/notes", json=payload, headers=self.auth_headers_a)
        self.assertEqual(res.status_code, 202)
        doc = res.json()
        doc_id = doc["id"]
        self.assertEqual(doc["user_id"], self.user_a_id)
        self.assertEqual(doc["file_type"], "notes")
        self.assertEqual(doc["status"], "pending")
        self.assertIsNotNone(doc["file_hash"])

        # Fetch document and verify processed text
        get_res = self.client.get(f"/api/v1/documents/{doc_id}", headers=self.auth_headers_a)
        self.assertEqual(get_res.status_code, 200)
        processed = get_res.json()
        self.assertEqual(processed["status"], "completed")
        self.assertNotIn("\x00", processed["extracted_text"])
        self.assertIn("5+ years Python experience", processed["extracted_text"])
        self.assertGreater(processed["metadata"]["word_count"], 0)

    def test_valid_pdf_and_docx_ingestion(self):
        """Uploads valid PDF and DOCX, extracts text, and preserves metadata."""
        # 1. Valid PDF upload
        pdf_bytes = create_minimal_pdf_bytes("Staff Engineer Resume")
        files = {"file": ("my_resume.pdf", pdf_bytes, "application/pdf")}
        pdf_res = self.client.post(
            "/api/v1/documents/upload",
            files=files,
            data={"title": "My Official Resume", "doc_type": "resume"},
            headers=self.auth_headers_a,
        )
        self.assertEqual(pdf_res.status_code, 202)
        pdf_doc = pdf_res.json()
        self.assertEqual(pdf_doc["file_type"], "pdf")
        self.assertEqual(pdf_doc["doc_type"], "resume")
        self.assertEqual(pdf_doc["status"], "pending")
        self.assertIn("user-uuid-1111", pdf_doc["storage_path"])

        # Fetch processed document
        get_pdf = self.client.get(f"/api/v1/documents/{pdf_doc['id']}", headers=self.auth_headers_a)
        self.assertEqual(get_pdf.status_code, 200)
        completed_pdf = get_pdf.json()
        self.assertEqual(completed_pdf["status"], "completed")
        self.assertEqual(completed_pdf["metadata"]["page_count"], 1)

        # 2. Valid DOCX upload
        docx_bytes = create_minimal_docx_bytes(
            paragraphs=["Lead AI Architect", "Expertise in distributed systems"],
            tables=[["Skill", "Level"], ["FastAPI", "Expert"]]
        )
        files = {"file": ("job_spec.docx", docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
        docx_res = self.client.post(
            "/api/v1/documents/upload",
            files=files,
            data={"title": "Backend Spec", "doc_type": "job_description"},
            headers=self.auth_headers_a,
        )
        self.assertEqual(docx_res.status_code, 202)
        docx_doc = docx_res.json()
        self.assertEqual(docx_doc["file_type"], "docx")
        self.assertEqual(docx_doc["status"], "pending")

        # Fetch processed DOCX
        get_docx = self.client.get(f"/api/v1/documents/{docx_doc['id']}", headers=self.auth_headers_a)
        self.assertEqual(get_docx.status_code, 200)
        completed_docx = get_docx.json()
        self.assertEqual(completed_docx["status"], "completed")
        self.assertIn("Lead AI Architect", completed_docx["extracted_text"])
        self.assertIn("FastAPI | Expert", completed_docx["extracted_text"])
        self.assertGreaterEqual(completed_docx["metadata"]["paragraph_count"], 2)
        self.assertGreaterEqual(completed_docx["metadata"]["table_count"], 1)

    def test_cross_user_isolation_and_ownership(self):
        """Enforces that User B cannot read, download, retry, or delete User A's document."""
        # Create document owned by User A
        notes_payload = {"title": "Confidential Salary Notes", "content": "Secret target: 200k", "doc_type": "notes"}
        res = self.client.post("/api/v1/documents/notes", json=notes_payload, headers=self.auth_headers_a)
        doc_id = res.json()["id"]

        # User B attempts to access User A's document -> 403 Forbidden
        get_res = self.client.get(f"/api/v1/documents/{doc_id}", headers=self.auth_headers_b)
        self.assertEqual(get_res.status_code, 403)
        self.assertIn("do not own this document", get_res.json()["detail"])

        # User B attempts to get status -> 403 Forbidden
        status_res = self.client.get(f"/api/v1/documents/{doc_id}/status", headers=self.auth_headers_b)
        self.assertEqual(status_res.status_code, 403)

        # User B attempts to download / get signed URL -> 403 Forbidden
        dl_res = self.client.get(f"/api/v1/documents/{doc_id}/download", headers=self.auth_headers_b)
        self.assertEqual(dl_res.status_code, 403)

        # User B attempts to retry -> 403 Forbidden
        retry_res = self.client.post(f"/api/v1/documents/{doc_id}/retry", headers=self.auth_headers_b)
        self.assertEqual(retry_res.status_code, 403)

        # User B attempts to delete User A's document -> 403 Forbidden
        del_res = self.client.delete(f"/api/v1/documents/{doc_id}", headers=self.auth_headers_b)
        self.assertEqual(del_res.status_code, 403)

        # Verify User A's document list contains it, but User B's list does NOT
        list_a = self.client.get("/api/v1/documents", headers=self.auth_headers_a).json()
        list_b = self.client.get("/api/v1/documents", headers=self.auth_headers_b).json()
        self.assertTrue(any(d["id"] == doc_id for d in list_a["documents"]))
        self.assertFalse(any(d["id"] == doc_id for d in list_b["documents"]))

    def test_secure_deletion(self):
        """Deleting a document removes both the private storage artifact and database record."""
        pdf_bytes = create_minimal_pdf_bytes("Deletable Document")
        files = {"file": ("to_delete.pdf", pdf_bytes, "application/pdf")}
        upload_res = self.client.post(
            "/api/v1/documents/upload",
            files=files,
            data={"title": "To Delete", "doc_type": "resume"},
            headers=self.auth_headers_a,
        )
        doc = upload_res.json()
        doc_id = doc["id"]
        storage_path = doc["storage_path"]

        # Confirm file is present in storage
        loop = asyncio.new_event_loop()
        content_in_store = loop.run_until_complete(storage_service.download_file(storage_path))
        self.assertTrue(len(content_in_store) > 0)

        # Delete document as owner
        del_res = self.client.delete(f"/api/v1/documents/{doc_id}", headers=self.auth_headers_a)
        self.assertEqual(del_res.status_code, 200)

        # Verify document is gone from API
        get_res = self.client.get(f"/api/v1/documents/{doc_id}", headers=self.auth_headers_a)
        self.assertEqual(get_res.status_code, 404)

        # Verify physical file is gone from storage
        with self.assertRaises(FileNotFoundError):
            loop.run_until_complete(storage_service.download_file(storage_path))
        loop.close()

    def test_async_retries_and_failure_handling(self):
        """Simulates extraction failures and verifies retry tracking and eventual FAILED state."""
        loop = asyncio.new_event_loop()

        # Create a document record pointing to a non-existent storage path to trigger processing error
        fake_id = "failing-doc-uuid"
        record = {
            "id": fake_id,
            "user_id": self.user_a_id,
            "title": "Failing Document",
            "doc_type": "resume",
            "file_type": "pdf",
            "storage_path": "non_existent/storage/path.pdf",
            "file_size_bytes": 100,
            "status": "pending",
            "retry_count": 0,
            "max_retries": 2,
        }
        loop.run_until_complete(document_repository.create(record))

        # Use processor with fast delay
        processor = DocumentIngestionProcessor(max_retries=2, base_retry_delay=0.01)
        loop.run_until_complete(processor.process_document(fake_id))

        # Verify document is marked as FAILED with retry count and error message
        updated = loop.run_until_complete(document_repository.get_by_id(fake_id))
        self.assertIsNotNone(updated)
        self.assertEqual(updated.status, ProcessingStatus.FAILED)
        self.assertEqual(updated.retry_count, 2)
        self.assertIn("Processing failed after 2 retries", updated.error_message)

        # Test manual retry API
        res = self.client.post(f"/api/v1/documents/{fake_id}/retry", headers=self.auth_headers_a)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], "pending")

        # After background task runs, verify it failed again because file does not exist
        failed_again = self.client.get(f"/api/v1/documents/{fake_id}", headers=self.auth_headers_a)
        self.assertEqual(failed_again.status_code, 200)
        self.assertEqual(failed_again.json()["status"], "failed")

        loop.close()


if __name__ == "__main__":
    unittest.main()
