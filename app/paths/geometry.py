"""Line/polyline/spline evaluation with explicit arc-length resampling."""

from __future__ import annotations

import numpy as np
from scipy.interpolate import splprep, splev

from app.paths.base import PathGeometry


def cumulative_distance(points: np.ndarray) -> np.ndarray:
    """Return cumulative Euclidean arc length for N image x,y points."""
    points = np.asarray(points, dtype=float)
    if len(points) == 0:
        return np.empty(0, dtype=float)
    if len(points) == 1:
        return np.zeros(1, dtype=float)
    return np.concatenate(([0.0], np.cumsum(np.hypot(*(np.diff(points, axis=0).T)))))


def resample_by_arclength(points: np.ndarray, step: float) -> tuple[np.ndarray, np.ndarray]:
    """Resample a dense polyline at uniform physical pixel arc-length intervals.

    The spline parameter is never exposed as distance. Endpoint inclusion avoids
    silently shortening a user-selected slit.
    """
    points = np.asarray(points, dtype=float)
    if len(points) < 2:
        raise ValueError("At least two points are needed to make a path.")
    if step <= 0:
        raise ValueError("Spatial sample step must be positive.")
    original_s = cumulative_distance(points)
    length = original_s[-1]
    if not np.isfinite(length) or length <= 0:
        raise ValueError("Path length must be positive.")
    samples_s = np.arange(0.0, length, step)
    if samples_s.size == 0 or not np.isclose(samples_s[-1], length):
        samples_s = np.append(samples_s, length)
    x = np.interp(samples_s, original_s, points[:, 0])
    y = np.interp(samples_s, original_s, points[:, 1])
    return np.column_stack((x, y)), samples_s


def _densify_spline(points: np.ndarray, smoothing: float, step: float) -> np.ndarray:
    """Evaluate an interpolating/smoothed B-spline densely before arc sampling."""
    if len(points) < 3:
        return points
    # splprep can become singular for repeated mouse clicks; remove duplicates.
    unique = np.vstack((points[0], points[1:][np.any(np.diff(points, axis=0) != 0, axis=1)]))
    if len(unique) < 3:
        return unique
    degree = min(3, len(unique) - 1)
    chord = cumulative_distance(unique)
    chord /= chord[-1]
    try:
        tck, _ = splprep([unique[:, 0], unique[:, 1]], u=chord, s=max(0.0, smoothing), k=degree)
        estimated = max(int(cumulative_distance(unique)[-1] / max(step, 0.25) * 4), 100)
        parameter = np.linspace(0.0, 1.0, estimated)
        x, y = splev(parameter, tck)
        return np.column_stack((x, y))
    except Exception:
        return unique


def sample_path_geometry(geometry: PathGeometry) -> tuple[np.ndarray, np.ndarray]:
    """Create centerline x,y samples and pixel arc length for a PathGeometry."""
    if not geometry.complete:
        raise ValueError("Finish at least two path points before generating a diagram.")
    points = geometry.control_points_pixel
    if geometry.path_type == "smooth":
        points = _densify_spline(points, geometry.smoothing, geometry.sample_step_pixel)
    samples, distances = resample_by_arclength(points, geometry.sample_step_pixel)
    geometry.cache_pixel_samples(samples)
    return samples, distances


def local_normals(points: np.ndarray) -> np.ndarray:
    """Compute unit image-plane normals from centered local path tangents.

    For image x,y points, a tangent (tx, ty) has normal (-ty, tx). Degenerate
    zero-gradient positions reuse the preceding nonzero tangent to maintain a
    continuous width strip.
    """
    points = np.asarray(points, dtype=float)
    if len(points) < 2:
        raise ValueError("At least two samples are needed for a normal.")
    tangent = np.gradient(points, axis=0)
    norm = np.hypot(tangent[:, 0], tangent[:, 1])
    for index in range(len(norm)):
        if norm[index] <= np.finfo(float).eps:
            tangent[index] = tangent[index - 1] if index else np.array([1.0, 0.0])
    norm = np.hypot(tangent[:, 0], tangent[:, 1])
    unit = tangent / norm[:, None]
    return np.column_stack((-unit[:, 1], unit[:, 0]))
