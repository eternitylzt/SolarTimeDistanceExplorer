"""Finite-width, sub-pixel numerical extraction for normal arrays and WCS frames."""

from __future__ import annotations

import warnings

import numpy as np
from scipy.ndimage import map_coordinates

from app.paths.geometry import local_normals


def interpolation_order(name: str) -> int:
    """Map visible interpolation names to SciPy spline orders."""
    return {"nearest": 0, "linear": 1, "cubic": 3}[name]


def width_offsets(width_pixel: float, samples: int | None = None) -> np.ndarray:
    """Generate symmetric normal offsets for a physical scientific slit width.

    Width <= 1 means one central sub-pixel sample, matching the common
    one-pixel-slit expectation. Wider slits include both boundaries and enough
    intermediate points for interpolation; a noninteger width remains continuous.
    """
    if width_pixel <= 1.0:
        return np.array([0.0])
    count = samples or max(3, int(np.ceil(width_pixel)) + 1)
    return np.linspace(-width_pixel / 2.0, width_pixel / 2.0, count)


def sample_path_width(
    frame: np.ndarray,
    center_points: np.ndarray,
    width_pixel: float,
    integration: str = "mean",
    interpolation: str = "linear",
    width_samples: int | None = None,
) -> np.ndarray:
    """Sample and integrate a finite-width slit in a 2-D array.

    Given centerline r(s) and local unit normal N(s), values are sampled at
    r(s) + nN(s). The discrete average is

        I(s,t) = 1/N sum_j I(x(s)+n_j*Nx(s), y(s)+n_j*Ny(s), t).

    Coordinates are passed to SciPy as (row=y, column=x), in constant mode with
    NaN outside the detector. Consequently out-of-FOV positions never become
    edge pixels. NaN image values remain ignored by reductions where possible.
    """
    image = np.asarray(frame, dtype=float)
    if image.ndim != 2:
        raise ValueError("Path sampling requires a 2-D frame.")
    points = np.asarray(center_points, dtype=float)
    normals = local_normals(points)
    offsets = width_offsets(float(width_pixel), width_samples)
    x = points[None, :, 0] + offsets[:, None] * normals[None, :, 0]
    y = points[None, :, 1] + offsets[:, None] * normals[None, :, 1]
    sampled = map_coordinates(
        image,
        np.vstack((y.ravel(), x.ravel())),
        order=interpolation_order(interpolation),
        mode="constant",
        cval=np.nan,
        prefilter=interpolation == "cubic",
    ).reshape(x.shape)
    reducers = {
        "mean": lambda a: np.nanmean(a, axis=0),
        "median": lambda a: np.nanmedian(a, axis=0),
        "sum": lambda a: np.nansum(a, axis=0),
        "maximum": lambda a: np.nanmax(a, axis=0),
        "minimum": lambda a: np.nanmin(a, axis=0),
    }
    if integration not in reducers:
        raise ValueError(f"Unknown width integration method: {integration}")
    with np.errstate(all="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        output = reducers[integration](sampled)
    output[np.all(~np.isfinite(sampled), axis=0)] = np.nan
    return output


def width_boundaries(center_points: np.ndarray, width_pixel: float) -> tuple[np.ndarray, np.ndarray]:
    """Return left/right strips for an honest visualisation of scientific width."""
    normals = local_normals(center_points)
    half = max(0.0, width_pixel) / 2.0
    return center_points - half * normals, center_points + half * normals
