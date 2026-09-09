"""Create known-truth synthetic FITS data for manual and automated validation.

The moving Gaussian follows the same smooth reference path used in tests. Its
time-distance ridge has known speed 1.1 pixel/s, so a user can independently
verify both curved extraction and the slope tool in the GUI.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from astropy.io import fits
from astropy.time import Time, TimeDelta

# Permit the documented direct invocation "python tests/data_generator.py".
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.paths.base import PathGeometry
from app.paths.geometry import sample_path_geometry

TRUTH_SPEED_PIXEL_PER_SECOND = 1.1
SHAPE = (256, 256)
CONTROL_POINTS = np.array([[22.0, 38.0], [70.0, 43.0], [126.0, 96.0], [208.0, 142.0]])


def _header(obstime: Time) -> fits.Header:
    header = fits.Header()
    header["DATE-OBS"] = obstime.isot
    header["INSTRUME"] = "STDE-SYNTH"
    header["OBSERVAT"] = "Synthetic Observatory"
    header["WAVELNTH"] = 171
    header["BUNIT"] = "arb"
    header["CTYPE1"] = "HPLN-TAN"
    header["CTYPE2"] = "HPLT-TAN"
    header["CUNIT1"] = "arcsec"
    header["CUNIT2"] = "arcsec"
    header["CRPIX1"] = 128.0
    header["CRPIX2"] = 128.0
    header["CRVAL1"] = 0.0
    header["CRVAL2"] = 0.0
    header["CDELT1"] = 0.6
    header["CDELT2"] = 0.6
    header["HGLN_OBS"] = 0.0
    header["HGLT_OBS"] = 0.0
    header["DSUN_OBS"] = 149_597_870_700.0
    header["RSUN_REF"] = 695_700_000.0
    return header


def moving_curve_frames(times_seconds: np.ndarray, shape: tuple[int, int] = SHAPE) -> np.ndarray:
    """Return noisy frames with a Gaussian feature moving along a curved path."""
    geometry = PathGeometry("smooth", CONTROL_POINTS.copy(), sample_step_pixel=0.4, smoothing=0.0)
    samples, distance = sample_path_geometry(geometry)
    y, x = np.indices(shape, dtype=float)
    rng = np.random.default_rng(20260908)
    frames = np.empty((len(times_seconds), *shape), dtype=np.float32)
    for index, seconds in enumerate(times_seconds):
        target = 12.0 + TRUTH_SPEED_PIXEL_PER_SECOND * seconds
        target = min(target, distance[-1] - 8.0)
        cx = np.interp(target, distance, samples[:, 0])
        cy = np.interp(target, distance, samples[:, 1])
        gaussian = 500.0 * np.exp(-((x - cx) ** 2 + (y - cy) ** 2) / (2 * 2.4**2))
        background = 10.0 + 0.025 * x + 0.01 * y
        frames[index] = background + gaussian + rng.normal(0.0, 0.8, size=shape)
    return frames


def generate(output: str | Path, n_frames: int = 100) -> dict[str, Path]:
    """Write a FITS folder plus regular and irregular-cadence cubes."""
    destination = Path(output)
    folder = destination / "fits_folder_irregular"
    folder.mkdir(parents=True, exist_ok=True)
    start = Time("2026-05-10T04:23:12.350", scale="utc")
    irregular_seconds = np.concatenate(([0.0], np.cumsum(np.where(np.arange(1, n_frames) % 4 == 0, 1.6, 1.0))))
    frames = moving_curve_frames(irregular_seconds)
    for index, frame in enumerate(frames):
        timestamp = start + TimeDelta(irregular_seconds[index], format="sec")
        fits.PrimaryHDU(frame, header=_header(timestamp)).writeto(folder / f"solar_{index:03d}.fits", overwrite=True)

    regular_seconds = np.arange(n_frames, dtype=float)
    regular_frames = moving_curve_frames(regular_seconds)
    cube_header = _header(start)
    cube_header["CTYPE3"] = "TIME"
    cube_header["CUNIT3"] = "s"
    cube_header["CRPIX3"] = 1.0
    cube_header["CRVAL3"] = 0.0
    cube_header["CDELT3"] = 1.0
    cube_path = destination / "moving_curve_cube_axis0.fits"
    fits.PrimaryHDU(regular_frames, header=cube_header).writeto(cube_path, overwrite=True)
    return {"folder": folder, "cube": cube_path}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="tests/generated")
    parser.add_argument("--frames", type=int, default=100)
    arguments = parser.parse_args()
    created = generate(arguments.output, arguments.frames)
    print("Created:")
    for name, path in created.items():
        print(f"  {name}: {path}")
