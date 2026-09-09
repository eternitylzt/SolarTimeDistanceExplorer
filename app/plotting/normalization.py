"""Astropy visualization intervals/stretch wrappers for Matplotlib."""

from __future__ import annotations

import numpy as np
from astropy.visualization import (
    AsymmetricPercentileInterval,
    AsinhStretch,
    ImageNormalize,
    LinearStretch,
    LogStretch,
    ManualInterval,
    MinMaxInterval,
    PercentileInterval,
    PowerStretch,
    SqrtStretch,
    ZScaleInterval,
)


def make_norm(
    data: np.ndarray,
    mode: str = "percentile",
    stretch: str = "linear",
    vmin: float | None = None,
    vmax: float | None = None,
    low_percent: float = 1.0,
    high_percent: float = 99.0,
) -> ImageNormalize:
    """Build an Astropy scientific image normalization without altering data."""
    array = np.asarray(data)
    # Display normalization does not need to scan/copy every 4096² AIA pixel.
    # A deterministic strided sample caps interactive work near one million
    # values while retaining the full-resolution array for rendering/science.
    stride = max(1, int(np.ceil(np.sqrt(array.size / 1_000_000))))
    sampled = array[::stride, ::stride] if array.ndim == 2 else array.ravel()[::stride]
    finite = np.asarray(sampled)[np.isfinite(sampled)]
    if finite.size == 0:
        finite = np.array([0.0, 1.0])
    if mode == "manual" and vmin is not None and vmax is not None:
        lower = float(vmin)
        upper = float(vmax)
        if upper <= lower:
            upper = float(np.nextafter(lower, np.inf))
        interval = ManualInterval(lower, upper)
    elif mode == "minmax":
        interval = MinMaxInterval()
    elif mode == "zscale":
        interval = ZScaleInterval()
    else:
        lower_percent = float(np.clip(low_percent, 0.0, 99.999))
        upper_percent = float(np.clip(high_percent, lower_percent + 0.001, 100.0))
        interval = AsymmetricPercentileInterval(lower_percent, upper_percent)
    stretches = {
        "linear": LinearStretch(),
        "log": LogStretch(),
        "sqrt": SqrtStretch(),
        "asinh": AsinhStretch(),
        "power": PowerStretch(2.0),
    }
    return ImageNormalize(finite, interval=interval, stretch=stretches[stretch], clip=True)
