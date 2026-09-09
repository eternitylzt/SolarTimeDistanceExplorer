"""FITS, cube-WCS, and loose-array time parsing using Astropy Time."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np
from astropy import units as u
from astropy.time import Time, TimeDelta

TIME_KEYS = (
    "DATE-OBS",
    "DATE_OBS",
    "DATEOBS",
    "T_OBS",
    "T-OBS",
    "DATE-BEG",
    "DATE_BEG",
    "DATE-AVG",
    "DATE_AVG",
    "DATE-END",
    "DATE_END",
    "T_REC",
    "TREC",
)
MJD_KEYS = ("MJD-OBS", "MJD_OBS", "MJDOBS")


def _header_upper(header: Mapping[str, Any]) -> dict[str, Any]:
    """Return a case-insensitive view for plain dict and FITS Header inputs."""
    return {str(key).upper(): value for key, value in header.items()}


def _parse_time_value(value: Any, scale: str) -> Time | None:
    """Parse one explicit FITS time value with SunPy formats before Astropy.

    SunPy's parser understands common solar archive forms such as
    ``YYYY.MM.DD_HH:MM:SS_TAI`` and slash-separated dates. Astropy remains the
    canonical internal representation and the fallback when SunPy is absent.
    """
    text = str(value).strip()
    if not text:
        return None
    parse_scale = scale
    upper = text.upper()
    if upper.endswith("_TAI") or upper.endswith(" TAI"):
        parse_scale = "tai"
        text = text[:-4]
    elif upper.endswith("_UTC") or upper.endswith(" UTC"):
        parse_scale = "utc"
        text = text[:-4]
    try:
        from sunpy.time import parse_time

        return parse_time(text, scale=parse_scale).utc
    except Exception:
        pass
    for candidate in (text, text.replace(" ", "T")):
        try:
            return Time(candidate, scale=parse_scale).utc
        except Exception:
            continue
    return None


def parse_header_time(header: Mapping[str, Any]) -> Time | None:
    """Parse one FITS frame's observation time into an Astropy ``Time``.

    No cadence is synthesized here, so an irregular folder sequence retains
    the timestamp read independently from every FITS file.
    """
    values = _header_upper(header)
    scale = str(values.get("TIMESYS", "utc")).strip().lower()
    if scale not in {"utc", "tai", "tt", "tdb", "tcg", "tcb", "ut1"}:
        scale = "utc"

    # Some older files split the calendar date and clock into two cards.
    clock = values.get("TIME-OBS", values.get("TIME_OBS"))
    for date_key in ("DATE-OBS", "DATE_OBS", "DATEOBS", "DATE"):
        date_value = values.get(date_key)
        if date_value not in (None, "") and clock not in (None, ""):
            date_text = str(date_value).strip()
            if ":" not in date_text:
                parsed = _parse_time_value(f"{date_text} {clock}", scale)
                if parsed is not None:
                    return parsed

    for key in TIME_KEYS:
        value = values.get(key)
        if value not in (None, ""):
            parsed = _parse_time_value(value, scale)
            if parsed is not None:
                return parsed
    for key in MJD_KEYS:
        value = values.get(key)
        if value not in (None, ""):
            try:
                return Time(float(value), format="mjd", scale=scale).utc
            except Exception:
                continue
    return None


def times_from_axis(
    header: Mapping[str, Any], numpy_axis: int, shape: tuple[int, ...]
) -> Time | None:
    """Reconstruct absolute cube timestamps from FITS linear time WCS."""
    fits_axis = len(shape) - numpy_axis
    ctype = str(header.get(f"CTYPE{fits_axis}", "")).upper()
    if not any(token in ctype for token in ("TIME", "UTC", "TAI", "MJD", "JD")):
        return None
    try:
        crval = float(header[f"CRVAL{fits_axis}"])
        crpix = float(header.get(f"CRPIX{fits_axis}", 1.0))
        cdelt = float(header[f"CDELT{fits_axis}"])
    except (KeyError, TypeError, ValueError):
        return None
    indices = np.arange(shape[numpy_axis], dtype=float)
    values = crval + (indices + 1.0 - crpix) * cdelt
    unit_text = str(header.get(f"CUNIT{fits_axis}", header.get("TIMEUNIT", "s"))).strip()
    scale = str(header.get("TIMESYS", "utc")).lower()
    try:
        if "MJD" in ctype:
            return Time(values, format="mjd", scale=scale)
        if ctype.startswith("JD") or ctype == "JD":
            return Time(values, format="jd", scale=scale)
        reference = parse_header_time(header)
        if reference is None and header.get("MJDREF") is not None:
            reference = Time(float(header["MJDREF"]), format="mjd", scale=scale)
        if reference is None:
            return None
        return reference + TimeDelta(values * u.Unit(unit_text))
    except Exception:
        return None


def times_from_array(values: Any) -> Time | None:
    """Best-effort conversion of a selected SAV string time variable to Time."""
    array = np.asarray(values)
    if array.ndim != 1 or array.size == 0:
        return None
    try:
        if np.issubdtype(array.dtype, np.number):
            return None
        text = [str(item).strip().replace(" ", "T") for item in array]
        return Time(text, scale="utc")
    except Exception:
        return None


def manual_times(n_frames: int, start: str | None, cadence_seconds: float | None) -> Time | None:
    """Build a configured time axis, or None for explicit frame-index mode."""
    if start is None or cadence_seconds is None:
        return None
    base = Time(start, scale="utc")
    return base + TimeDelta(np.arange(n_frames) * float(cadence_seconds), format="sec")


def cadence_statistics(times: Time | None) -> tuple[float | None, float | None, float | None, str]:
    """Return median/min/max cadence and a conservative uniformity label."""
    if times is None or len(times) < 2:
        return None, None, None, "unknown"
    delta = np.diff(times.unix)
    median = float(np.median(delta))
    minimum = float(np.min(delta))
    maximum = float(np.max(delta))
    tolerance = max(0.02 * abs(median), 0.001)
    kind = "nearly uniform" if np.max(np.abs(delta - median)) <= tolerance else "irregular"
    return median, minimum, maximum, kind
