"""Single two-dimensional FITS scientific-image dataset."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from astropy.time import Time
from astropy.wcs import WCS

from app.data.base import TimeSeriesDataset
from app.data.fits_common import extract_2d_from_hdu, first_image_header, header_exposure_seconds, spatial_wcs
from app.data.metadata import FrameMetadata
from app.data.solar_map import make_solar_map
from app.data.time_parser import parse_header_time


class FitsImageDataset(TimeSeriesDataset):
    """One FITS image with SunPy/WCS-aware scientific preview semantics."""

    source_type = "fits_image"

    def __init__(self, path: str | Path, prepare_aia: bool = True) -> None:
        path = Path(path)
        hdu_index, header, shape = first_image_header(path)
        if len(shape) != 2:
            raise ValueError(f"Expected one 2-D FITS image, found shape {shape}.")
        self._hdu_index = hdu_index
        self._header = dict(header)
        self.prepare_aia = prepare_aia
        self._frame: np.ndarray | None = None
        self._map: Any | None = None
        self.map_notice: str | None = None
        self.aia_prepared = False
        time = parse_header_time(header)
        times = Time([time]) if time is not None else None
        metadata = [
            FrameMetadata(
                source=str(path),
                time=time,
                header=self._header,
                exposure_seconds=header_exposure_seconds(header),
                shape=(shape[0], shape[1]),
            )
        ]
        super().__init__(path, times, metadata, (shape[0], shape[1]))

    def _raw_frame(self) -> np.ndarray:
        if self._frame is None:
            self._frame, _ = extract_2d_from_hdu(self.source, self._hdu_index)
        return self._frame

    def get_map(self, index: int) -> Any | None:
        if index != 0:
            raise IndexError(index)
        if self._map is None:
            self._map, self.map_notice, self.aia_prepared = make_solar_map(
                self._raw_frame(), self._header, observation_time=self.get_time(0), prepare_aia=self.prepare_aia
            )
            if self._map is not None and self.aia_prepared:
                self._frame = np.asarray(self._map.data)
                self.shape = self._frame.shape
        return self._map

    def get_frame(self, index: int) -> np.ndarray:
        if index != 0:
            raise IndexError(index)
        if self.prepare_aia:
            self.get_map(0)
        return self._raw_frame()

    def get_wcs(self, index: int) -> WCS | None:
        if index != 0:
            raise IndexError(index)
        smap = self.get_map(0)
        return smap.wcs if smap is not None else spatial_wcs(self._header)

    def project_descriptor(self) -> dict[str, Any]:
        output = super().project_descriptor()
        output["prepare_aia"] = self.prepare_aia
        return output
