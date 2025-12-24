"""
Centralized Configuration for SQL-Agent Multi-Agent System

Uses pydantic-settings for validation and environment variable loading.
"""
import os
from typing import Optional, Literal
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    # === Supabase ===
    supabase_url: str = Field(..., alias="SUPABASE_URL")
    supabase_anon_key: str = Field(..., alias="SUPABASE_ANON_KEY")
    supabase_service_key: str = Field(..., alias="SUPABASE_SERVICE_KEY")

    # Postgres direct connection (optional, for checkpointer)
    postgres_url: Optional[str] = Field(None, alias="POSTGRES_URL")

    # === LLM ===
    gemini_api_key: str = Field(..., alias="GEMINI_API_KEY")
    gemini_model: str = Field("gemini-3-flash-preview", alias="GEMINI_MODEL")

    # === n8n RAG ===
    n8n_base_url: str = Field(
        "https://horsepower-n8n.e5l6dk.easypanel.host",
        alias="N8N_BASE_URL"
    )
    n8n_rag_webhook_path: str = Field(
        "/webhook/rag-products",
        alias="N8N_RAG_WEBHOOK_PATH"
    )

    # === LangSmith ===
    langchain_tracing_v2: bool = Field(True, alias="LANGCHAIN_TRACING_V2")
    langchain_project: str = Field("sql-agent", alias="LANGCHAIN_PROJECT")
    langchain_api_key: Optional[str] = Field(None, alias="LANGCHAIN_API_KEY")
    langsmith_api_key: Optional[str] = Field(None, alias="LANGSMITH_API_KEY")

    # === Server ===
    port: int = Field(8000, alias="PORT")
    frontend_url: str = Field("http://localhost:3000", alias="FRONTEND_URL")
    demo_mode: bool = Field(False, alias="DEMO_MODE")

    # === Memory ===
    memory_backend: Literal["postgres", "sqlite", "memory"] = Field(
        "memory",
        alias="MEMORY_BACKEND"
    )
    sqlite_path: str = Field("./data/langgraph.db", alias="SQLITE_PATH")
    memory_ttl_hours: int = Field(24 * 7, alias="MEMORY_TTL_HOURS")  # 1 week

    # === Timeouts ===
    llm_timeout_seconds: int = Field(60, alias="LLM_TIMEOUT_SECONDS")
    db_timeout_seconds: int = Field(30, alias="DB_TIMEOUT_SECONDS")
    rag_timeout_seconds: int = Field(10, alias="RAG_TIMEOUT_SECONDS")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

    @field_validator("postgres_url", mode="before")
    @classmethod
    def build_postgres_url(cls, v, info):
        """Build Postgres URL from Supabase URL if not provided"""
        if v:
            return v
        # Try to build from Supabase URL (requires port 5432 access)
        # This won't work on EasyPanel without direct DB access
        return None

    @property
    def n8n_rag_url(self) -> str:
        """Full URL for RAG webhook"""
        return f"{self.n8n_base_url}{self.n8n_rag_webhook_path}"

    @property
    def effective_langsmith_key(self) -> Optional[str]:
        """Get the effective LangSmith API key"""
        return self.langsmith_api_key or self.langchain_api_key

    @property
    def can_use_postgres_checkpointer(self) -> bool:
        """Check if we can use PostgresSaver"""
        return self.postgres_url is not None


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()


# Convenience exports
settings = get_settings()
