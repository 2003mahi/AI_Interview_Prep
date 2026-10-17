import os
from pydantic import BaseSettings, Field
import json

class Settings(BaseSettings):
    # PostgreSQL URL for Supabase (asyncpg driver)
    DATABASE_URL: str = Field(..., env="DATABASE_URL")
    # OpenAI API key for embeddings and LLM
    OPENAI_API_KEY: str = Field(..., env="OPENAI_API_KEY")
    # Mapping of API keys to user identifiers (JSON string)
    API_KEYS: str = Field("{}", env="API_KEYS")

    @property
    def api_key_map(self) -> dict:
        try:
            return json.loads(self.API_KEYS)
        except json.JSONDecodeError:
            return {}

settings = Settings()
