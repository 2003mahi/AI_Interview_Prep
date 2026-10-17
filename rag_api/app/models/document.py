import uuid
from sqlalchemy import Column, String, Integer, LargeBinary, JSON
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from pgvector.sqlalchemy import Vector
from .db import Base

class Document(Base):
    __tablename__ = "documents"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String, nullable=False, index=True)
    content = Column(String, nullable=False)
    metadata = Column(JSON, nullable=True)
    embedding = Column(Vector(1536), nullable=False)  # Assuming OpenAI ada-002 size
    # optional chunk index if needed
    chunk_index = Column(Integer, nullable=True)
