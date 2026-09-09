from __future__ import annotations

from pathlib import Path

import numpy as np
from astropy.io import fits
from astropy.time import Time, TimeDelta

import app.data.fits_folder as folder_module
from app.data.fits_folder import FitsFolderDataset
from app.data.solar_map import make_solar_map as real_make_solar_map
from tests.data_generator import _header


def test_prepared_map_disk_cache_avoids_reprocessing_after_lru_eviction(
    tmp_path: Path, monkeypatch,
) -> None:
    start = Time("2026-01-01T00:00:00")
    for index in range(3):
        fits.PrimaryHDU(
            np.full((16, 16), index, dtype=np.float32),
            header=_header(start + TimeDelta(index, format="sec")),
        ).writeto(tmp_path / f"frame_{index}.fits")

    calls: list[int] = []

    def prepared(data, header, **kwargs):
        calls.append(int(np.asarray(data)[0, 0]))
        smap, notice, _ = real_make_solar_map(data, header, prepare_aia=False, **{k: v for k, v in kwargs.items() if k != "prepare_aia"})
        assert smap is not None
        return smap, notice, True

    monkeypatch.setattr(folder_module, "make_solar_map", prepared)
    dataset = FitsFolderDataset(tmp_path, cache_size=2, prepare_aia=True)
    for index in (0, 1, 2, 0):
        dataset.get_frame(index)
    assert calls == [0, 1, 2]
    assert np.all(dataset.get_frame(0) == 0)
