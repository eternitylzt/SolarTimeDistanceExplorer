"""Optional official SunPy nearest-pixel backend for standard Map paths."""

from __future__ import annotations

from typing import Any

import numpy as np


def sample_map_coordinate_path(smap: Any, skycoord_path: Any) -> tuple[Any, np.ndarray]:
    """Use SunPy's official pixelate and sampling API for a zero-width path.

    This compatibility backend is intentionally restricted to nearest-pixel,
    centreline-only extraction. Finite widths, smooth sub-pixel sampling and
    NaN-preserving out-of-FOV policy use the general SciPy backend instead.
    """
    from sunpy.map import pixelate_coord_path, sample_at_coords

    coords = pixelate_coord_path(smap, skycoord_path)
    values = sample_at_coords(smap, coords)
    return coords, np.asarray(getattr(values, "value", values), dtype=float)
