from __future__ import annotations

import numpy as np

from app.processing.time_edges import centers_to_edges


def test_irregular_centers_become_true_midpoint_edges() -> None:
    centers = np.array([0.0, 10.0, 25.0, 60.0])
    assert np.allclose(centers_to_edges(centers), [-5.0, 5.0, 17.5, 42.5, 77.5])


def test_centers_require_strict_increasing_order() -> None:
    import pytest

    with pytest.raises(ValueError):
        centers_to_edges(np.array([0.0, 10.0, 10.0]))
