"""
cache.py — Thread-safe in-memory TTL cache using a plain dict.

Usage:
    from cache import cache

    cache.set("user:torvalds", data, ttl=300)
    data = cache.get("user:torvalds")      # None if missing or expired
    cache.delete("user:torvalds")
    cache.flush()                          # clear everything
    cache.stats()                          # { keys, hits, misses, evictions }
"""

import time
import threading
from typing import Any, Optional


class TTLCache:
    """
    In-memory key-value store with per-key TTL and LRU-style eviction.

    Internals:
        _store: { key: { value, expires_at, created_at, hits } }
        _lock:  RLock for thread safety
        _stats: global hit/miss/eviction counters
    """

    def __init__(self, default_ttl: int = 300, max_keys: int = 500):
        self._store:   dict[str, dict] = {}
        self._lock:    threading.RLock = threading.RLock()
        self._default_ttl = default_ttl
        self._max_keys    = max_keys
        self._hits        = 0
        self._misses      = 0
        self._evictions   = 0

    # ── Core ops ──────────────────────────────────────────────────────────────

    def set(self, key: str, value: Any, ttl: Optional[int]) -> None:
        """Store a value. ttl=None uses the default."""
        ttl = ttl if ttl is not None else self._default_ttl
        now = time.time()
        with self._lock:
            # Evict oldest entry if at capacity (and key is new)
            if key not in self._store and len(self._store) >= self._max_keys:
                self._evict_oldest()
            self._store[key] = {
                "value":      value,
                "expires_at": now + ttl,
                "created_at": now,
                "ttl":        ttl,
                "hits":       0,
            }

    def get(self, key: str) -> Optional[Any]:
        """Return value if key exists and hasn't expired. None otherwise."""
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self._misses += 1
                return None
            if time.time() > entry["expires_at"]:
                del self._store[key]
                self._misses  += 1
                self._evictions += 1
                return None
            entry["hits"] += 1
            self._hits += 1
            return entry["value"]

    def get_with_meta(self, key: str) -> Optional[dict]:
        """Like get() but also returns TTL remaining and hit count."""
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            remaining = entry["expires_at"] - time.time()
            if remaining <= 0:
                del self._store[key]
                self._evictions += 1
                return None
            return {
                "value":      entry["value"],
                "ttl_left":   round(remaining),
                "created_at": entry["created_at"],
                "hits":       entry["hits"],
            }

    def delete(self, key: str) -> bool:
        """Remove a key. Returns True if it existed."""
        with self._lock:
            existed = key in self._store
            self._store.pop(key, None)
            return existed

    def exists(self, key: str) -> bool:
        """True if key exists and hasn't expired."""
        return self.get(key) is not None

    def flush(self) -> int:
        """Clear all keys. Returns number of keys removed."""
        with self._lock:
            n = len(self._store)
            self._store.clear()
            return n

    def flush_pattern(self, prefix: str) -> int:
        """Remove all keys starting with prefix. Returns count removed."""
        with self._lock:
            keys = [k for k in self._store if k.startswith(prefix)]
            for k in keys:
                del self._store[k]
            return len(keys)

    # ── TTL helpers ───────────────────────────────────────────────────────────

    def ttl(self, key: str) -> int:
        """Seconds until key expires. -1 if missing or expired."""
        with self._lock:
            entry = self._store.get(key)
            if not entry:
                return -1
            remaining = entry["expires_at"] - time.time()
            return max(0, int(remaining))

    def touch(self, key: str, ttl: Optional[int]) -> bool:
        """Reset expiry on an existing key. Returns False if key doesn't exist."""
        with self._lock:
            entry = self._store.get(key)
            if not entry or time.time() > entry["expires_at"]:
                return False
            new_ttl = ttl if ttl is not None else entry["ttl"]
            entry["expires_at"] = time.time() + new_ttl
            entry["ttl"]        = new_ttl
            return True

    # ── Background cleanup ────────────────────────────────────────────────────

    def purge_expired(self) -> int:
        """Remove all expired keys. Call periodically to free memory."""
        now = time.time()
        with self._lock:
            expired = [k for k, v in self._store.items() if now > v["expires_at"]]
            for k in expired:
                del self._store[k]
            self._evictions += len(expired)
            return len(expired)

    def start_auto_purge(self, interval: int = 60) -> threading.Thread:
        """
        Start a background daemon thread that purges expired keys every
        `interval` seconds. Returns the thread so you can join it if needed.
        """
        def _worker():
            while True:
                time.sleep(interval)
                removed = self.purge_expired()

        t = threading.Thread(target=_worker, daemon=True, name="cache-purge")
        t.start()
        return t

    # ── Introspection ─────────────────────────────────────────────────────────

    def stats(self) -> dict:
        """Return cache health stats."""
        now = time.time()
        with self._lock:
            live    = sum(1 for v in self._store.values() if now <= v["expires_at"])
            expired = len(self._store) - live
            total_reqs = self._hits + self._misses
            return {
                "keys_live":     live,
                "keys_expired":  expired,   # not yet purged
                "keys_total":    len(self._store),
                "max_keys":      self._max_keys,
                "hits":          self._hits,
                "misses":        self._misses,
                "evictions":     self._evictions,
                "hit_rate":      round(self._hits / total_reqs * 100, 1) if total_reqs else 0.0,
                "default_ttl":   self._default_ttl,
            }

    def keys(self, prefix: str = "") -> list[str]:
        """List all live (non-expired) keys, optionally filtered by prefix."""
        now = time.time()
        with self._lock:
            return [
                k for k, v in self._store.items()
                if now <= v["expires_at"] and k.startswith(prefix)
            ]

    def __len__(self) -> int:
        with self._lock:
            return sum(1 for v in self._store.values() if time.time() <= v["expires_at"])

    def __contains__(self, key: str) -> bool:
        return self.exists(key)

    def __repr__(self) -> str:
        s = self.stats()
        return f"<TTLCache keys={s['keys_live']} hit_rate={s['hit_rate']}% default_ttl={s['default_ttl']}s>"


# ── Singleton ──────────────────────────────────────────────────────────────────
# Import this everywhere: `from cache import cache`

cache = TTLCache(default_ttl=300, max_keys=500)
cache.start_auto_purge(interval=60)   # purge expired keys every minute