"""WCS coordinate transformation helpers kept outside GUI code."""

from __future__ import annotations

import numpy as np
from astropy.wcs import WCS


def pixel_to_world_values(wcs: WCS, points: np.ndarray) -> np.ndarray:
    """Transform N image x,y samples to first two WCS world-value axes."""
    values = wcs.pixel_to_world_values(points[:, 0], points[:, 1])
    return np.column_stack((np.asarray(values[0]), np.asarray(values[1])))


def world_to_pixel_values(wcs: WCS, values: np.ndarray) -> np.ndarray:
    """Transform N first-two WCS world values to image x,y samples."""
    x, y = wcs.world_to_pixel_values(values[:, 0], values[:, 1])
    return np.column_stack((np.asarray(x), np.asarray(y)))
