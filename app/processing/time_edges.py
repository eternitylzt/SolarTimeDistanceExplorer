"""True temporal bin edges for irregular cadence rendering."""

from __future__ import annotations

import numpy as np


def gap_aware_edges(centers: np.ndarray, matrix: np.ndarray, factor: float = 5.0) -> tuple[np.ndarray, np.ndarray]:
    """Insert NaN columns across intervals > factor*median positive cadence.

    Adjacent observations keep half a median cadence on the gap-facing side.
    Gap locations are visual hypotheses, not inferred exposure durations.
    """
    x = np.asarray(centers, float)
    edges = centers_to_edges(x)
    if len(x) < 3:
        return edges, matrix
    dt = np.diff(x)
    cadence = float(np.median(dt))
    gaps = set(np.flatnonzero(dt > max(1.01, factor)*cadence))
    output_edges = [edges[0]]
    columns = []
    for i in range(len(x)):
        right = x[i]+cadence/2 if i in gaps else edges[i+1]
        columns.append(matrix[:, i]); output_edges.append(right)
        if i in gaps:
            columns.append(np.full(matrix.shape[0], np.nan))
            output_edges.append(x[i+1]-cadence/2)
    return np.asarray(output_edges), np.column_stack(columns)
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
