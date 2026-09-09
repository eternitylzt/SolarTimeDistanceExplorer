"""Memory-mapped 3-D FITS cube source and explicit time-axis inference."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from astropy.io import fits
from astropy.time import Time
from astropy.wcs import WCS

from app.data.base import TimeSeriesDataset
from app.data.fits_common import first_image_header, header_exposure_seconds, spatial_wcs
from app.data.metadata import FrameMetadata, TimeAxisDetection
from app.data.time_parser import parse_header_time, times_from_axis


def detect_time_axis(header: dict[str, Any], shape: tuple[int, ...]) -> TimeAxisDetection:
    """Detect a cube time axis from FITS WCS, falling back to a transparent heuristic."""
    candidates: list[int] = []
    for numpy_axis in range(len(shape)):
        fits_axis = len(shape) - numpy_axis
        text = f"{header.get(f'CTYPE{fits_axis}', '')} {header.get(f'CNAME{fits_axis}', '')}".upper()
        if any(token in text for token in ("TIME", "UTC", "TAI", "MJD", "JD")):
            candidates.append(numpy_axis)
    if len(candidates) == 1:
        return TimeAxisDetection(candidates[0], "High", "FITS CTYPE/CNAME identifies a time axis.")
    if len(candidates) > 1:
        return TimeAxisDetection(None, "Uncertain", "More than one FITS axis looks temporal.")

    # A conservative heuristic: unique smallest dimension only. It is never silent
    # in the GUI because the returned confidence is Low.
    sizes = list(shape)
    smallest = min(sizes)
    if sizes.count(smallest) == 1:
        return TimeAxisDetection(sizes.index(smallest), "Low", "Unique smallest dimension heuristic.")
    return TimeAxisDetection(None, "Uncertain", "No time CTYPE and spatial dimensions are ambiguous.")


class FitsCubeDataset(TimeSeriesDataset):
    """3-D FITS cube accessed as individual 2-D memmap slices."""

    source_type = "fits_cube"

    def __init__(self, path: str | Path, time_axis: int | None = None) -> None:
        path = Path(path)
        hdu_index, header, shape = first_image_header(path)
        if len(shape) != 3:
            raise ValueError(f"Expected a 3-D FITS image cube, found shape {shape}.")
        detection = detect_time_axis(dict(header), shape)
        self.detection = detection
        if time_axis is None:
            if detection.axis is None:
                raise ValueError("Cube time axis is uncertain. Select Axis 0, Axis 1, or Axis 2.")
            time_axis = detection.axis
        if time_axis not in (0, 1, 2):
            raise ValueError("Time axis must be 0, 1, or 2.")
        self.time_axis = time_axis
        self._hdu_index = hdu_index
        self._header = dict(header)
        self._shape_3d = shape
        spatial_shape = tuple(shape[axis] for axis in range(3) if axis != time_axis)
        # The data convention is y,x for a normal FITS cube; preserve the remaining
        # NumPy axis order so no implicit transpose contaminates scientific values.
        if len(spatial_shape) != 2:
            raise ValueError("A cube must leave exactly two spatial axes.")
        times = times_from_axis(header, time_axis, shape)
        fallback_time = parse_header_time(header)
        if times is None and fallback_time is not None:
            times = fallback_time + np.arange(shape[time_axis]) * 0.0  # known start, unknown cadence
            times = None
        metadata = [
            FrameMetadata(
                source=str(path),
                time=times[i] if times is not None else None,
                header=dict(header),
                exposure_seconds=header_exposure_seconds(header),
                shape=(spatial_shape[0], spatial_shape[1]),
            )
            for i in range(shape[time_axis])
        ]
        self._wcs = spatial_wcs(header)
        super().__init__(path, times, metadata, (spatial_shape[0], spatial_shape[1]))

    @classmethod
    def inspect(cls, path: str | Path) -> TimeAxisDetection:
        """Inspect a cube without instantiating a data-reading object."""
        _, header, shape = first_image_header(path)
        if len(shape) != 3:
            raise ValueError(f"Expected a 3-D FITS image cube, found shape {shape}.")
        return detect_time_axis(dict(header), shape)

    def _data(self) -> np.ndarray:
        """Open the selected HDU as a current memmap; no persistent file handle."""
        with fits.open(self.source, memmap=True, lazy_load_hdus=True) as hdul:
            data = hdul[self._hdu_index].data
            if data is None:
                raise ValueError("FITS cube data are missing.")
            return np.asarray(data)

    def get_frame(self, index: int) -> np.ndarray:
        """Take one 2-D slice along the user-selected time axis."""
        if not 0 <= index < self.n_frames:
            raise IndexError(index)
        frame = np.take(self._data(), index, axis=self.time_axis)
        if frame.ndim != 2:
            raise ValueError("Selected time axis did not leave a 2-D frame.")
        return np.asarray(frame)

    def get_wcs(self, index: int) -> WCS | None:
        """Return static celestial WCS when representable after cube slicing."""
        return self._wcs

    def project_descriptor(self) -> dict[str, Any]:
        """Persist explicit cube axis choice, never merely the AUTO inference."""
        output = super().project_descriptor()
        output["time_axis"] = self.time_axis
        return output
