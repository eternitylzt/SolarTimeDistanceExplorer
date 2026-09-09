"""Non-destructive frame processor interfaces."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import numpy as np


class FrameProcessor(ABC):
    """Plugin-like per-frame transform; never writes back to the source dataset."""

    name = "None"

    @abstractmethod
    def process(self, frame: np.ndarray, metadata: dict[str, Any]) -> np.ndarray:
        """Return a derived frame while retaining NaN/bad-pixel semantics."""


class IdentityProcessor(FrameProcessor):
    """Default processor that deliberately leaves scientific data untouched."""

    name = "None"

    def process(self, frame: np.ndarray, metadata: dict[str, Any]) -> np.ndarray:
        return np.asarray(frame, dtype=float)


class RunningDifferenceProcessor(FrameProcessor):
    """Future-ready running difference processor, used only when explicitly selected."""

    name = "Running difference"

    def __init__(self) -> None:
        self._previous: np.ndarray | None = None

    def process(self, frame: np.ndarray, metadata: dict[str, Any]) -> np.ndarray:
        current = np.asarray(frame, dtype=float)
        result = np.full_like(current, np.nan) if self._previous is None else current - self._previous
        self._previous = current.copy()
        return result
