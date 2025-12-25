"""
Chat Memory - Persistent conversation history using Supabase REST API

Stores and retrieves chat messages for conversation continuity.
"""
import os
import json
from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel
import httpx
from dotenv import load_dotenv

# Ensure env vars are loaded
load_dotenv()


class ChatMessage(BaseModel):
    """A single chat message"""
    role: str  # 'user', 'assistant', 'system'
    content: str
    metadata: Dict[str, Any] = {}
    created_at: Optional[datetime] = None


class SupabaseMemoryClient:
    """REST client for chat/agent memory tables"""

    def __init__(self):
        self.base_url = os.getenv("SUPABASE_URL", "").rstrip("/")
        self.api_key = os.getenv("SUPABASE_ANON_KEY", "")
        self.service_key = os.getenv("SUPABASE_SERVICE_KEY", self.api_key)

        self.headers = {
            "apikey": self.api_key,
            "Authorization": f"Bearer {self.service_key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }

        self.client = httpx.Client(timeout=10.0)
        self._available = bool(self.base_url and self.api_key)

    @property
    def is_available(self) -> bool:
        return self._available

    def insert(self, table: str, data: Dict) -> bool:
        """Insert a row into a table"""
        if not self._available:
            return False

        try:
            url = f"{self.base_url}/rest/v1/{table}"
            response = self.client.post(url, headers=self.headers, json=data)
            if response.status_code >= 400:
                print(f"[MemoryClient] Insert error: {response.status_code} - {response.text}")
                return False
            return True
        except Exception as e:
            print(f"[MemoryClient] Insert exception: {e}")
            return False

    def select(self, table: str, filters: Dict[str, str], select: str = "*",
               order: Optional[str] = None, limit: Optional[int] = None) -> List[Dict]:
        """Select rows from a table with filters"""
        if not self._available:
            return []

        try:
            params = {"select": select}
            params.update(filters)

            if order:
                params["order"] = order
            if limit:
                params["limit"] = str(limit)

            url = f"{self.base_url}/rest/v1/{table}"
            response = self.client.get(url, headers=self.headers, params=params)

            if response.status_code >= 400:
                print(f"[MemoryClient] Select error: {response.status_code} - {response.text}")
                return []

            return response.json() if response.text else []
        except Exception as e:
            print(f"[MemoryClient] Select exception: {e}")
            return []

    def upsert(self, table: str, data: Dict, on_conflict: str) -> bool:
        """Upsert a row into a table"""
        if not self._available:
            return False

        try:
            url = f"{self.base_url}/rest/v1/{table}"
            headers = {**self.headers, "Prefer": "resolution=merge-duplicates"}
            response = self.client.post(url, headers=headers, json=data)
            if response.status_code >= 400:
                print(f"[MemoryClient] Upsert error: {response.status_code} - {response.text}")
                return False
            return True
        except Exception as e:
            print(f"[MemoryClient] Upsert exception: {e}")
            return False


# Singleton client
_memory_client: Optional[SupabaseMemoryClient] = None

def get_memory_client() -> SupabaseMemoryClient:
    global _memory_client
    if _memory_client is None:
        _memory_client = SupabaseMemoryClient()
    return _memory_client


class ChatMemory:
    """
    Manages chat history persistence.

    Uses Supabase REST API for storage with fallback to in-memory.
    """

    def __init__(self, thread_id: str, user_id: Optional[str] = None):
        self.thread_id = thread_id
        self.user_id = user_id or "anonymous"
        self._messages: List[ChatMessage] = []
        self._client = get_memory_client()

    def load_history_sync(self, limit: int = 50) -> List[ChatMessage]:
        """Load chat history synchronously"""
        if not self._client.is_available:
            return self._messages

        try:
            rows = self._client.select(
                "chat_messages",
                filters={"thread_id": f"eq.{self.thread_id}"},
                order="created_at.asc",
                limit=limit
            )

            self._messages = [
                ChatMessage(
                    role=row["role"],
                    content=row["content"],
                    metadata=row.get("metadata", {}),
                    created_at=row.get("created_at")
                )
                for row in rows
            ]
            return self._messages

        except Exception as e:
            print(f"[ChatMemory] Error loading history: {e}")
            return self._messages

    async def load_history(self, limit: int = 50) -> List[ChatMessage]:
        """Load chat history (async wrapper)"""
        return self.load_history_sync(limit)

    def add_message_sync(self, role: str, content: str, metadata: Dict[str, Any] = None) -> ChatMessage:
        """Add a message synchronously"""
        msg = ChatMessage(
            role=role,
            content=content,
            metadata=metadata or {},
            created_at=datetime.utcnow()
        )

        self._messages.append(msg)

        if self._client.is_available:
            self._client.insert("chat_messages", {
                "thread_id": self.thread_id,
                "user_id": self.user_id,
                "role": role,
                "content": content,
                "metadata": metadata or {}
            })

        return msg

    async def add_message(self, role: str, content: str, metadata: Dict[str, Any] = None) -> ChatMessage:
        """Add a message (async wrapper)"""
        return self.add_message_sync(role, content, metadata)

    def get_messages(self) -> List[ChatMessage]:
        """Get all messages in memory"""
        return self._messages

    def get_context_string(self, max_messages: int = 10) -> str:
        """Get recent messages as context string for LLM"""
        recent = self._messages[-max_messages:] if len(self._messages) > max_messages else self._messages

        context_parts = []
        for msg in recent:
            role_label = "Usuario" if msg.role == "user" else "Asistente"
            context_parts.append(f"{role_label}: {msg.content}")

        return "\n".join(context_parts)

    def clear(self):
        """Clear in-memory messages"""
        self._messages = []


class AgentMemory:
    """
    Long-term memory for user preferences and learnings.

    Stores preferences like:
    - Preferred chart types
    - Common date ranges
    - Favorite metrics
    """

    def __init__(self, user_id: str):
        self.user_id = user_id
        self._client = get_memory_client()
        self._cache: Dict[str, Any] = {}

    def get_preference(self, key: str, default: Any = None) -> Any:
        """Get a user preference"""
        if key in self._cache:
            return self._cache[key]

        if not self._client.is_available:
            return default

        try:
            rows = self._client.select(
                "agent_memory",
                filters={
                    "user_id": f"eq.{self.user_id}",
                    "memory_type": "eq.preference",
                    "key": f"eq.{key}"
                },
                limit=1
            )

            if rows:
                value = rows[0].get("value")
                self._cache[key] = value
                return value

        except Exception as e:
            print(f"[AgentMemory] Error getting preference: {e}")

        return default

    def set_preference(self, key: str, value: Any, confidence: float = 1.0):
        """Set a user preference"""
        self._cache[key] = value

        if not self._client.is_available:
            return

        self._client.upsert("agent_memory", {
            "user_id": self.user_id,
            "memory_type": "preference",
            "key": key,
            "value": value,
            "confidence": confidence
        }, on_conflict="user_id,memory_type,key")

    def learn(self, key: str, value: Any, thread_id: Optional[str] = None):
        """Store a learning from conversation"""
        if not self._client.is_available:
            return

        self._client.insert("agent_memory", {
            "user_id": self.user_id,
            "thread_id": thread_id,
            "memory_type": "learning",
            "key": key,
            "value": value,
            "confidence": 0.8
        })

    def get_all_preferences(self) -> Dict[str, Any]:
        """Get all user preferences"""
        if not self._client.is_available:
            return self._cache

        try:
            rows = self._client.select(
                "agent_memory",
                filters={
                    "user_id": f"eq.{self.user_id}",
                    "memory_type": "eq.preference"
                }
            )

            prefs = {row["key"]: row["value"] for row in rows}
            self._cache.update(prefs)
            return prefs

        except Exception as e:
            print(f"[AgentMemory] Error getting preferences: {e}")
            return self._cache


# Singleton instances per thread/user
_chat_memories: Dict[str, ChatMemory] = {}
_agent_memories: Dict[str, AgentMemory] = {}


def get_chat_memory(thread_id: str, user_id: Optional[str] = None) -> ChatMemory:
    """Get or create chat memory for a thread"""
    if thread_id not in _chat_memories:
        _chat_memories[thread_id] = ChatMemory(thread_id, user_id)
    return _chat_memories[thread_id]


def get_agent_memory(user_id: str) -> AgentMemory:
    """Get or create agent memory for a user"""
    if user_id not in _agent_memories:
        _agent_memories[user_id] = AgentMemory(user_id)
    return _agent_memories[user_id]
