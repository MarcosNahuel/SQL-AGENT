"""
Structured Logging Module for SQL-Agent

Provides consistent logging format across all components:
[NODO] trace_id | status | message | detail

Supports:
- LOG_LEVEL env var (DEBUG, INFO, WARNING, ERROR)
- LOG_FORMAT env var (json, text)
- Integration with LangSmith tracing
"""
import os
import sys
import json
import logging
from datetime import datetime
from typing import Optional, Any, Dict
from enum import Enum


class LogLevel(Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


# Map string levels to logging constants
LEVEL_MAP = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
}


class StructuredFormatter(logging.Formatter):
    """Custom formatter for structured logs"""

    def __init__(self, use_json: bool = False):
        super().__init__()
        self.use_json = use_json

    def format(self, record: logging.LogRecord) -> str:
        # Extract custom attributes
        trace_id = getattr(record, 'trace_id', 'unknown')
        status = getattr(record, 'status', 'INFO')
        node = getattr(record, 'node', record.name.split('.')[-1])
        detail = getattr(record, 'detail', None)

        timestamp = datetime.utcnow().isoformat()

        if self.use_json:
            log_data = {
                "ts": timestamp,
                "node": node,
                "trace_id": trace_id,
                "status": status,
                "message": record.getMessage(),
                "level": record.levelname,
            }
            if detail:
                log_data["detail"] = detail
            if record.exc_info:
                log_data["exception"] = self.formatException(record.exc_info)
            return json.dumps(log_data)
        else:
            # Text format: [NODE] trace_id | status | message | detail
            base = f"[{node}] {trace_id} | {status} | {record.getMessage()}"
            if detail:
                detail_str = json.dumps(detail) if isinstance(detail, dict) else str(detail)
                base += f" | {detail_str}"
            return base


class StructuredLogger:
    """Logger with structured output for SQL-Agent components"""

    def __init__(self, node_name: str):
        self.node_name = node_name
        self._logger = logging.getLogger(f"sql-agent.{node_name}")

    def _log(
        self,
        level: int,
        trace_id: str,
        status: str,
        message: str,
        detail: Optional[Dict] = None,
        exc_info: bool = False
    ):
        """Internal log method with extra attributes"""
        extra = {
            'trace_id': trace_id,
            'status': status,
            'node': self.node_name,
            'detail': detail,
        }
        self._logger.log(level, message, extra=extra, exc_info=exc_info)

    def debug(self, trace_id: str, message: str, detail: Optional[Dict] = None):
        """Debug level log"""
        self._log(logging.DEBUG, trace_id, "DEBUG", message, detail)

    def info(self, trace_id: str, message: str, detail: Optional[Dict] = None):
        """Info level log"""
        self._log(logging.INFO, trace_id, "INFO", message, detail)

    def warning(self, trace_id: str, message: str, detail: Optional[Dict] = None):
        """Warning level log"""
        self._log(logging.WARNING, trace_id, "WARNING", message, detail)

    def error(self, trace_id: str, message: str, detail: Optional[Dict] = None, exc_info: bool = True):
        """Error level log with optional exception info"""
        self._log(logging.ERROR, trace_id, "ERROR", message, detail, exc_info=exc_info)

    def start(self, trace_id: str, message: str, detail: Optional[Dict] = None):
        """Log start of an operation"""
        self._log(logging.INFO, trace_id, "START", message, detail)

    def end(self, trace_id: str, message: str, detail: Optional[Dict] = None):
        """Log end of an operation"""
        self._log(logging.INFO, trace_id, "END", message, detail)

    def progress(self, trace_id: str, message: str, detail: Optional[Dict] = None):
        """Log progress of an operation"""
        self._log(logging.INFO, trace_id, "PROGRESS", message, detail)


# Global loggers cache
_loggers: Dict[str, StructuredLogger] = {}


def get_logger(node_name: str) -> StructuredLogger:
    """Get or create a structured logger for a node"""
    if node_name not in _loggers:
        _loggers[node_name] = StructuredLogger(node_name)
    return _loggers[node_name]


def configure_logging(
    level: Optional[str] = None,
    format_type: Optional[str] = None
) -> None:
    """
    Configure logging for the application.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR). Default from LOG_LEVEL env.
        format_type: Output format (json, text). Default from LOG_FORMAT env.
    """
    # Get settings from env or params
    log_level = level or os.getenv("LOG_LEVEL", "INFO").upper()
    log_format = format_type or os.getenv("LOG_FORMAT", "text").lower()

    # Map to logging level
    numeric_level = LEVEL_MAP.get(log_level, logging.INFO)

    # Create formatter
    use_json = log_format == "json"
    formatter = StructuredFormatter(use_json=use_json)

    # Configure root logger for sql-agent
    root_logger = logging.getLogger("sql-agent")
    root_logger.setLevel(numeric_level)

    # Remove existing handlers
    root_logger.handlers = []

    # Add stdout handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(numeric_level)
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)

    # Prevent propagation to root logger
    root_logger.propagate = False

    print(f"[Logger] Configured: level={log_level}, format={log_format}")


# Auto-configure on import if not already configured
_configured = False

def ensure_configured():
    """Ensure logging is configured (call once at startup)"""
    global _configured
    if not _configured:
        configure_logging()
        _configured = True
