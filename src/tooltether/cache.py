"""Async-safe local caches with hashed, identity-scoped keys."""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar

T = TypeVar("T")


@dataclass(slots=True)
class CacheEntry:
    value: Any
    expires_at: float
    tags: frozenset[str]
    tool_fingerprint: str


class CacheBackend(Protocol):
    async def get(self, key: str) -> Any | None: ...

    async def set(
        self,
        key: str,
        value: Any,
        ttl_seconds: float,
        *,
        tags: frozenset[str] = frozenset(),
        tool_fingerprint: str = "",
    ) -> None: ...

    async def delete(self, key: str) -> None: ...

    async def invalidate(
        self, *, tag: str | None = None, fingerprint: str | None = None
    ) -> int: ...


class MemoryCache:
    def __init__(self, max_entries: int = 1024) -> None:
        self.max_entries = max_entries
        self._items: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = asyncio.Lock()
        self._key_locks: dict[str, asyncio.Lock] = {}

    async def get(self, key: str) -> Any | None:
        async with self._lock:
            entry = self._items.get(key)
            if entry is None:
                return None
            if entry.expires_at <= time.monotonic():
                self._items.pop(key, None)
                return None
            self._items.move_to_end(key)
            return entry.value

    async def set(
        self,
        key: str,
        value: Any,
        ttl_seconds: float,
        *,
        tags: frozenset[str] = frozenset(),
        tool_fingerprint: str = "",
    ) -> None:
        async with self._lock:
            self._items[key] = CacheEntry(
                value=value,
                expires_at=time.monotonic() + ttl_seconds,
                tags=tags,
                tool_fingerprint=tool_fingerprint,
            )
            self._items.move_to_end(key)
            while len(self._items) > self.max_entries:
                self._items.popitem(last=False)

    async def delete(self, key: str) -> None:
        async with self._lock:
            self._items.pop(key, None)

    async def invalidate(self, *, tag: str | None = None, fingerprint: str | None = None) -> int:
        async with self._lock:
            keys = [
                key
                for key, entry in self._items.items()
                if (tag is None or tag in entry.tags)
                and (fingerprint is None or entry.tool_fingerprint == fingerprint)
            ]
            for key in keys:
                self._items.pop(key, None)
            return len(keys)

    async def get_or_compute(
        self,
        key: str,
        factory: Callable[[], Awaitable[T]],
        ttl_seconds: float,
        *,
        tags: frozenset[str] = frozenset(),
        tool_fingerprint: str = "",
    ) -> tuple[T, bool]:
        cached = await self.get(key)
        if cached is not None:
            return cached, True
        async with self._lock:
            key_lock = self._key_locks.setdefault(key, asyncio.Lock())
        try:
            async with key_lock:
                cached = await self.get(key)
                if cached is not None:
                    return cached, True
                value = await factory()
                await self.set(
                    key,
                    value,
                    ttl_seconds,
                    tags=tags,
                    tool_fingerprint=tool_fingerprint,
                )
                return value, False
        finally:
            async with self._lock:
                if not key_lock.locked():
                    self._key_locks.pop(key, None)
