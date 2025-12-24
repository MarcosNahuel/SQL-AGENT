"""
Supabase Memory Store para LangGraph

Implementa memoria a largo plazo usando Supabase:
- Checkpointer: Guarda estado del grafo entre invocaciones
- Memory Store: Guarda memorias semanticas por user/namespace
- Conversation History: Historial de mensajes por thread

Basado en la documentacion de LangGraph Memory:
https://docs.langchain.com/oss/python/langgraph/memory
"""
import os
import json
import hashlib
from typing import Optional, Any, Dict, List, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, field
import httpx

from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.base import BaseCheckpointSaver


@dataclass
class MemoryEntry:
    """Una entrada de memoria"""
    id: str
    namespace: str
    key: str
    value: Dict[str, Any]
    user_id: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class SupabaseMemoryStore:
    """
    Memory Store usando Supabase REST API.

    Guarda memorias en la tabla 'agent_memory' con estructura:
    - id: UUID
    - namespace: string (ej: "user_preferences", "conversation_facts")
    - key: string (clave unica dentro del namespace)
    - value: JSONB (datos de la memoria)
    - user_id: string (opcional, para filtrar por usuario)
    - embedding: vector(1536) (opcional, para busqueda semantica)
    - created_at, updated_at, expires_at: timestamps
    """

    TABLE_NAME = "agent_memory"

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

    def _generate_id(self, namespace: str, key: str, user_id: Optional[str] = None) -> str:
        """Genera un ID determinista basado en namespace/key/user"""
        parts = [namespace, key]
        if user_id:
            parts.append(user_id)
        content = ":".join(parts)
        return hashlib.sha256(content.encode()).hexdigest()[:32]

    def put(
        self,
        namespace: str,
        key: str,
        value: Dict[str, Any],
        user_id: Optional[str] = None,
        ttl_hours: Optional[int] = None,
        metadata: Optional[Dict] = None
    ) -> bool:
        """
        Guarda una memoria en el store.

        Args:
            namespace: Espacio de nombres (ej: "user_prefs", "facts")
            key: Clave unica dentro del namespace
            value: Datos a guardar (dict)
            user_id: Usuario asociado (opcional)
            ttl_hours: Tiempo de vida en horas (opcional)
            metadata: Metadatos adicionales (opcional)

        Returns:
            True si se guardo correctamente
        """
        memory_id = self._generate_id(namespace, key, user_id)
        now = datetime.utcnow().isoformat()

        expires_at = None
        if ttl_hours:
            expires_at = (datetime.utcnow() + timedelta(hours=ttl_hours)).isoformat()

        data = {
            "id": memory_id,
            "namespace": namespace,
            "key": key,
            "value": value,
            "user_id": user_id,
            "created_at": now,
            "updated_at": now,
            "expires_at": expires_at,
            "metadata": metadata or {}
        }

        try:
            # Upsert (insert or update on conflict)
            url = f"{self.base_url}/rest/v1/{self.TABLE_NAME}"
            response = self.client.post(
                url,
                headers={**self.headers, "Prefer": "resolution=merge-duplicates"},
                json=data
            )
            return response.status_code in (200, 201)
        except Exception as e:
            print(f"[SupabaseMemory] Error putting memory: {e}")
            return False

    def get(
        self,
        namespace: str,
        key: str,
        user_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Obtiene una memoria del store.

        Returns:
            El valor guardado o None si no existe
        """
        memory_id = self._generate_id(namespace, key, user_id)

        try:
            url = f"{self.base_url}/rest/v1/{self.TABLE_NAME}"
            params = {
                "select": "value,expires_at",
                "id": f"eq.{memory_id}"
            }
            response = self.client.get(url, headers=self.headers, params=params)

            if response.status_code == 200:
                rows = response.json()
                if rows:
                    row = rows[0]
                    # Check expiration
                    expires_at = row.get("expires_at")
                    if expires_at:
                        exp_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
                        if exp_dt < datetime.now(exp_dt.tzinfo):
                            # Expired, delete it
                            self.delete(namespace, key, user_id)
                            return None
                    return row.get("value")
            return None
        except Exception as e:
            print(f"[SupabaseMemory] Error getting memory: {e}")
            return None

    def delete(
        self,
        namespace: str,
        key: str,
        user_id: Optional[str] = None
    ) -> bool:
        """Elimina una memoria"""
        memory_id = self._generate_id(namespace, key, user_id)

        try:
            url = f"{self.base_url}/rest/v1/{self.TABLE_NAME}"
            params = {"id": f"eq.{memory_id}"}
            response = self.client.delete(url, headers=self.headers, params=params)
            return response.status_code in (200, 204)
        except Exception as e:
            print(f"[SupabaseMemory] Error deleting memory: {e}")
            return False

    def list_by_namespace(
        self,
        namespace: str,
        user_id: Optional[str] = None,
        limit: int = 100
    ) -> List[MemoryEntry]:
        """Lista todas las memorias de un namespace"""
        try:
            url = f"{self.base_url}/rest/v1/{self.TABLE_NAME}"
            params = {
                "select": "*",
                "namespace": f"eq.{namespace}",
                "limit": str(limit),
                "order": "updated_at.desc"
            }
            if user_id:
                params["user_id"] = f"eq.{user_id}"

            response = self.client.get(url, headers=self.headers, params=params)

            if response.status_code == 200:
                return [
                    MemoryEntry(
                        id=row["id"],
                        namespace=row["namespace"],
                        key=row["key"],
                        value=row["value"],
                        user_id=row.get("user_id"),
                        metadata=row.get("metadata", {})
                    )
                    for row in response.json()
                ]
            return []
        except Exception as e:
            print(f"[SupabaseMemory] Error listing memories: {e}")
            return []

    def search_semantic(
        self,
        query_embedding: List[float],
        namespace: Optional[str] = None,
        user_id: Optional[str] = None,
        limit: int = 5,
        threshold: float = 0.7
    ) -> List[Tuple[MemoryEntry, float]]:
        """
        Busqueda semantica usando pgvector.

        Requiere que la columna 'embedding' tenga datos.
        Retorna lista de (memoria, similarity_score).
        """
        # TODO: Implementar con RPC function en Supabase
        # Por ahora retorna lista vacia
        return []

    def cleanup_expired(self) -> int:
        """Elimina memorias expiradas. Retorna cantidad eliminada."""
        try:
            now = datetime.utcnow().isoformat()
            url = f"{self.base_url}/rest/v1/{self.TABLE_NAME}"
            params = {"expires_at": f"lt.{now}"}
            response = self.client.delete(url, headers=self.headers, params=params)
            # Can't easily get count from DELETE response
            return 0
        except Exception as e:
            print(f"[SupabaseMemory] Error cleaning up: {e}")
            return 0


class SupabaseCheckpointSaver(BaseCheckpointSaver):
    """
    Checkpointer que guarda estado en Supabase.

    Usa la tabla 'langgraph_checkpoints' con estructura:
    - thread_id: string
    - checkpoint_id: string
    - checkpoint: JSONB
    - metadata: JSONB
    - created_at: timestamp
    """

    TABLE_NAME = "langgraph_checkpoints"

    def __init__(self):
        super().__init__()
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
        self._fallback = MemorySaver()
        self._use_fallback = False

        # Test connection
        if not self._test_table_exists():
            print("[SupabaseCheckpoint] Table not found, using MemorySaver fallback")
            self._use_fallback = True

    def _test_table_exists(self) -> bool:
        """Verifica si la tabla existe"""
        try:
            url = f"{self.base_url}/rest/v1/{self.TABLE_NAME}"
            params = {"select": "thread_id", "limit": "1"}
            response = self.client.get(url, headers=self.headers, params=params)
            return response.status_code == 200
        except:
            return False

    def put(self, config: dict, checkpoint: dict, metadata: dict) -> dict:
        """Guarda un checkpoint"""
        if self._use_fallback:
            return self._fallback.put(config, checkpoint, metadata)

        thread_id = config.get("configurable", {}).get("thread_id", "default")
        checkpoint_id = checkpoint.get("id", str(datetime.utcnow().timestamp()))

        data = {
            "thread_id": thread_id,
            "checkpoint_id": checkpoint_id,
            "checkpoint": checkpoint,
            "metadata": metadata,
            "created_at": datetime.utcnow().isoformat()
        }

        try:
            url = f"{self.base_url}/rest/v1/{self.TABLE_NAME}"
            response = self.client.post(
                url,
                headers={**self.headers, "Prefer": "resolution=merge-duplicates"},
                json=data
            )
            if response.status_code not in (200, 201):
                print(f"[SupabaseCheckpoint] Error saving: {response.status_code}")
                return self._fallback.put(config, checkpoint, metadata)
            return {"configurable": {"thread_id": thread_id, "checkpoint_id": checkpoint_id}}
        except Exception as e:
            print(f"[SupabaseCheckpoint] Error: {e}")
            return self._fallback.put(config, checkpoint, metadata)

    def get(self, config: dict) -> Optional[dict]:
        """Obtiene el ultimo checkpoint de un thread"""
        if self._use_fallback:
            return self._fallback.get(config)

        thread_id = config.get("configurable", {}).get("thread_id", "default")

        try:
            url = f"{self.base_url}/rest/v1/{self.TABLE_NAME}"
            params = {
                "select": "checkpoint,metadata",
                "thread_id": f"eq.{thread_id}",
                "order": "created_at.desc",
                "limit": "1"
            }
            response = self.client.get(url, headers=self.headers, params=params)

            if response.status_code == 200:
                rows = response.json()
                if rows:
                    return rows[0]["checkpoint"]
            return None
        except Exception as e:
            print(f"[SupabaseCheckpoint] Error getting: {e}")
            return self._fallback.get(config)

    def list(self, config: dict, *, before: Optional[str] = None, limit: int = 10):
        """Lista checkpoints de un thread"""
        if self._use_fallback:
            return self._fallback.list(config, before=before, limit=limit)

        thread_id = config.get("configurable", {}).get("thread_id", "default")

        try:
            url = f"{self.base_url}/rest/v1/{self.TABLE_NAME}"
            params = {
                "select": "checkpoint_id,metadata,created_at",
                "thread_id": f"eq.{thread_id}",
                "order": "created_at.desc",
                "limit": str(limit)
            }
            response = self.client.get(url, headers=self.headers, params=params)

            if response.status_code == 200:
                return response.json()
            return []
        except Exception as e:
            print(f"[SupabaseCheckpoint] Error listing: {e}")
            return []


# Singletons
_memory_store: Optional[SupabaseMemoryStore] = None
_checkpointer: Optional[SupabaseCheckpointSaver] = None


def get_memory_store() -> SupabaseMemoryStore:
    """Obtiene el store de memoria singleton"""
    global _memory_store
    if _memory_store is None:
        _memory_store = SupabaseMemoryStore()
    return _memory_store


def get_supabase_checkpointer() -> SupabaseCheckpointSaver:
    """Obtiene el checkpointer singleton"""
    global _checkpointer
    if _checkpointer is None:
        _checkpointer = SupabaseCheckpointSaver()
    return _checkpointer
