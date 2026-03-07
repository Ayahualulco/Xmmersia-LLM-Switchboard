"""
Health Check Cache
══════════════════

Thread-safe in-memory cache for health check results.
Prevents hammering status pages on every check() call.
"""

from __future__ import annotations

import time
import threading
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CacheEntry:
    """A single cached health check result."""
    key: str
    value: Any
    created_at: float
    ttl: float

    @property
    def is_expired(self) -> bool:
        return (time.time() - self.created_at) > self.ttl


class HealthCache:
    """
    Thread-safe TTL cache for health check results.

    Usage:
        cache = HealthCache(default_ttl=30)
        cache.set("anthropic", health_data)
        result = cache.get("anthropic")  # Returns None if expired
    """

    def __init__(self, default_ttl: float = 30.0):
        self._default_ttl = default_ttl
        self._store: dict[str, CacheEntry] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Any | None:
        """Get a cached value. Returns None if missing or expired."""
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            if entry.is_expired:
                del self._store[key]
                return None
            return entry.value

    def set(self, key: str, value: Any, ttl: float | None = None) -> None:
        """Store a value with optional custom TTL."""
        with self._lock:
            self._store[key] = CacheEntry(
                key=key,
                value=value,
                created_at=time.time(),
                ttl=ttl if ttl is not None else self._default_ttl,
            )

    def invalidate(self, key: str) -> bool:
        """Remove a specific key. Returns True if it existed."""
        with self._lock:
            return self._store.pop(key, None) is not None

    def clear(self) -> int:
        """Clear all entries. Returns count of entries removed."""
        with self._lock:
            count = len(self._store)
            self._store.clear()
            return count

    def cleanup(self) -> int:
        """Remove all expired entries. Returns count removed."""
        with self._lock:
            expired = [k for k, v in self._store.items() if v.is_expired]
            for k in expired:
                del self._store[k]
            return len(expired)

    @property
    def size(self) -> int:
        """Number of entries (including possibly expired ones)."""
        with self._lock:
            return len(self._store)

    def stats(self) -> dict:
        """Cache statistics."""
        with self._lock:
            now = time.time()
            active = sum(1 for v in self._store.values() if not v.is_expired)
            expired = len(self._store) - active
            return {
                "total_entries": len(self._store),
                "active": active,
                "expired": expired,
                "default_ttl": self._default_ttl,
            }
