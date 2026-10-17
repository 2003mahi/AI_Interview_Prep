"""User model for API key based isolation."""
import uuid
from sqlalchemy import Column, String
from sqlalchemy.dialects.postgresql import UUID
from .db import Base

class User(Base):
    __tablename__ = "users"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String, unique=True, nullable=False)  # logical user identifier
    api_key = Column(String, unique=True, nullable=False)
"
