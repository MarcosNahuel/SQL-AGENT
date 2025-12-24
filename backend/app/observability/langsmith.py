"""
LangSmith Observability Module

Provides:
- Centralized LangSmith configuration
- Custom callbacks for each agent/node
- Trace context management
- Performance metrics

Based on LangSmith docs:
https://docs.smith.langchain.com/
"""
import os
import time
from typing import Optional, Dict, Any, List
from datetime import datetime
from functools import wraps
from contextlib import contextmanager
import uuid

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult


class SQLAgentCallbackHandler(BaseCallbackHandler):
    """
    Custom callback handler for SQL-Agent.

    Tracks:
    - LLM calls and tokens
    - Agent steps
    - Errors and retries
    - Performance metrics
    """

    def __init__(
        self,
        trace_id: Optional[str] = None,
        node_name: Optional[str] = None,
        user_id: Optional[str] = None
    ):
        super().__init__()
        self.trace_id = trace_id or str(uuid.uuid4())[:8]
        self.node_name = node_name or "unknown"
        self.user_id = user_id
        self.start_time: Optional[float] = None
        self.metrics: Dict[str, Any] = {
            "llm_calls": 0,
            "total_tokens": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "errors": 0,
            "retries": 0
        }

    def on_llm_start(
        self,
        serialized: Dict[str, Any],
        prompts: List[str],
        **kwargs
    ) -> None:
        """Called when LLM starts"""
        self.start_time = time.time()
        model = serialized.get("name", "unknown")
        print(f"[LangSmith] [{self.trace_id}] LLM start: {model} in {self.node_name}")

    def on_llm_end(self, response: LLMResult, **kwargs) -> None:
        """Called when LLM completes"""
        duration = (time.time() - self.start_time) * 1000 if self.start_time else 0
        self.metrics["llm_calls"] += 1

        # Extract token usage if available
        if response.llm_output:
            usage = response.llm_output.get("token_usage", {})
            self.metrics["prompt_tokens"] += usage.get("prompt_tokens", 0)
            self.metrics["completion_tokens"] += usage.get("completion_tokens", 0)
            self.metrics["total_tokens"] += usage.get("total_tokens", 0)

        print(f"[LangSmith] [{self.trace_id}] LLM end: {duration:.0f}ms in {self.node_name}")

    def on_llm_error(self, error: Exception, **kwargs) -> None:
        """Called on LLM error"""
        self.metrics["errors"] += 1
        print(f"[LangSmith] [{self.trace_id}] LLM error in {self.node_name}: {error}")

    def on_retry(self, *args, **kwargs) -> None:
        """Called on retry"""
        self.metrics["retries"] += 1
        print(f"[LangSmith] [{self.trace_id}] Retry #{self.metrics['retries']} in {self.node_name}")


class TraceContext:
    """
    Context manager for tracing operations.

    Usage:
        with TraceContext("DataAgent", trace_id="abc123") as ctx:
            # operations...
            ctx.log_event("query_executed", {"rows": 100})
    """

    def __init__(
        self,
        name: str,
        trace_id: Optional[str] = None,
        parent_id: Optional[str] = None,
        metadata: Optional[Dict] = None
    ):
        self.name = name
        self.trace_id = trace_id or str(uuid.uuid4())[:8]
        self.parent_id = parent_id
        self.span_id = str(uuid.uuid4())[:8]
        self.metadata = metadata or {}
        self.events: List[Dict[str, Any]] = []
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None

    def __enter__(self) -> "TraceContext":
        self.start_time = time.time()
        print(f"[Trace] [{self.trace_id}] START {self.name}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.end_time = time.time()
        duration = (self.end_time - self.start_time) * 1000

        status = "error" if exc_type else "ok"
        print(f"[Trace] [{self.trace_id}] END {self.name}: {duration:.0f}ms ({status})")

        # Log final metrics
        self._log_to_langsmith()

    def log_event(self, event_name: str, data: Optional[Dict] = None) -> None:
        """Log an event within this trace"""
        event = {
            "name": event_name,
            "timestamp": datetime.utcnow().isoformat(),
            "data": data or {}
        }
        self.events.append(event)
        print(f"[Trace] [{self.trace_id}] EVENT {event_name}")

    def _log_to_langsmith(self) -> None:
        """Send trace data to LangSmith (if enabled)"""
        if not os.getenv("LANGCHAIN_TRACING_V2", "").lower() == "true":
            return

        # LangSmith automatically captures traces through callbacks
        # This is for additional custom logging
        pass


@contextmanager
def trace_node(node_name: str, trace_id: Optional[str] = None):
    """
    Context manager for tracing a node execution.

    Usage:
        with trace_node("DataAgent", trace_id) as ctx:
            result = execute_node()
            ctx.log_event("completed", {"rows": len(result)})
    """
    ctx = TraceContext(node_name, trace_id)
    try:
        yield ctx.__enter__()
    finally:
        ctx.__exit__(None, None, None)


def traced(node_name: str):
    """
    Decorator for tracing function execution.

    Usage:
        @traced("DataAgent")
        def run_data_agent(state):
            ...
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Try to extract trace_id from state
            trace_id = None
            if args and isinstance(args[0], dict):
                trace_id = args[0].get("trace_id")

            with trace_node(node_name, trace_id) as ctx:
                result = func(*args, **kwargs)
                if isinstance(result, dict) and result.get("error"):
                    ctx.log_event("error", {"message": result["error"]})
                return result

        return wrapper
    return decorator


def get_langsmith_callback(
    trace_id: Optional[str] = None,
    node_name: Optional[str] = None
) -> SQLAgentCallbackHandler:
    """Factory function for creating callback handlers"""
    return SQLAgentCallbackHandler(
        trace_id=trace_id,
        node_name=node_name
    )


def configure_langsmith() -> bool:
    """
    Configure LangSmith from environment variables.

    Required env vars:
    - LANGCHAIN_TRACING_V2=true
    - LANGSMITH_API_KEY or LANGCHAIN_API_KEY
    - LANGCHAIN_PROJECT (optional)

    Returns True if LangSmith is properly configured.
    """
    tracing_enabled = os.getenv("LANGCHAIN_TRACING_V2", "").lower() == "true"
    api_key = os.getenv("LANGSMITH_API_KEY") or os.getenv("LANGCHAIN_API_KEY")
    project = os.getenv("LANGCHAIN_PROJECT", "sql-agent")

    if tracing_enabled and api_key:
        # Ensure env vars are set for LangChain to pick up
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_API_KEY"] = api_key
        os.environ["LANGCHAIN_PROJECT"] = project
        print(f"[LangSmith] Configured for project: {project}")
        return True
    else:
        print("[LangSmith] Not configured (missing LANGCHAIN_TRACING_V2 or API key)")
        return False


# Auto-configure on import
_langsmith_configured = configure_langsmith()


def is_langsmith_enabled() -> bool:
    """Check if LangSmith is enabled"""
    return _langsmith_configured
