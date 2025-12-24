"""
supabase_store.py - Almacén de Memoria a Largo Plazo

Implementa memoria semántica persistente usando Supabase para:
- Preferencias de usuario aprendidas
- Reglas de negocio descubiertas
- Correcciones de errores pasados
- Insights importantes a recordar

Tabla requerida en Supabase:
CREATE TABLE agent_memory (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    namespace TEXT NOT NULL DEFAULT 'default',
    key TEXT NOT NULL,
    content JSONB NOT NULL,
    embedding VECTOR(1536),  -- Para búsqueda semántica (opcional)
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ,
    UNIQUE(user_id, namespace, key)
);

CREATE INDEX idx_agent_memory_user ON agent_memory(user_id, namespace);
CREATE INDEX idx_agent_memory_embedding ON agent_memory USING ivfflat (embedding vector_cosine_ops);
"""
import os
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

from supabase import create_client, Client


@dataclass
class MemoryEntry:
    """Una entrada de memoria"""
    key: str
    content: Dict[str, Any]
    namespace: str = "default"
    created_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None


class SupabaseMemoryStore:
    """
    Almacén de memoria a largo plazo usando Supabase.

    Soporta:
    - CRUD básico de memorias
    - Namespaces para organización (preferences, corrections, insights)
    - TTL automático para limpieza
    - Búsqueda por clave o prefijo
    """

    TABLE_NAME = "agent_memory"

    # Namespaces predefinidos
    NS_PREFERENCES = "preferences"  # Preferencias del usuario
    NS_CORRECTIONS = "corrections"  # Correcciones aprendidas
    NS_INSIGHTS = "insights"        # Insights importantes
    NS_SCHEMA = "schema"           # Cache de esquema
    NS_QUERIES = "queries"         # Queries exitosas pasadas

    def __init__(self, supabase_url: str = None, supabase_key: str = None):
        url = supabase_url or os.getenv("SUPABASE_URL")
        key = supabase_key or os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_ANON_KEY")

        if not url or not key:
            raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_KEY required")

        self.client: Client = create_client(url, key)
        self._table_checked = False

    def _ensure_table(self):
        """Verifica que la tabla existe (lazy check)"""
        if self._table_checked:
            return

        # Intentar hacer una query simple
        try:
            self.client.table(self.TABLE_NAME).select("id").limit(1).execute()
            self._table_checked = True
        except Exception as e:
            print(f"[MemoryStore] Warning: Table check failed - {e}")
            print("[MemoryStore] Run SQL migration to create agent_memory table")
            self._table_checked = True  # No reintentar

    def put(
        self,
        user_id: str,
        key: str,
        content: Dict[str, Any],
        namespace: str = "default",
        ttl_hours: Optional[int] = None
    ) -> bool:
        """
        Guarda o actualiza una memoria.

        Args:
            user_id: ID del usuario
            key: Clave única dentro del namespace
            content: Contenido JSON a guardar
            namespace: Namespace para organización
            ttl_hours: Tiempo de vida en horas (None = permanente)

        Returns:
            True si se guardó correctamente
        """
        self._ensure_table()

        expires_at = None
        if ttl_hours:
            expires_at = (datetime.utcnow() + timedelta(hours=ttl_hours)).isoformat()

        data = {
            "user_id": user_id,
            "namespace": namespace,
            "key": key,
            "value": content,  # La tabla usa "value" en vez de "content"
            "expires_at": expires_at,
            "updated_at": datetime.utcnow().isoformat()
        }

        try:
            # Upsert: insert o update si existe
            result = self.client.table(self.TABLE_NAME).upsert(
                data,
                on_conflict="user_id,namespace,key"
            ).execute()
            return len(result.data) > 0
        except Exception as e:
            print(f"[MemoryStore] Error saving memory: {e}")
            return False

    def get(
        self,
        user_id: str,
        key: str,
        namespace: str = "default"
    ) -> Optional[Dict[str, Any]]:
        """
        Recupera una memoria por clave.

        Returns:
            Contenido de la memoria o None si no existe/expiró
        """
        self._ensure_table()

        try:
            result = self.client.table(self.TABLE_NAME).select("*").eq(
                "user_id", user_id
            ).eq(
                "namespace", namespace
            ).eq(
                "key", key
            ).execute()

            if not result.data:
                return None

            entry = result.data[0]

            # Verificar expiración
            if entry.get("expires_at"):
                expires = datetime.fromisoformat(entry["expires_at"].replace("Z", "+00:00"))
                if datetime.utcnow().replace(tzinfo=expires.tzinfo) > expires:
                    # Expirado, eliminar
                    self.delete(user_id, key, namespace)
                    return None

            return entry.get("value")

        except Exception as e:
            print(f"[MemoryStore] Error getting memory: {e}")
            return None

    def list(
        self,
        user_id: str,
        namespace: str = None,
        prefix: str = None,
        limit: int = 100
    ) -> List[MemoryEntry]:
        """
        Lista memorias con filtros opcionales.

        Args:
            user_id: ID del usuario
            namespace: Filtrar por namespace
            prefix: Filtrar por prefijo de clave
            limit: Máximo de resultados

        Returns:
            Lista de MemoryEntry
        """
        self._ensure_table()

        try:
            query = self.client.table(self.TABLE_NAME).select("*").eq(
                "user_id", user_id
            )

            if namespace:
                query = query.eq("namespace", namespace)

            if prefix:
                query = query.like("key", f"{prefix}%")

            result = query.order("created_at", desc=True).limit(limit).execute()

            entries = []
            for row in result.data:
                # Filtrar expirados
                if row.get("expires_at"):
                    expires = datetime.fromisoformat(row["expires_at"].replace("Z", "+00:00"))
                    if datetime.utcnow().replace(tzinfo=expires.tzinfo) > expires:
                        continue

                entries.append(MemoryEntry(
                    key=row["key"],
                    content=row["value"],  # La tabla usa "value"
                    namespace=row["namespace"],
                    created_at=datetime.fromisoformat(row["created_at"].replace("Z", "+00:00")) if row.get("created_at") else None,
                    expires_at=datetime.fromisoformat(row["expires_at"].replace("Z", "+00:00")) if row.get("expires_at") else None
                ))

            return entries

        except Exception as e:
            print(f"[MemoryStore] Error listing memories: {e}")
            return []

    def delete(
        self,
        user_id: str,
        key: str,
        namespace: str = "default"
    ) -> bool:
        """Elimina una memoria"""
        self._ensure_table()

        try:
            self.client.table(self.TABLE_NAME).delete().eq(
                "user_id", user_id
            ).eq(
                "namespace", namespace
            ).eq(
                "key", key
            ).execute()
            return True
        except Exception as e:
            print(f"[MemoryStore] Error deleting memory: {e}")
            return False

    def clear_namespace(self, user_id: str, namespace: str) -> int:
        """Limpia todas las memorias de un namespace"""
        self._ensure_table()

        try:
            result = self.client.table(self.TABLE_NAME).delete().eq(
                "user_id", user_id
            ).eq(
                "namespace", namespace
            ).execute()
            return len(result.data) if result.data else 0
        except Exception as e:
            print(f"[MemoryStore] Error clearing namespace: {e}")
            return 0

    def cleanup_expired(self) -> int:
        """Limpia memorias expiradas (ejecutar periódicamente)"""
        self._ensure_table()

        try:
            now = datetime.utcnow().isoformat()
            result = self.client.table(self.TABLE_NAME).delete().lt(
                "expires_at", now
            ).execute()
            count = len(result.data) if result.data else 0
            if count > 0:
                print(f"[MemoryStore] Cleaned up {count} expired memories")
            return count
        except Exception as e:
            print(f"[MemoryStore] Error cleaning up: {e}")
            return 0

    # === Métodos de conveniencia ===

    def remember_preference(
        self,
        user_id: str,
        preference_key: str,
        preference_value: Any
    ):
        """Guarda una preferencia del usuario"""
        self.put(
            user_id=user_id,
            key=preference_key,
            content={"value": preference_value, "type": "preference"},
            namespace=self.NS_PREFERENCES
        )

    def remember_correction(
        self,
        user_id: str,
        original_query: str,
        correction: str,
        reason: str
    ):
        """Guarda una corrección aprendida"""
        key = f"correction_{hash(original_query) % 10000}"
        self.put(
            user_id=user_id,
            key=key,
            content={
                "original": original_query,
                "correction": correction,
                "reason": reason
            },
            namespace=self.NS_CORRECTIONS,
            ttl_hours=24 * 30  # 30 días
        )

    def remember_insight(
        self,
        user_id: str,
        insight_key: str,
        insight: str,
        context: Dict[str, Any] = None
    ):
        """Guarda un insight importante"""
        self.put(
            user_id=user_id,
            key=insight_key,
            content={
                "insight": insight,
                "context": context or {}
            },
            namespace=self.NS_INSIGHTS,
            ttl_hours=24 * 7  # 7 días
        )

    def get_relevant_memories(
        self,
        user_id: str,
        namespaces: List[str] = None
    ) -> Dict[str, List[Dict]]:
        """Obtiene memorias relevantes organizadas por namespace"""
        if namespaces is None:
            namespaces = [self.NS_PREFERENCES, self.NS_CORRECTIONS, self.NS_INSIGHTS]

        result = {}
        for ns in namespaces:
            entries = self.list(user_id, namespace=ns, limit=20)
            result[ns] = [{"key": e.key, **(e.content if isinstance(e.content, dict) else {"value": e.content})} for e in entries]

        return result


# Singleton global
_store: Optional[SupabaseMemoryStore] = None


def get_memory_store() -> Optional[SupabaseMemoryStore]:
    """Obtiene el store de memoria global"""
    global _store
    if _store is None:
        try:
            _store = SupabaseMemoryStore()
        except Exception as e:
            print(f"[MemoryStore] Could not initialize: {e}")
            return None
    return _store


# SQL para crear la tabla (para referencia)
# NOTA: La tabla ya existe con esta estructura:
CREATE_TABLE_SQL = """
-- Tabla para memoria a largo plazo del agente (estructura existente)
CREATE TABLE IF NOT EXISTS agent_memory (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    namespace TEXT NOT NULL DEFAULT 'default',
    key TEXT NOT NULL,
    value JSONB NOT NULL,  -- Almacena el contenido
    metadata JSONB,        -- Metadata adicional opcional
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ,
    UNIQUE(user_id, namespace, key)
);

-- Índices
CREATE INDEX IF NOT EXISTS idx_agent_memory_user ON agent_memory(user_id, namespace);
CREATE INDEX IF NOT EXISTS idx_agent_memory_key ON agent_memory(key);
"""
