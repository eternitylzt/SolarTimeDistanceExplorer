"""A UI-independent abstraction over lazy 2-D image time series."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
from astropy.time import Time
from astropy.wcs import WCS

from app.data.metadata import DatasetSummary, FrameMetadata
from app.data.time_parser import cadence_statistics


class TimeSeriesDataset(ABC):
    """Abstract source of ordered 2-D frames and optional WCS/time metadata.

    Subclasses are responsible for loading one frame at a time. GUI objects never
    hold FITS HDULists or raw SAV state; all source specifics remain here.
    """

    source_type: str = "unknown"

    def __init__(
        self,
        source: str | Path,
        times: Time | None,
        frame_metadata: list[FrameMetadata],
        shape: tuple[int, int],
    ) -> None:
        self.source = Path(source)
        self.times = times
        self.time_origin = "source"
        self._frame_metadata = frame_metadata
        self.shape = tuple(map(int, shape))
        if not frame_metadata:
            raise ValueError("A dataset must contain at least one frame.")

    @property
    def n_frames(self) -> int:
        """Number of time-indexed two-dimensional frames."""
        return len(self._frame_metadata)

    @abstractmethod
    def get_frame(self, index: int) -> np.ndarray:
        """Return an in-memory numeric frame in NumPy row(y), column(x) order."""

    @abstractmethod
    def get_wcs(self, index: int) -> WCS | None:
        """Return the frame spatial WCS or None if it cannot be trusted."""

    def get_time(self, index: int) -> Time | None:
        """Return a single observation time, preserving Astropy precision."""
        if self.times is None:
            return None
        return self.times[index]

    def get_frame_metadata(self, index: int) -> FrameMetadata:
        """Return cached header-derived metadata without opening image data."""
        return self._frame_metadata[index]

    def get_header(self, index: int) -> Mapping[str, Any]:
        """Return a safe plain header mapping suitable for a metadata inspector."""
        return self._frame_metadata[index].header

    def get_map(self, index: int) -> Any | None:
        """Optionally return a SunPy Map. Generic readers return None by default."""
        return None

    def clear_cache(self, *, include_disk: bool = True) -> None:
        """Release optional derived-frame caches; generic datasets have none."""

    def close(self) -> None:
        """Release optional source resources before another dataset is installed."""
        self.clear_cache(include_disk=True)

    def set_times(self, times: Time | None) -> None:
        """Apply a user-confirmed manual time configuration."""
        if times is not None and len(times) != self.n_frames:
            raise ValueError("Time axis length does not match frame count.")
        self.times = times
        self.time_origin = "user/project configured"

    def summary(self) -> DatasetSummary:
        """Build a stable scan summary, including conservative cadence details."""
        start = self.times[0] if self.times is not None else None
        end = self.times[-1] if self.times is not None else None
        median, minimum, maximum, kind = cadence_statistics(self.times)
        first = self._frame_metadata[0].header
        wave = first.get("WAVELNTH", first.get("WAVELENGTH"))
        return DatasetSummary(
            source_type=self.source_type,
            n_frames=self.n_frames,
            shape=self.shape,
            start=start,
            end=end,
            median_cadence_s=median,
            min_cadence_s=minimum,
            max_cadence_s=maximum,
            cadence_type=kind,
            instrument=_as_text(first.get("INSTRUME")),
            observatory=_as_text(first.get("OBSERVAT", first.get("TELESCOP"))),
            wavelength=_as_text(wave),
        )

    def project_descriptor(self) -> dict[str, Any]:
        """Return minimal re-openable source information for a project file."""
        return {"source_type": self.source_type, "source": str(self.source)}


def _as_text(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)
