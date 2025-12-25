"""
PostgresSaver Checkpointer for LangGraph v2

Implements persistent state management using PostgreSQL for:
- Thread-based conversation persistence
- Time-travel debugging (checkpoint history)
- Crash recovery and session resumption

Based on: langgraph-checkpoint-postgres

Supports both sync and async modes:
- Sync mode: Works on all platforms including Windows
- Async mode: Requires Unix-like platforms
"""
import os
import sys
from typing import Optional
from contextlib import asynccontextmanager

# Windows compatibility: psycopg3 async has issues on Windows
IS_WINDOWS = sys.platform == "win32"

# Try to import postgres checkpointers (sync and async)
POSTGRES_SYNC_AVAILABLE = False
POSTGRES_ASYNC_AVAILABLE = False
PostgresSaver = None
AsyncPostgresSaver = None
ConnectionPool = None
AsyncConnectionPool = None

# Try sync PostgresSaver first (works on all platforms)
try:
    from langgraph.checkpoint.postgres import PostgresSaver
    from psycopg_pool import ConnectionPool
    POSTGRES_SYNC_AVAILABLE = True
    print("[Checkpointer] PostgresSaver (sync) available")
except ImportError as e:
    print(f"[Checkpointer] PostgresSaver (sync) not available: {e}")

# Try async PostgresSaver (Unix only)
if not IS_WINDOWS:
    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        from psycopg_pool import AsyncConnectionPool
        POSTGRES_ASYNC_AVAILABLE = True
        print("[Checkpointer] AsyncPostgresSaver available")
    except ImportError as e:
        print(f"[Checkpointer] AsyncPostgresSaver not available: {e}")
else:
    print("[Checkpointer] Windows detected - using sync PostgresSaver")

# Fallback to memory saver
from langgraph.checkpoint.memory import MemorySaver


class CheckpointerManager:
    """
    Manages checkpointer lifecycle for LangGraph.

    Supports:
    - PostgresSaver (sync) for all platforms including Windows
    - AsyncPostgresSaver for Unix platforms (optional)
    - MemorySaver for development (in-memory fallback)
    """

    def __init__(self):
        self._sync_pool: Optional[ConnectionPool] = None
        self._async_pool: Optional[AsyncConnectionPool] = None
        self._checkpointer = None
        self._is_postgres = False
        self._is_async = False

    @property
    def checkpointer(self):
        """Get the current checkpointer instance"""
        return self._checkpointer

    @property
    def is_postgres(self) -> bool:
        """Check if using PostgreSQL backend"""
        return self._is_postgres

    @property
    def is_async(self) -> bool:
        """Check if using async checkpointer"""
        return self._is_async

    def initialize_sync(self, postgres_url: Optional[str] = None) -> None:
        """
        Initialize the checkpointer synchronously (works on Windows).

        Args:
            postgres_url: PostgreSQL connection string. If None, uses MemorySaver.
        """
        # Get URL from env if not provided
        if postgres_url is None:
            postgres_url = os.getenv("POSTGRES_URL")

        # Try sync PostgreSQL first (works on all platforms)
        if postgres_url and POSTGRES_SYNC_AVAILABLE:
            try:
                print(f"[Checkpointer] Connecting to PostgreSQL (sync)...")

                # Create sync connection pool
                self._sync_pool = ConnectionPool(
                    conninfo=postgres_url,
                    min_size=2,
                    max_size=10,
                    open=True
                )

                # Create sync checkpointer
                self._checkpointer = PostgresSaver(self._sync_pool)

                # Setup tables (creates if not exist)
                self._checkpointer.setup()

                self._is_postgres = True
                self._is_async = False
                print("[Checkpointer] PostgreSQL (sync) checkpointer initialized successfully")
                return

            except Exception as e:
                print(f"[Checkpointer] PostgreSQL (sync) failed: {e}")
                print("[Checkpointer] Falling back to MemorySaver...")
                # Cleanup failed connection
                if self._sync_pool:
                    try:
                        self._sync_pool.close()
                    except:
                        pass
                    self._sync_pool = None

        # Fallback to MemorySaver
        if not POSTGRES_SYNC_AVAILABLE:
            print("[Checkpointer] langgraph-checkpoint-postgres not installed")

        self._checkpointer = MemorySaver()
        self._is_postgres = False
        self._is_async = False
        print("[Checkpointer] Using in-memory checkpointer (MemorySaver)")

    async def initialize(self, postgres_url: Optional[str] = None) -> None:
        """
        Initialize the checkpointer asynchronously.
        Falls back to sync mode on Windows or if async is not available.

        Args:
            postgres_url: PostgreSQL connection string. If None, uses MemorySaver.
        """
        # Get URL from env if not provided
        if postgres_url is None:
            postgres_url = os.getenv("POSTGRES_URL")

        # Try async PostgreSQL on Unix platforms
        if postgres_url and POSTGRES_ASYNC_AVAILABLE and not IS_WINDOWS:
            try:
                print(f"[Checkpointer] Connecting to PostgreSQL (async)...")

                # Create async connection pool
                self._async_pool = AsyncConnectionPool(
                    conninfo=postgres_url,
                    min_size=2,
                    max_size=10,
                    open=False
                )
                await self._async_pool.open()

                # Create async checkpointer
                self._checkpointer = AsyncPostgresSaver(self._async_pool)

                # Setup tables (creates if not exist)
                await self._checkpointer.setup()

                self._is_postgres = True
                self._is_async = True
                print("[Checkpointer] PostgreSQL (async) checkpointer initialized successfully")
                return

            except Exception as e:
                print(f"[Checkpointer] PostgreSQL (async) failed: {e}")
                # Cleanup failed connection
                if self._async_pool:
                    try:
                        await self._async_pool.close()
                    except:
                        pass
                    self._async_pool = None

        # Fall back to sync initialization
        print("[Checkpointer] Falling back to sync initialization...")
        self.initialize_sync(postgres_url)

    def close_sync(self) -> None:
        """Close the checkpointer synchronously"""
        if self._sync_pool:
            try:
                self._sync_pool.close()
                print("[Checkpointer] PostgreSQL (sync) connection pool closed")
            except Exception as e:
                print(f"[Checkpointer] Error closing sync pool: {e}")
            self._sync_pool = None

        self._checkpointer = None
        self._is_postgres = False
        self._is_async = False

    async def close(self) -> None:
        """Close the checkpointer and release resources"""
        if self._async_pool:
            try:
                await self._async_pool.close()
                print("[Checkpointer] PostgreSQL (async) connection pool closed")
            except Exception as e:
                print(f"[Checkpointer] Error closing async pool: {e}")
            self._async_pool = None

        # Also close sync pool if exists
        self.close_sync()

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
