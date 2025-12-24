"""
AsyncPostgresSaver Checkpointer for LangGraph v2

Implements persistent state management using PostgreSQL for:
- Thread-based conversation persistence
- Time-travel debugging (checkpoint history)
- Crash recovery and session resumption

Based on: langgraph-checkpoint-postgres
"""
import os
import sys
from typing import Optional
from contextlib import asynccontextmanager

# Windows compatibility: psycopg3 async requires SelectorEventLoop
IS_WINDOWS = sys.platform == "win32"

# Try to import postgres checkpointer
POSTGRES_AVAILABLE = False
AsyncPostgresSaver = None
AsyncConnectionPool = None

if not IS_WINDOWS:  # Only try PostgreSQL on non-Windows platforms
    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        from psycopg_pool import AsyncConnectionPool
        POSTGRES_AVAILABLE = True
    except ImportError:
        pass
else:
    print("[Checkpointer] Windows detected - PostgreSQL async not supported, using MemorySaver")

# Fallback to memory saver
from langgraph.checkpoint.memory import MemorySaver


class CheckpointerManager:
    """
    Manages checkpointer lifecycle for LangGraph.

    Supports:
    - AsyncPostgresSaver for production (persistent)
    - MemorySaver for development (in-memory)
    """

    def __init__(self):
        self._pool: Optional[AsyncConnectionPool] = None
        self._checkpointer = None
        self._is_postgres = False

    @property
    def checkpointer(self):
        """Get the current checkpointer instance"""
        return self._checkpointer

    @property
    def is_postgres(self) -> bool:
        """Check if using PostgreSQL backend"""
        return self._is_postgres

    async def initialize(self, postgres_url: Optional[str] = None) -> None:
        """
        Initialize the checkpointer.

        Args:
            postgres_url: PostgreSQL connection string. If None, uses MemorySaver.
        """
        # Get URL from env if not provided
        if postgres_url is None:
            postgres_url = os.getenv("POSTGRES_URL")

        # Try PostgreSQL first
        if postgres_url and POSTGRES_AVAILABLE:
            try:
                print(f"[Checkpointer] Connecting to PostgreSQL...")

                # Create connection pool
                self._pool = AsyncConnectionPool(
                    conninfo=postgres_url,
                    min_size=2,
                    max_size=10,
                    open=False  # Don't open immediately
                )
                await self._pool.open()

                # Create checkpointer
                self._checkpointer = AsyncPostgresSaver(self._pool)

                # Setup tables (creates if not exist)
                await self._checkpointer.setup()

                self._is_postgres = True
                print("[Checkpointer] PostgreSQL checkpointer initialized successfully")
                return

            except Exception as e:
                print(f"[Checkpointer] PostgreSQL failed: {e}")
                print("[Checkpointer] Falling back to MemorySaver...")
                # Cleanup failed connection
                if self._pool:
                    try:
                        await self._pool.close()
                    except:
                        pass
                    self._pool = None

        # Fallback to MemorySaver
        if not POSTGRES_AVAILABLE:
            print("[Checkpointer] langgraph-checkpoint-postgres not installed")

        self._checkpointer = MemorySaver()
        self._is_postgres = False
        print("[Checkpointer] Using in-memory checkpointer (MemorySaver)")

    async def close(self) -> None:
        """Close the checkpointer and release resources"""
        if self._pool:
            try:
                await self._pool.close()
                print("[Checkpointer] PostgreSQL connection pool closed")
            except Exception as e:
                print(f"[Checkpointer] Error closing pool: {e}")
            self._pool = None

        self._checkpointer = None
        self._is_postgres = False

    def get_config(self, thread_id: str, checkpoint_ns: str = "") -> dict:
        """
        Get configuration dict for graph invocation.

        Args:
            thread_id: Unique conversation/session ID
            checkpoint_ns: Optional namespace for checkpoints

        Returns:
            Config dict for graph.invoke() or graph.astream()
        """
        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns
            }
        }


# Global singleton instance
_manager: Optional[CheckpointerManager] = None


def get_checkpointer_manager() -> CheckpointerManager:
    """Get or create the global checkpointer manager"""
    global _manager
    if _manager is None:
        _manager = CheckpointerManager()
    return _manager


async def init_checkpointer(postgres_url: Optional[str] = None) -> CheckpointerManager:
    """Initialize the global checkpointer"""
    manager = get_checkpointer_manager()
    await manager.initialize(postgres_url)
    return manager


async def close_checkpointer() -> None:
    """Close the global checkpointer"""
    global _manager
    if _manager:
        await _manager.close()
        _manager = None


@asynccontextmanager
async def checkpointer_lifespan(postgres_url: Optional[str] = None):
    """
    Context manager for checkpointer lifecycle.

    Usage:
        async with checkpointer_lifespan() as manager:
            graph = workflow.compile(checkpointer=manager.checkpointer)
    """
    manager = await init_checkpointer(postgres_url)
    try:
        yield manager
    finally:
        await close_checkpointer()
