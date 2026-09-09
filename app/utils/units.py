"""Small, explicit unit helpers for the GUI and TD distance axis."""

from __future__ import annotations

import numpy as np
from astropy import units as u
from astropy.wcs import WCS
from astropy.wcs.utils import proj_plane_pixel_scales

SOLAR_RADIUS_KM = 695_700.0
SOLAR_ANGULAR_RADIUS_ARCSEC = 959.63


def convert_distance_value(
    value: float,
    source_unit: str,
    target_unit: str,
    *,
    pixel_scale_arcsec_value: float | None = None,
) -> float:
    """Convert one signed projected distance for slope/velocity reporting.

    Pixel conversion is accepted only when the TD result retained a defensible
    WCS pixel scale.  Angular-to-linear conversion uses the same nominal solar
    radius convention as the TD distance-axis engine, keeping plotted and
    measured values reproducible.
    """
    if source_unit == target_unit:
        return float(value)
    if source_unit == "pixel":
        if pixel_scale_arcsec_value is None:
            raise ValueError("Pixel conversion requires a reliable WCS pixel scale.")
        arcsec = float(value) * pixel_scale_arcsec_value
    elif source_unit == "arcsec":
        arcsec = float(value)
    elif source_unit == "km":
        arcsec = float(value) / SOLAR_RADIUS_KM * SOLAR_ANGULAR_RADIUS_ARCSEC
    elif source_unit == "Mm":
        arcsec = float(value) * 1_000.0 / SOLAR_RADIUS_KM * SOLAR_ANGULAR_RADIUS_ARCSEC
    else:
        raise ValueError(f"Unsupported distance unit: {source_unit}")

    if target_unit == "arcsec":
        return arcsec
    if target_unit == "km":
        return arcsec / SOLAR_ANGULAR_RADIUS_ARCSEC * SOLAR_RADIUS_KM
    if target_unit == "Mm":
        return arcsec / SOLAR_ANGULAR_RADIUS_ARCSEC * (SOLAR_RADIUS_KM / 1_000.0)
    if target_unit == "pixel":
        if pixel_scale_arcsec_value is None:
            raise ValueError("Pixel conversion requires a reliable WCS pixel scale.")
        return arcsec / pixel_scale_arcsec_value
    raise ValueError(f"Unsupported distance unit: {target_unit}")


def pixel_scale_arcsec(wcs: WCS | None) -> float | None:
    """Estimate geometric-mean angular pixel scale in arcsec/pixel.

    Only an angular celestial WCS is accepted. Returning None rather than
    guessing is intentional: non-angular detector WCS cannot support arcsec
    slit widths or a physical distance conversion.
    """
    if wcs is None or not wcs.has_celestial:
        return None
    try:
        scales = proj_plane_pixel_scales(wcs.celestial) * u.deg
        return float(np.sqrt(scales[0] * scales[1]).to_value(u.arcsec))
    except Exception:
        return None


def convert_width_to_pixels(width: float, unit: str, wcs: WCS | None) -> float:
    """Convert a GUI width to pixels or raise a defensible error."""
    if unit == "pixel":
        return float(width)
    scale = pixel_scale_arcsec(wcs)
    if scale is None:
        raise ValueError("This dataset has no reliable angular WCS; use pixels.")
    if unit == "arcsec":
        return float(width) / scale
    if unit == "km":
        return (float(width) / SOLAR_RADIUS_KM * SOLAR_ANGULAR_RADIUS_ARCSEC) / scale
    if unit == "Mm":
        return (float(width) * 1_000.0 / SOLAR_RADIUS_KM * SOLAR_ANGULAR_RADIUS_ARCSEC) / scale
    raise ValueError(f"Unsupported width unit: {unit}")


def distance_from_pixels(distance_px: np.ndarray, unit: str, wcs: WCS | None) -> np.ndarray:
    """Convert cumulative pixel distance to an honest requested distance unit."""
    if unit == "pixel":
        return np.asarray(distance_px, dtype=float)
    scale = pixel_scale_arcsec(wcs)
    if scale is None:
        raise ValueError("This dataset has no reliable angular WCS; use pixels.")
    arcsec = np.asarray(distance_px, dtype=float) * scale
    if unit == "arcsec":
        return arcsec
    if unit == "km":
        return arcsec / SOLAR_ANGULAR_RADIUS_ARCSEC * SOLAR_RADIUS_KM
    if unit == "Mm":
        return arcsec / SOLAR_ANGULAR_RADIUS_ARCSEC * (SOLAR_RADIUS_KM / 1_000.0)
    raise ValueError(f"Unsupported distance unit: {unit}")


def distance_along_path(samples_pixel: np.ndarray, unit: str, wcs: WCS | None) -> np.ndarray:
    """Calculate cumulative path length in pixels or projected angular units.

    For an angular solar WCS this transforms every centreline sample first and
    integrates successive separations in the projected world plane.  This is
    more accurate than multiplying total pixel length by one average scale when
    the WCS is rotated, anisotropic, or mildly distorted.
    """
    samples = np.asarray(samples_pixel, dtype=float)
    pixel_steps = np.hypot(np.diff(samples[:, 0]), np.diff(samples[:, 1]))
    pixel_distance = np.concatenate(([0.0], np.cumsum(pixel_steps)))
    if unit == "pixel":
        return pixel_distance
    if wcs is None or not wcs.has_celestial:
        raise ValueError("This dataset has no reliable angular WCS; use pixels.")
    try:
        world = wcs.pixel_to_world_values(samples[:, 0], samples[:, 1])
        lon_quantity = u.Quantity(
            np.asarray(world[0], dtype=float), wcs.world_axis_units[0] or "deg"
        )
        # FITS celestial longitudes commonly wrap from 359.999... to 0 near
        # Solar-X=0. Unwrap before differencing so a sub-pixel step is never
        # mistaken for an almost-360-degree path segment.
        lon = np.rad2deg(np.unwrap(lon_quantity.to_value(u.rad))) * 3600.0
        lat = u.Quantity(np.asarray(world[1], dtype=float), wcs.world_axis_units[1] or "deg").to_value(u.arcsec)
        angular = np.concatenate(([0.0], np.cumsum(np.hypot(np.diff(lon), np.diff(lat)))))
    except Exception as exc:
        raise ValueError("The spatial WCS could not transform the selected path; use pixels.") from exc
    if unit == "arcsec":
        return angular
    if unit == "km":
        return angular / SOLAR_ANGULAR_RADIUS_ARCSEC * SOLAR_RADIUS_KM
    if unit == "Mm":
        return angular / SOLAR_ANGULAR_RADIUS_ARCSEC * (SOLAR_RADIUS_KM / 1_000.0)
    raise ValueError(f"Unsupported distance unit: {unit}")
