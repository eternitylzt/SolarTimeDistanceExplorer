"""Metadata structures exposed to GUI controls without exposing FITS handles."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from astropy.time import Time


@dataclass(frozen=True)
class FrameMetadata:
    """Header-derived frame-local metadata that is safe to retain in memory."""

    source: str
    time: Time | None
    header: dict[str, Any] = field(default_factory=dict)
    exposure_seconds: float | None = None
    shape: tuple[int, int] | None = None


@dataclass(frozen=True)
class TimeAxisDetection:
    """Result of cube time-axis inference shown to the user before a choice."""

    axis: int | None
    confidence: str
    reason: str


@dataclass(frozen=True)
class DatasetSummary:
    """Concise summary displayed after a source scan."""

    source_type: str
    n_frames: int
    shape: tuple[int, int]
    start: Time | None
    end: Time | None
    median_cadence_s: float | None
    min_cadence_s: float | None
    max_cadence_s: float | None
    cadence_type: str
    instrument: str | None = None
    observatory: str | None = None
    wavelength: str | None = None
