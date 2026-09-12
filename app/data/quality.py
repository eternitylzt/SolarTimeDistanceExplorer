"""Header-only quality reporting; never invent missing observation metadata."""
from __future__ import annotations

from collections import Counter
from typing import Any, Callable
import numpy as np

from app.data.base import TimeSeriesDataset
from app.data.time_parser import TIME_KEYS, MJD_KEYS
from app.data.fits_common import spatial_wcs


def quality_report(dataset: TimeSeriesDataset, progress: Callable[[int, int], None] | None = None,
                   cancelled: Callable[[], bool] | None = None) -> dict[str, Any]:
    """Scan already-loaded metadata, not image data or full-disk AIA preparation."""
    sources: Counter[str] = Counter()
    wcs_cache: dict[tuple, bool] = {}
    missing_time = missing_exposure = missing_wcs = missing_observer = 0
    for index in range(dataset.n_frames):
        if cancelled and cancelled():
            raise InterruptedError("Quality report cancelled")
        meta = dataset.get_frame_metadata(index)
        h = {str(k).upper(): v for k, v in meta.header.items()}
        key = next((k for k in (*TIME_KEYS, *MJD_KEYS) if h.get(k) not in (None, "")), None)
        sources[key or "cube/SAV time array or unavailable"] += 1
        missing_time += meta.time is None
        exposure = meta.exposure_seconds
        missing_exposure += exposure is None or not np.isfinite(exposure) or exposure <= 0
        # Spatial validation does not need hundreds of acquisition/processing
        # cards, DATE fixups or ephemerides. Keep distortion and legacy WCS keys.
        spatial = {k: v for k, v in h.items() if k.startswith((
            "NAXIS", "WCS", "CTYPE", "CUNIT", "CRPIX", "CRVAL", "CDELT",
            "CD", "PC", "CROTA", "PV", "PS", "LONPOLE", "LATPOLE",
            "A_", "B_", "AP_", "BP_", "CPDIS", "DP", "D2IM")) or k in
            {"XCEN", "YCEN", "XC", "YC", "DX", "DY", "XSCALE", "YSCALE", "SOLAR_X", "SOLAR_Y"}}
        signature = tuple(sorted((k, repr(v)) for k, v in spatial.items()))
        if signature not in wcs_cache:
            wcs = spatial_wcs(spatial)
            wcs_cache[signature] = wcs is not None and wcs.has_celestial
        missing_wcs += not wcs_cache[signature]
        try:
            known_observer = np.isfinite(float(h.get("DSUN_OBS", 0))) and float(h.get("DSUN_OBS", 0)) > 0
        except (TypeError, ValueError):
            known_observer = False
        missing_observer += not known_observer
        if progress:
            progress(index + 1, dataset.n_frames)
    dt = np.array([]) if dataset.times is None else np.asarray((dataset.times[1:] - dataset.times[:-1]).to_value("s"))
    positive = dt[dt > 1e-6]
    cadence = float(np.median(positive)) if positive.size else None
    return {
        "frames": dataset.n_frames, "time_header_fields": dict(sources),
        "time_axis": getattr(dataset, "time_origin", "source") if dataset.times is not None else "frame index (explicit choice required)",
        "missing_individual_times": int(missing_time),
        "duplicate_time_intervals": int(np.count_nonzero(np.abs(dt) <= 1e-6)),
        "reversed_time_intervals": int(np.count_nonzero(dt < -1e-6)),
        "median_positive_cadence_s": cadence,
        "large_gap_after_frame_1based": (np.flatnonzero(dt > 5 * cadence) + 1).tolist() if cadence else [],
        "missing_or_invalid_exposure": int(missing_exposure),
        "missing_angular_wcs": int(missing_wcs), "missing_observer_distance": int(missing_observer),
        "distance_conversion": "Projected distance; nominal solar radius 695700 km / angular radius 959.63 arcsec. Not deprojected. Observer distance is not used by this convention.",
        "wcs_validation": "Header-level angular WCS availability; not a guarantee of pointing accuracy or coalignment.",
    }
