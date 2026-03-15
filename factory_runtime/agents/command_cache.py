"""Command result caching for agent efficiency.

Caches command outputs to avoid redundant operations within an issue scope.
Example: npm install run 3 times saves 8-12s by using cache.
"""

import hashlib
import time
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class CacheEntry:
    """Cached command result with TTL."""

    stdout: str
    stderr: str
    returncode: int
    timestamp: float
    execution_time_seconds: float


class CommandCache:
    """In-memory cache for command results with 1-hour TTL.

    Cache key: hash(command + cwd) for deterministic results.
    Metrics: cache_hits, time_saved_from_cache_seconds

    Usage:
        cache = CommandCache()

        # Check cache before running
        result = cache.get("npm install", "/path")
        if result:
            print(f"Cache hit! Saved {result.execution_time_seconds}s")
            return result

        # Run command and cache result
        start = time.time()
        output = subprocess.run(...)
        elapsed = time.time() - start

        cache.set("npm install", "/path", output.stdout, output.stderr,
                  output.returncode, elapsed)
    """

    def __init__(self, ttl_seconds: int = 3600):
        """Initialize cache with 1-hour default TTL."""
        self._cache: Dict[str, CacheEntry] = {}
        self._ttl_seconds = ttl_seconds
        self.cache_hits = 0
        self.time_saved_seconds = 0.0

    def _make_key(self, command: str, cwd: str) -> str:
        """Generate cache key from command + cwd."""
        key_data = f"{command}|{cwd}".encode("utf-8")
        return hashlib.sha256(key_data).hexdigest()[:16]

    def get(self, command: str, cwd: str) -> Optional[CacheEntry]:
        """Retrieve cached result if valid (within TTL).

        Returns None if not cached or expired.
        """
        key = self._make_key(command, cwd)
        entry = self._cache.get(key)

        if not entry:
            return None

        # Check TTL
        age = time.time() - entry.timestamp
        if age > self._ttl_seconds:
            # Expired, remove from cache
            del self._cache[key]
            return None

        # Cache hit
        self.cache_hits += 1
        self.time_saved_seconds += entry.execution_time_seconds
        return entry

    def set(
        self,
        command: str,
        cwd: str,
        stdout: str,
        stderr: str,
        returncode: int,
        execution_time_seconds: float,
    ) -> None:
        """Store command result in cache."""
        key = self._make_key(command, cwd)
        self._cache[key] = CacheEntry(
            stdout=stdout,
            stderr=stderr,
            returncode=returncode,
            timestamp=time.time(),
            execution_time_seconds=execution_time_seconds,
        )

    def clear(self) -> None:
        """Clear all cached entries."""
        self._cache.clear()
        self.cache_hits = 0
        self.time_saved_seconds = 0.0

    def get_metrics(self) -> Dict[str, float]:
        """Get cache performance metrics."""
        return {
            "cache_hits": self.cache_hits,
            "time_saved_from_cache_seconds": round(self.time_saved_seconds, 2),
            "cached_entries": len(self._cache),
        }

    def cleanup_expired(self) -> int:
        """Remove expired entries, return count removed."""
        now = time.time()
        expired_keys = [
            key
            for key, entry in self._cache.items()
            if (now - entry.timestamp) > self._ttl_seconds
        ]
        for key in expired_keys:
            del self._cache[key]
        return len(expired_keys)


# Global cache instance for agent tools
_global_cache = CommandCache()


def get_cache() -> CommandCache:
    """Get global command cache instance."""
    return _global_cache
