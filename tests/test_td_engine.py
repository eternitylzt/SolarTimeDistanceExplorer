from __future__ import annotations

from pathlib import Path

import numpy as np

from app.data.fits_folder import FitsFolderDataset
from app.paths.base import PathGeometry
from app.processing.td_generator import TDConfig, generate_time_distance
from tests.data_generator import CONTROL_POINTS, TRUTH_SPEED_PIXEL_PER_SECOND, generate


def test_end_to_end_curved_td_ridge_recovers_known_speed(tmp_path: Path) -> None:
    generated = generate(tmp_path, n_frames=70)
    dataset = FitsFolderDataset(generated["folder"])
    path = PathGeometry(
        "smooth",
        CONTROL_POINTS.copy(),
        width=3.0,
        integration_method="mean",
        interpolation="linear",
        sample_step_pixel=1.0,
        smoothing=0.0,
    )
    result = generate_time_distance(dataset, path, TDConfig(distance_unit="pixel"))
    ridge = result.distance[np.nanargmax(result.matrix, axis=0)]
    elapsed = dataset.times.unix - dataset.times.unix[0]  # type: ignore[union-attr]
    coefficient = np.polyfit(elapsed, ridge, 1)[0]
    assert np.isclose(coefficient, TRUTH_SPEED_PIXEL_PER_SECOND, rtol=0.10)
    assert result.shape == (len(result.distance), dataset.n_frames)


def test_world_path_tracks_wcs_offset(tmp_path: Path) -> None:
    from astropy.wcs import WCS

    path = PathGeometry("line", np.array([[10.0, 10.0], [20.0, 10.0]]))
    header = {
        "NAXIS": 2, "NAXIS1": 100, "NAXIS2": 100,
        "CTYPE1": "RA---TAN", "CTYPE2": "DEC--TAN",
        "CUNIT1": "deg", "CUNIT2": "deg", "CRPIX1": 50, "CRPIX2": 50,
        "CRVAL1": 0, "CRVAL2": 0, "CDELT1": 0.01, "CDELT2": 0.01,
    }
    first = WCS(header)
    samples = np.array([[10.0, 10.0], [20.0, 10.0]])
    path.capture_world_samples(first, samples)
    header["CRPIX1"] = 55
    shifted = path.pixel_samples_for_wcs(WCS(header))
    assert shifted is not None
    assert np.allclose(shifted[:, 0], samples[:, 0] + 5.0, atol=1e-6)
