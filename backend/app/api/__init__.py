"""API Module - Contains versioned API endpoints"""
from .v1_chat import router as v1_chat_router

__all__ = ["v1_chat_router"]
