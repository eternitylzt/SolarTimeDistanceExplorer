"""Thread-safe small LRU cache for decoded image frames."""

from __future__ import annotations

from collections import OrderedDict
from threading import RLock
from typing import Generic, TypeVar

T = TypeVar("T")


class LRUFrameCache(Generic[T]):
    """Bounded LRU cache; FITS folder reads use it to avoid slider thrashing."""

    def __init__(self, max_items: int = 12, max_bytes: int = 256 * 1024**2) -> None:
        if max_items < 1:
            raise ValueError("max_items must be positive")
        self.max_items = max_items
        self.max_bytes = max(1, int(max_bytes))
        self.hits = 0
        self.misses = 0
        self._items: OrderedDict[int, T] = OrderedDict()
        self._lock = RLock()

    def get(self, key: int) -> T | None:
        """Get and promote a cached frame, or return None."""
        with self._lock:
            value = self._items.get(key)
            if value is not None:
                self.hits += 1
                self._items.move_to_end(key)
            else:
                self.misses += 1
            return value

    def put(self, key: int, value: T) -> None:
        """Add a frame and evict the least-recently-used item if necessary."""
        with self._lock:
            self._items[key] = value
            self._items.move_to_end(key)
            self._evict()

    @property
    def used_bytes(self) -> int:
        """Count resident array payloads (Map.data included), not Python overhead."""
        with self._lock:
            return sum(int(getattr(value, "nbytes", getattr(getattr(value, "data", None), "nbytes", 0)))
                       for value in self._items.values())

    def _evict(self) -> None:
        while self._items and (len(self._items) > self.max_items or self.used_bytes > self.max_bytes):
            self._items.popitem(last=False)

    def set_byte_limit(self, limit: int) -> None:
        """Evict immediately, including a single frame larger than the budget."""
        with self._lock:
            self.max_bytes = max(1, int(limit))
            self._evict()

    def pop(self, key: int) -> T | None:
        """Remove one cached value and return it when present."""
        with self._lock:
            return self._items.pop(key, None)

    def __len__(self) -> int:
        """Return the number of resident cache entries."""
        with self._lock:
            return len(self._items)

    def clear(self) -> None:
        """Free references held by the cache."""
        with self._lock:
            self._items.clear()

    def resize(self, max_items: int) -> None:
        """Change the LRU capacity and immediately evict excess old entries."""
        if max_items < 1:
            raise ValueError("max_items must be positive")
        with self._lock:
            self.max_items = max_items
            self._evict()
