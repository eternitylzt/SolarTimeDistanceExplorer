from __future__ import annotations

from pathlib import Path

import numpy as np
from astropy.io import fits
from astropy.time import Time

from app.data.fits_cube import FitsCubeDataset
from app.data.fits_folder import FitsFolderDataset
from app.data.time_parser import parse_header_time
from tests.data_generator import generate


def test_folder_sorts_by_observation_time_and_detects_irregularity(tmp_path: Path) -> None:
    generated = generate(tmp_path, n_frames=8)
    dataset = FitsFolderDataset(generated["folder"])
    assert dataset.n_frames == 8
    assert dataset.times is not None
    assert np.all(np.diff(dataset.times.unix) > 0)
    assert dataset.summary().cadence_type == "irregular"


def test_folder_reports_scan_progress_and_can_clear_frame_cache(tmp_path: Path) -> None:
    generated = generate(tmp_path, n_frames=5)
    updates: list[tuple[int, int, str]] = []
    dataset = FitsFolderDataset(
        generated["folder"], prepare_aia=False,
        progress=lambda current, total, name: updates.append((current, total, name)),
    )
    assert len(updates) == 5
    assert updates[-1][:2] == (5, 5)
    dataset.get_frame(0)
    assert len(dataset._cache) == 1
    dataset.clear_cache(include_disk=True)
    assert len(dataset._cache) == 0
    assert len(dataset._map_cache) == 0
    dataset.close()


def test_folder_reads_irregular_times_from_primary_headers_and_extension_wcs(tmp_path: Path) -> None:
    """Primary timing plus image-extension WCS is common in solar FITS archives."""
    start = Time("2026-05-10T04:23:12.350", scale="utc")
    for sequence, seconds in enumerate((20.0, 0.0, 7.0)):
        primary_header = fits.Header({"DATE-OBS": (start.unix + seconds)})
        primary_header["MJD-OBS"] = (start.unix + seconds) / 86400.0 + 40587.0
        primary_header.remove("DATE-OBS")  # Exercise numeric MJD in the primary HDU.
        image_header = fits.Header(
            {
                "CTYPE1": "HPLN-TAN",
                "CTYPE2": "HPLT-TAN",
                "CUNIT1": "arcsec",
                "CUNIT2": "arcsec",
                "CRPIX1": 4.5,
                "CRPIX2": 4.5,
                "CRVAL1": 0.0,
                "CRVAL2": 0.0,
                "CDELT1": 0.6,
                "CDELT2": 0.6,
                "HGLN_OBS": 0.0,
                "HGLT_OBS": 0.0,
                "DSUN_OBS": 149_597_870_700.0,
                "RSUN_REF": 695_700_000.0,
            }
        )
        target = tmp_path / f"unordered_{sequence}.fits"
        fits.HDUList(
            [fits.PrimaryHDU(header=primary_header), fits.ImageHDU(np.ones((8, 8)), header=image_header)]
        ).writeto(target)

    dataset = FitsFolderDataset(tmp_path)
    assert dataset.times is not None
    assert np.allclose(np.diff(dataset.times.unix), [7.0, 13.0], atol=1e-5)
    assert dataset.summary().cadence_type == "irregular"
    solar_map = dataset.get_map(0)
    assert solar_map is not None
    assert solar_map.coordinate_frame.name == "helioprojective"
    assert np.isclose(solar_map.date.utc.unix, dataset.times[0].utc.unix, atol=1e-5)


def test_solar_archive_time_formats_are_normalized_to_utc() -> None:
    parsed = parse_header_time({"T_REC": "2026.05.10_04:23:12_TAI"})
    assert parsed is not None
    assert parsed.scale == "utc"
    assert parsed.isot == "2026-05-10T04:22:35.000"
    split = parse_header_time({"DATE": "2026/05/10", "TIME-OBS": "04:23:12.350"})
    assert split is not None
    assert split.isot == "2026-05-10T04:23:12.350"


def test_cube_axis0_and_time_wcs(tmp_path: Path) -> None:
    generated = generate(tmp_path, n_frames=6)
    dataset = FitsCubeDataset(generated["cube"])
    assert dataset.time_axis == 0
    assert dataset.n_frames == 6
    assert dataset.get_frame(2).shape == (256, 256)
    assert dataset.times is not None
    assert np.isclose((dataset.times[3] - dataset.times[0]).sec, 3.0)


def test_cube_axis_selection_is_explicit_for_other_orders(tmp_path: Path) -> None:
    array = np.arange(4 * 5 * 6, dtype=np.float32).reshape(4, 5, 6)
    header = fits.Header()
    header["CTYPE1"] = "TIME"
    header["CUNIT1"] = "s"
    header["CRVAL1"] = 0
    header["CRPIX1"] = 1
    header["CDELT1"] = 2
    header["DATE-OBS"] = "2026-01-01T00:00:00"
    target = tmp_path / "axis2.fits"
    fits.PrimaryHDU(array, header=header).writeto(target)
    dataset = FitsCubeDataset(target)
    assert dataset.time_axis == 2
    assert dataset.get_frame(1).shape == (4, 5)
    assert dataset.times is not None
