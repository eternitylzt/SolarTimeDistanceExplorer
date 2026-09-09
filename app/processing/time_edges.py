"""True temporal bin edges for irregular cadence rendering."""

from __future__ import annotations

import numpy as np
from astropy.time import Time


def centers_to_edges(centers: np.ndarray) -> np.ndarray:
    """Convert sorted numeric bin centers to N+1 midpoint/extrapolated edges.

    A one-point sequence receives a unit-wide bin. The routine supports Unix
    seconds, Matplotlib date numbers, distance, and any other linear coordinate.
    """
    values = np.asarray(centers, dtype=float)
    if values.ndim != 1 or values.size == 0:
        raise ValueError("At least one center is required.")
    if values.size == 1:
        return np.array([values[0] - 0.5, values[0] + 0.5])
    gaps = np.diff(values)
    if np.any(gaps <= 0):
        raise ValueError("Time centers must be strictly increasing.")
    middle = values[:-1] + gaps / 2.0
    return np.concatenate(([values[0] - gaps[0] / 2.0], middle, [values[-1] + gaps[-1] / 2.0]))


def time_edges_unix(times: Time) -> np.ndarray:
    """Return bin edges in Unix seconds while preserving irregular observation gaps."""
    return centers_to_edges(np.asarray(times.unix, dtype=float))
