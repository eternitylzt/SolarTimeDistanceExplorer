"""Thread-safe small LRU cache for decoded image frames."""

from __future__ import annotations

from collections import OrderedDict
from threading import RLock
from typing import Generic, TypeVar

T = TypeVar("T")


class LRUFrameCache(Generic[T]):
    """Bounded LRU cache; FITS folder reads use it to avoid slider thrashing."""

    def __init__(self, max_items: int = 12) -> None:
        if max_items < 1:
            raise ValueError("max_items must be positive")
        self.max_items = max_items
        self._items: OrderedDict[int, T] = OrderedDict()
        self._lock = RLock()

    def get(self, key: int) -> T | None:
        """Get and promote a cached frame, or return None."""
        with self._lock:
            value = self._items.get(key)
            if value is not None:
                self._items.move_to_end(key)
            return value

    def put(self, key: int, value: T) -> None:
        """Add a frame and evict the least-recently-used item if necessary."""
        with self._lock:
            self._items[key] = value
            self._items.move_to_end(key)
            while len(self._items) > self.max_items:
                self._items.popitem(last=False)

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
            while len(self._items) > self.max_items:
                self._items.popitem(last=False)
