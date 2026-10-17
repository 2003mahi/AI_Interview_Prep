from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from typing import List, Optional

from ..dependencies import get_user_id, get_db
from ..models.document import Document
from ..utils import chunk_text, embed_text
from ..config import settings

router = APIRouter()

@router.post("/ingest", status_code=201)
async def ingest_documents(
    files: List[UploadFile] = File(...),
    metadata: Optional[dict] = None,
    user_id: str = Depends(get_user_id),
    db: "AsyncSession" = Depends(get_db),
):
    """Ingest one or more text files.
    Each file is chunked, embeddings are computed, and rows are inserted into the
    `documents` table with the supplied `metadata` (if any) and the caller's
    `user_id` for isolation.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    async with db.begin():
        for upload in files:
            content_bytes = await upload.read()
            try:
                text = content_bytes.decode("utf-8")
            except UnicodeDecodeError:
                raise HTTPException(status_code=400, detail=f"File {upload.filename} is not UTF‑8 text")

            chunks = chunk_text(text)
            for idx, chunk in enumerate(chunks):
                embedding = embed_text(chunk)
                doc = Document(
                    user_id=user_id,
                    content=chunk,
                    metadata=metadata,
                    embedding=embedding,
                    chunk_index=idx,
                )
                db.add(doc)
    return {"detail": f"Ingested {len(files)} file(s) with total {len(chunks)} chunks"}
