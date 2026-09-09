from __future__ import annotations

import numpy as np

from app.paths.base import PathGeometry
from app.paths.geometry import sample_path_geometry
from app.paths.sampling import sample_path_width


def test_horizontal_subpixel_line_matches_linear_image() -> None:
    y, x = np.indices((40, 60), dtype=float)
    frame = 2.0 * x + 3.0 * y
    path = PathGeometry("line", np.array([[5.2, 10.5], [45.2, 10.5]]), sample_step_pixel=1.0)
    points, _ = sample_path_geometry(path)
    sampled = sample_path_width(frame, points, 1.0, interpolation="linear")
    assert np.allclose(sampled, 2.0 * points[:, 0] + 3.0 * points[:, 1], atol=1e-8)


def test_width_average_samples_normal_not_display_linewidth() -> None:
    y, _ = np.indices((80, 80), dtype=float)
    path = PathGeometry("line", np.array([[10.0, 40.0], [70.0, 40.0]]), sample_step_pixel=1.0)
    points, _ = sample_path_geometry(path)
    result = sample_path_width(y, points, width_pixel=5.0, integration="mean", interpolation="linear")
    assert np.allclose(result, 40.0, atol=1e-8)


def test_out_of_fov_stays_nan() -> None:
    frame = np.ones((20, 20))
    path = PathGeometry("line", np.array([[-5.0, 10.0], [5.0, 10.0]]), sample_step_pixel=1.0)
    points, _ = sample_path_geometry(path)
    values = sample_path_width(frame, points, 1.0)
    assert np.isnan(values[0])
    assert np.isfinite(values[-1])


def test_smooth_path_uses_arclength_not_spline_parameter() -> None:
    path = PathGeometry(
        "smooth",
        np.array([[2.0, 2.0], [4.0, 28.0], [38.0, 30.0], [44.0, 4.0]]),
        sample_step_pixel=1.0,
    )
    points, distances = sample_path_geometry(path)
    increments = np.hypot(*(np.diff(points, axis=0).T))
    assert np.allclose(increments[:-1], 1.0, atol=0.03)
    assert np.all(np.diff(distances) > 0)
