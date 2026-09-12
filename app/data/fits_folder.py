"""Lazy reader for folders containing individual 2-D FITS observations."""

from __future__ import annotations

import logging
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Callable

import numpy as np
from astropy.time import Time
from astropy.wcs import WCS

from app.data.base import TimeSeriesDataset
from app.data.cache import LRUFrameCache
from app.data.fits_common import (
    extract_2d_from_hdu,
    first_image_header,
    header_exposure_seconds,
    spatial_wcs,
)
from app.data.metadata import FrameMetadata
from app.data.solar_map import make_solar_map
from app.data.time_parser import parse_header_time
from app.utils.natural_sort import natural_key

LOG = logging.getLogger(__name__)
FITS_SUFFIXES = {".fits", ".fit", ".fts"}


class FitsFolderDataset(TimeSeriesDataset):
    """Header-scanned, LRU-cached FITS folder sequence."""

    source_type = "fits_folder"

    def __init__(
        self,
        directory: str | Path,
        cache_size: int = 12,
        prepare_aia: bool = True,
        progress: Callable[[int, int, str], None] | None = None,
    ) -> None:
        directory = Path(directory)
        files = sorted(
            (path for path in directory.iterdir() if path.is_file() and path.suffix.lower() in FITS_SUFFIXES),
            key=natural_key,
        )
        if not files:
            raise ValueError("The selected folder contains no .fits, .fit, or .fts files.")

        scanned: list[tuple[Path, int, FrameMetadata]] = []
        for scan_index, path in enumerate(files, start=1):
            try:
                hdu, header, shape = first_image_header(path)
                if len(shape) != 2:
                    LOG.info("Skipping non-2D folder member %s", path.name)
                    continue
                data_shape = (shape[-2], shape[-1])
                metadata = FrameMetadata(
                    source=str(path),
                    time=parse_header_time(header),
                    header=dict(header),
                    exposure_seconds=header_exposure_seconds(header),
                    shape=data_shape,
                )
                scanned.append((path, hdu, metadata))
            except Exception:
                LOG.exception("Cannot scan FITS header: %s", path)
            finally:
                if progress is not None:
                    progress(scan_index, len(files), path.name)

        if not scanned:
            raise ValueError("No readable two-dimensional FITS images were found.")
        expected_shape = scanned[0][2].shape
        scanned = [item for item in scanned if item[2].shape == expected_shape]
        if not scanned:
            raise ValueError("No consistently shaped FITS images were found.")

        timed_count = sum(item[2].time is not None for item in scanned)
        if 0 < timed_count < len(scanned):
            missing = [item[0].name for item in scanned if item[2].time is None]
            preview = ", ".join(missing[:5])
            more = f" (and {len(missing) - 5} more)" if len(missing) > 5 else ""
            raise ValueError(
                f"Parsed observation times from {timed_count} of {len(scanned)} FITS files, "
                f"but these files have no readable time: {preview}{more}. "
                "The sequence was not assigned an artificial fixed cadence."
            )
        all_have_time = timed_count == len(scanned)
        if all_have_time:
            scanned.sort(key=lambda item: float(item[2].time.unix))
            times: Time | None = Time([item[2].time for item in scanned])
        else:
            scanned.sort(key=lambda item: natural_key(item[0]))
            times = None

        self._files = [item[0] for item in scanned]
        self._hdu_indices = [item[1] for item in scanned]
        self._cache: LRUFrameCache[np.ndarray] = LRUFrameCache(cache_size)
        self._wcs_cache: dict[int, WCS | None] = {}
        # Prepared AIA maps are the expensive representation.  Keep the same
        # user-controlled LRU depth as decoded frames; the previous four-map
        # cap caused a full FITS reopen/Map rebuild on nearly every animation
        # cycle even after all frames had already been prepared.
        self._map_cache: LRUFrameCache[Any] = LRUFrameCache(cache_size)
        self.prepare_aia = prepare_aia
        self.map_notice: str | None = None
        self.aia_prepared = False
        self._aia_prepared_indices: set[int] = set()
        self._aia_cache_dir = TemporaryDirectory(prefix="stde_aia_prepared_")
        super().__init__(directory, times, [item[2] for item in scanned], expected_shape)  # type: ignore[arg-type]

    def get_frame(self, index: int) -> np.ndarray:
        """Read a requested image only once while it is resident in the LRU."""
        self._validate_index(index)
        if self.prepare_aia:
            mapped = self.get_map(index)
            if mapped is not None:
                return np.asarray(mapped.data)
        return self._raw_frame(index)

    def _raw_frame(self, index: int) -> np.ndarray:
        """Read unregistered source pixels without recursively constructing a map."""
        cached = self._cache.get(index)
        if cached is not None:
            return cached
        data, _ = extract_2d_from_hdu(self._files[index], self._hdu_indices[index])
        self._cache.put(index, data)
        return data

    def get_wcs(self, index: int) -> WCS | None:
        """Create spatial WCS lazily from the scanned header."""
        self._validate_index(index)
        if index not in self._wcs_cache:
            smap = self.get_map(index)
            self._wcs_cache[index] = smap.wcs if smap is not None else spatial_wcs(self._frame_metadata[index].header)
        return self._wcs_cache[index]

    def get_map(self, index: int) -> Any | None:
        """Return the SunPy equivalent of SSW ``fits2map`` for this frame.

        Building from cached data plus the merged header supports image
        extensions while retaining lazy folder loading.
        """
        self._validate_index(index)
        cached = self._map_cache.get(index)
        if cached is not None:
            return cached
        prepared_path = Path(self._aia_cache_dir.name) / f"frame_{index:06d}.fits"
        if prepared_path.exists():
            try:
                from astropy.io import fits
                import sunpy.map

                # memmap=False is essential on Windows: otherwise an LRU-held
                # Map keeps the temporary FITS file locked until process exit.
                with fits.open(prepared_path, memmap=False) as hdul:
                    cached_data = np.array(hdul[0].data, copy=True)
                    cached_header = hdul[0].header.copy()
                result = sunpy.map.Map((cached_data, cached_header))
                self._aia_prepared_indices.add(index)
                self._map_cache.put(index, result)
                return result
            except Exception:
                LOG.warning("Could not reopen temporary AIA cache %s", prepared_path, exc_info=True)
        try:
            metadata = self._frame_metadata[index]
            result, notice, prepared = make_solar_map(
                self._raw_frame(index),
                metadata.header,
                observation_time=metadata.time,
                prepare_aia=self.prepare_aia,
            )
            if notice:
                self.map_notice = notice
            self.aia_prepared = self.aia_prepared or prepared
            if result is None:
                return None
            if prepared:
                self._aia_prepared_indices.add(index)
                # Do not retain both the raw level-1 array and registered map.
                self._cache.pop(index)
                try:
                    result.save(prepared_path, overwrite=True)
                except Exception:
                    LOG.warning("Could not write temporary prepared AIA cache", exc_info=True)
            self._map_cache.put(index, result)
            return result
        except Exception:
            LOG.debug("SunPy Map unavailable for %s", self._files[index], exc_info=True)
            return None

    def project_descriptor(self) -> dict[str, Any]:
        """Describe this directory source for project reopening."""
        output = super().project_descriptor()
        output["cache_size"] = self._cache.max_items
        output["prepare_aia"] = self.prepare_aia
        return output

    def set_cache_size(self, size: int) -> None:
        """Resize raw/prepared in-memory LRUs without discarding disk prep cache."""
        self._cache.resize(size)
        self._map_cache.resize(size)

    def set_cache_budget(self, megabytes: int) -> None:
        """Split a conservative payload budget between raw frames and Maps.

        Shared raw/Map arrays may be counted twice; process memory also includes
        active calculations, GUI artists and Python overhead outside this budget.
        """
        budget = max(1, int(megabytes)) * 1024**2 // 2
        self._cache.set_byte_limit(budget)
        self._map_cache.set_byte_limit(budget)

    def cache_stats(self) -> dict[str, int]:
        return {"bytes": self._cache.used_bytes + self._map_cache.used_bytes,
                "budget": self._cache.max_bytes + self._map_cache.max_bytes,
                "hits": self._cache.hits + self._map_cache.hits,
                "misses": self._cache.misses + self._map_cache.misses}

    def clear_cache(self, *, include_disk: bool = True) -> None:
        """Release decoded/prepared frames and optionally reset the session prep store."""
        self._cache.clear()
        self._map_cache.clear()
        self._wcs_cache.clear()
        if include_disk:
            self._aia_cache_dir.cleanup()
            self._aia_cache_dir = TemporaryDirectory(prefix="stde_aia_prepared_")
            self._aia_prepared_indices.clear()
            self.aia_prepared = False

    def close(self) -> None:
        """Release all temporary data owned by this source."""
        self._cache.clear()
        self._map_cache.clear()
        self._wcs_cache.clear()
        self._aia_prepared_indices.clear()
        self._aia_cache_dir.cleanup()

    def _validate_index(self, index: int) -> None:
        if not 0 <= index < self.n_frames:
            raise IndexError(f"Frame {index} is outside 0..{self.n_frames - 1}")
