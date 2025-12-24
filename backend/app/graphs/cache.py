"""
Cache Module for LangGraph Nodes

Provides:
- LRU cache with TTL
- Per-node caching policies
- Cache key generation based on state

Based on LangGraph caching docs:
https://docs.langchain.com/oss/python/langgraph/graph-api
"""
import hashlib
import json
import time
from typing import Any, Dict, Optional, Callable
from functools import wraps
from dataclasses import dataclass, field
from collections import OrderedDict
import threading


@dataclass
class CachePolicy:
    """Politica de cache para un nodo"""
    enabled: bool = True
    ttl_seconds: int = 300  # 5 minutos default
    max_size: int = 100
    key_fields: list = field(default_factory=lambda: ["question"])

    def generate_key(self, state: Dict[str, Any]) -> str:
        """Genera una clave de cache basada en los campos especificados"""
        key_parts = []
        for field_name in self.key_fields:
            value = state.get(field_name)
            if value is not None:
                if isinstance(value, (dict, list)):
                    value = json.dumps(value, sort_keys=True)
                key_parts.append(f"{field_name}:{value}")

        key_str = "|".join(key_parts)
        return hashlib.sha256(key_str.encode()).hexdigest()[:16]


class LRUCache:
    """Thread-safe LRU Cache with TTL"""

    def __init__(self, max_size: int = 100, default_ttl: int = 300):
        self.max_size = max_size
        self.default_ttl = default_ttl
        self._cache: OrderedDict[str, tuple[Any, float]] = OrderedDict()
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Optional[Any]:
        """Obtiene un valor del cache si existe y no expiro"""
        with self._lock:
            if key not in self._cache:
                self._misses += 1
                return None

            value, expires_at = self._cache[key]

            # Check expiration
            if expires_at < time.time():
                del self._cache[key]
                self._misses += 1
                return None

            # Move to end (most recently used)
            self._cache.move_to_end(key)
            self._hits += 1
            return value

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Guarda un valor en el cache"""
        ttl = ttl or self.default_ttl
        expires_at = time.time() + ttl

        with self._lock:
            # If key exists, update and move to end
            if key in self._cache:
                self._cache[key] = (value, expires_at)
                self._cache.move_to_end(key)
            else:
                # Evict oldest if at capacity
                while len(self._cache) >= self.max_size:
                    self._cache.popitem(last=False)

                self._cache[key] = (value, expires_at)

    def delete(self, key: str) -> bool:
        """Elimina una clave del cache"""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    def clear(self) -> None:
        """Limpia todo el cache"""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0

    def cleanup_expired(self) -> int:
        """Elimina entradas expiradas. Retorna cantidad eliminada."""
        now = time.time()
        expired_keys = []

        with self._lock:
            for key, (_, expires_at) in self._cache.items():
                if expires_at < now:
                    expired_keys.append(key)

            for key in expired_keys:
                del self._cache[key]

        return len(expired_keys)

    @property
    def stats(self) -> Dict[str, Any]:
        """Estadisticas del cache"""
        with self._lock:
            total = self._hits + self._misses
            hit_rate = (self._hits / total * 100) if total > 0 else 0
            return {
                "size": len(self._cache),
                "max_size": self.max_size,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": f"{hit_rate:.1f}%"
            }


# Global caches por tipo de nodo
_router_cache = LRUCache(max_size=200, default_ttl=600)  # 10 min
_data_cache = LRUCache(max_size=100, default_ttl=300)    # 5 min
_presentation_cache = LRUCache(max_size=50, default_ttl=180)  # 3 min


# Cache policies por nodo
NODE_CACHE_POLICIES = {
    "Router": CachePolicy(
        enabled=True,
        ttl_seconds=600,
        max_size=200,
        key_fields=["question"]
    ),
    "DataAgent": CachePolicy(
        enabled=True,
        ttl_seconds=300,
        max_size=100,
        key_fields=["question", "date_from", "date_to"]
    ),
    "PresentationAgent": CachePolicy(
        enabled=True,
        ttl_seconds=180,
        max_size=50,
        key_fields=["question"]  # Presentation depends on question + data
    ),
    "DirectResponse": CachePolicy(
        enabled=True,
        ttl_seconds=3600,  # 1 hour for static responses
        max_size=50,
        key_fields=["question"]
    )
}


def get_cache_for_node(node_name: str) -> LRUCache:
    """Obtiene el cache apropiado para un nodo"""
    if node_name == "Router":
        return _router_cache
    elif node_name == "DataAgent":
        return _data_cache
    elif node_name in ("PresentationAgent", "DirectResponse"):
        return _presentation_cache
    else:
        return _data_cache  # Default


def cached_node(node_name: str):
    """
    Decorator para cachear resultados de nodos.

    Usage:
        @cached_node("DataAgent")
        def run_data_agent_node(state):
            ...
    """
    policy = NODE_CACHE_POLICIES.get(node_name, CachePolicy(enabled=False))
    cache = get_cache_for_node(node_name)

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(state: Dict[str, Any]) -> Dict[str, Any]:
            if not policy.enabled:
                return func(state)

            # Generate cache key
            cache_key = f"{node_name}:{policy.generate_key(state)}"

            # Try cache hit
            cached_result = cache.get(cache_key)
            if cached_result is not None:
                print(f"[Cache] HIT for {node_name}")
                return cached_result

            # Execute and cache
            print(f"[Cache] MISS for {node_name}")
            result = func(state)

            # Only cache successful results
            if result and not result.get("error"):
                cache.set(cache_key, result, policy.ttl_seconds)

            return result

        return wrapper
    return decorator


def invalidate_cache(node_name: Optional[str] = None) -> None:
    """Invalida el cache de un nodo o todos"""
    if node_name:
        cache = get_cache_for_node(node_name)
        cache.clear()
        print(f"[Cache] Cleared cache for {node_name}")
    else:
        _router_cache.clear()
        _data_cache.clear()
        _presentation_cache.clear()
        print("[Cache] Cleared all caches")


def get_cache_stats() -> Dict[str, Dict[str, Any]]:
    """Obtiene estadisticas de todos los caches"""
    return {
        "router": _router_cache.stats,
        "data": _data_cache.stats,
        "presentation": _presentation_cache.stats
    }
