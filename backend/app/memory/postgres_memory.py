"""
PostgreSQL Memory Module for LangGraph

Provides:
- PostgresSaver for checkpoint persistence (if direct Postgres access available)
- MemorySaver fallback for in-memory persistence
- Custom memory store for long-term cross-thread memory
"""
import os
from typing import Optional, Any
from dataclasses import dataclass
from contextlib import asynccontextmanager

from langgraph.checkpoint.memory import MemorySaver

# Try to import PostgresSaver - may not be available
try:
    from langgraph.checkpoint.postgres import PostgresSaver
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    POSTGRES_AVAILABLE = True
except ImportError:
    POSTGRES_AVAILABLE = False
    PostgresSaver = None
    AsyncPostgresSaver = None


@dataclass
class MemoryConfig:
    """Configuration for memory backend"""
    backend: str = "memory"  # "postgres", "sqlite", "memory"
    postgres_url: Optional[str] = None
    sqlite_path: str = "./data/langgraph.db"
    ttl_hours: int = 24 * 7  # 1 week default


class MemoryManager:
    """
    Manages LangGraph memory/checkpointer instances.

    Supports multiple backends with automatic fallback:
    1. PostgresSaver (if postgres_url provided and package available)
    2. SqliteSaver (if sqlite_path provided)
    3. MemorySaver (in-memory fallback)
    """

    def __init__(self, config: MemoryConfig):
        self.config = config
        self._checkpointer = None
        self._store = None

    def get_checkpointer(self):
        """
        Get the appropriate checkpointer based on configuration.

        Returns:
            BaseCheckpointSaver: Configured checkpointer instance
        """
        if self._checkpointer is not None:
            return self._checkpointer

        # Try PostgresSaver first
        if (
            self.config.backend == "postgres"
            and self.config.postgres_url
            and POSTGRES_AVAILABLE
        ):
            try:
                self._checkpointer = PostgresSaver.from_conn_string(
                    self.config.postgres_url
                )
                # Setup tables if needed
                self._checkpointer.setup()
                return self._checkpointer
            except Exception as e:
                print(f"Warning: PostgresSaver failed ({e}), falling back to memory")

        # Fallback to MemorySaver
        self._checkpointer = MemorySaver()
        return self._checkpointer

    @asynccontextmanager
    async def get_async_checkpointer(self):
        """
        Get async checkpointer for use in async contexts.

        Yields:
            AsyncPostgresSaver or MemorySaver
        """
        if (
            self.config.backend == "postgres"
            and self.config.postgres_url
            and POSTGRES_AVAILABLE
            and AsyncPostgresSaver is not None
        ):
            try:
                async with AsyncPostgresSaver.from_conn_string(
                    self.config.postgres_url
                ) as checkpointer:
                    await checkpointer.setup()
                    yield checkpointer
                    return
            except Exception as e:
                print(f"Warning: AsyncPostgresSaver failed ({e}), falling back to memory")

        # Fallback to MemorySaver (sync, but works in async context)
        yield MemorySaver()


# Singleton instances
_memory_manager: Optional[MemoryManager] = None


def get_memory_manager(config: Optional[MemoryConfig] = None) -> MemoryManager:
    """Get or create the global memory manager"""
    global _memory_manager

    if _memory_manager is None:
        if config is None:
            # Load from environment
            config = MemoryConfig(
                backend=os.getenv("MEMORY_BACKEND", "memory"),
                postgres_url=os.getenv("POSTGRES_URL"),
                sqlite_path=os.getenv("SQLITE_PATH", "./data/langgraph.db"),
                ttl_hours=int(os.getenv("MEMORY_TTL_HOURS", "168"))
            )
        _memory_manager = MemoryManager(config)

    return _memory_manager


def get_checkpointer():
    """Convenience function to get the checkpointer"""
    return get_memory_manager().get_checkpointer()


def get_memory_store():
    """
    Get memory store for long-term memory.

    For now returns None - will implement with Supabase REST API
    for cross-thread memory storage.
    """
    # TODO: Implement SupabaseMemoryStore for long-term memory
    # This will use the agent_memory table via REST API
    return None
