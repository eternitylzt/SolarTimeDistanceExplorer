"""Shared robust FITS-HDU and spatial-WCS helpers."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

import numpy as np
from astropy.io import fits
from astropy.wcs import WCS


_ANGULAR_UNIT_ALIASES = {
    "arcsecs": "arcsec", "arcseconds": "arcsec", "arcsecond": "arcsec",
    "arc-sec": "arcsec", "arc_sec": "arcsec", "asec": "arcsec",
    "degrees": "deg", "degree": "deg", "degs": "deg",
}


def normalize_legacy_solar_header(header: Mapping[str, Any]) -> fits.Header:
    """Return a FITS/WCS-compatible copy of common SSW ``map2fits`` metadata.

    Older SSW products can contain human-readable angular units (``arcsecs``),
    ``SOLAR-X/Y`` axis names, IDL underscore date cards, XCEN/YCEN/DX/DY map
    fields, or a CD matrix without the CDELT values expected by SunPy's
    GenericMap.  This adapter changes metadata only. Original non-standard
    cards remain present for inspection while standard equivalents are added.
    """
    output = fits.Header(header)
    for axis in (1, 2):
        unit_key = f"CUNIT{axis}"
        unit = str(output.get(unit_key, "")).strip().lower().replace(" ", "")
        if unit in _ANGULAR_UNIT_ALIASES:
            output[unit_key] = _ANGULAR_UNIT_ALIASES[unit]

    ctype1 = str(output.get("CTYPE1", "")).strip().upper().replace("_", "-")
    ctype2 = str(output.get("CTYPE2", "")).strip().upper().replace("_", "-")
    x_aliases = {"SOLAR-X", "SOLARX", "X-SOLAR", "HPC-X", "HPLN"}
    y_aliases = {"SOLAR-Y", "SOLARY", "Y-SOLAR", "HPC-Y", "HPLT"}
    legacy_map = any(key in output for key in ("XCEN", "YCEN", "DX", "DY", "SOLAR_X", "SOLAR_Y"))
    if ctype1 in x_aliases or (not ctype1 and legacy_map):
        output["CTYPE1"] = "HPLN-TAN"
    elif ctype1.startswith("HPLN") and "-" not in ctype1:
        output["CTYPE1"] = "HPLN-TAN"
    if ctype2 in y_aliases or (not ctype2 and legacy_map):
        output["CTYPE2"] = "HPLT-TAN"
    elif ctype2.startswith("HPLT") and "-" not in ctype2:
        output["CTYPE2"] = "HPLT-TAN"

    aliases = {
        "CRVAL1": ("XCEN", "XC", "SOLAR_X"), "CRVAL2": ("YCEN", "YC", "SOLAR_Y"),
        "CDELT1": ("DX", "XSCALE"), "CDELT2": ("DY", "YSCALE"),
        "DATE-OBS": ("DATE_OBS", "DATEOBS"), "CROTA2": ("CROTA", "CROTA1"),
        "HGLN_OBS": ("HGLNOBS", "L0", "SOLAR_L0"),
        "HGLT_OBS": ("HGLTOBS", "B0", "SOLAR_B0"),
        "DSUN_OBS": ("DSUN", "D_SUN"),
    }
    for standard, legacy_keys in aliases.items():
        if standard in output:
            continue
        for legacy in legacy_keys:
            if legacy in output:
                output[standard] = output[legacy]
                break
    if "CRPIX1" not in output and output.get("NAXIS1"):
        output["CRPIX1"] = (float(output["NAXIS1"]) + 1.0) / 2.0
    if "CRPIX2" not in output and output.get("NAXIS2"):
        output["CRPIX2"] = (float(output["NAXIS2"]) + 1.0) / 2.0
    if str(output.get("CTYPE1", "")).upper().startswith("HPLN"):
        output.setdefault("CUNIT1", "arcsec")
    if str(output.get("CTYPE2", "")).upper().startswith("HPLT"):
        output.setdefault("CUNIT2", "arcsec")

    cd_keys = ("CD1_1", "CD1_2", "CD2_1", "CD2_2")
    if all(key in output for key in cd_keys) and not all(key in output for key in ("CDELT1", "CDELT2")):
        cd = np.array([[output["CD1_1"], output["CD1_2"]], [output["CD2_1"], output["CD2_2"]]], dtype=float)
        scales = np.hypot(cd[:, 0], cd[:, 1])
        if np.all(scales > 0):
            scales[1] *= -1.0 if np.linalg.det(cd) < 0 else 1.0
            output["CDELT1"], output["CDELT2"] = float(scales[0]), float(scales[1])
            output["PC1_1"], output["PC1_2"] = float(cd[0, 0] / scales[0]), float(cd[0, 1] / scales[0])
            output["PC2_1"], output["PC2_2"] = float(cd[1, 0] / scales[1]), float(cd[1, 1] / scales[1])
            for key in cd_keys:
                del output[key]
    return output


def merged_image_header(hdul: fits.HDUList, image_index: int) -> fits.Header:
    """Merge primary metadata with an image extension header.

    Solar archives frequently put observation time/instrument cards in the
    primary HDU and pixels/WCS in an image extension. Extension values take
    precedence, matching the metadata associated with the actual image.
    """
    header = hdul[0].header.copy()
    if image_index != 0:
        header.extend(
            hdul[image_index].header,
            strip=False,
            update=True,
            update_first=True,
        )
    return normalize_legacy_solar_header(header)


def first_image_hdu(path: str | Path, memmap: bool = True) -> tuple[int, np.ndarray, fits.Header]:
    """Open FITS and return the first HDU containing numeric image data.

    The returned array can be a memmap. Callers must not retain an HDUList, so
    reading frame slices stays safe on Windows and no file handle leaks into Qt.
    """
    with fits.open(path, memmap=memmap, lazy_load_hdus=True) as hdul:
        for index, hdu in enumerate(hdul):
            if hdu.data is not None and isinstance(hdu.data, np.ndarray) and hdu.data.ndim >= 2:
                return index, hdu.data, merged_image_header(hdul, index)
    raise ValueError(f"No image HDU with at least two dimensions in {path}")


def first_image_header(path: str | Path) -> tuple[int, fits.Header, tuple[int, ...]]:
    """Read only FITS headers enough to identify the first image HDU."""
    with fits.open(path, memmap=True, lazy_load_hdus=True) as hdul:
        for index, hdu in enumerate(hdul):
            ndim = int(hdu.header.get("NAXIS", 0))
            if ndim >= 2 and hdu.header.get(f"NAXIS1") and hdu.header.get("NAXIS2"):
                shape = tuple(reversed([int(hdu.header[f"NAXIS{i}"]) for i in range(1, ndim + 1)]))
                return index, merged_image_header(hdul, index), shape
    raise ValueError(f"No image header in {path}")


def spatial_wcs(header: Mapping[str, Any]) -> WCS | None:
    """Return a valid 2-D celestial/spatial WCS or None without noisy warnings."""
    try:
        normalized = normalize_legacy_solar_header(header)
        raw = WCS(normalized, relax=True, fix=True, translate_units="shd")
        if raw.pixel_n_dim < 2:
            return None
        candidate = raw.celestial if raw.has_celestial else raw
        if candidate.pixel_n_dim != 2 or candidate.world_n_dim < 2:
            return None
        # Force a cheap transform now; malformed WCS otherwise fails later in UI.
        candidate.pixel_to_world_values(0.0, 0.0)
        return candidate
    except Exception:
        return None


def extract_2d_from_hdu(path: str | Path, hdu_index: int = 0) -> tuple[np.ndarray, dict[str, Any]]:
    """Read one 2-D image from the requested FITS HDU and make it float."""
    try:
        return _extract_2d(path, hdu_index, memmap=True)
    except ValueError as exc:
        # Integer solar FITS commonly use BSCALE/BZERO.  Astropy deliberately
        # cannot apply that scaling through a read-only memory map, so reopen
        # only this requested frame without memmap instead of rejecting valid
        # AIA and other archive products.
        if "memory-mapped" not in str(exc) and "BZERO/BSCALE" not in str(exc):
            raise
        return _extract_2d(path, hdu_index, memmap=False)


def _extract_2d(
    path: str | Path, hdu_index: int, *, memmap: bool
) -> tuple[np.ndarray, dict[str, Any]]:
    """Implementation shared by the safe memmap/scaled-image fallback."""
    with fits.open(path, memmap=memmap, lazy_load_hdus=True) as hdul:
        hdu = hdul[hdu_index]
        data = np.asarray(hdu.data)
        if data.ndim != 2:
            raise ValueError(f"Expected 2-D FITS image, found {data.ndim}-D in {path}")
        # Ensure no view depends on a closed FITS file on Windows.
        return np.array(data, copy=True), dict(merged_image_header(hdul, hdu_index))


def header_exposure_seconds(header: Mapping[str, Any]) -> float | None:
    """Extract exposure duration without assuming a particular solar instrument."""
    for key in ("EXPTIME", "EXPOSURE", "XPOSURE"):
        value = header.get(key)
        try:
            if value is not None and float(value) > 0:
                return float(value)
        except (TypeError, ValueError):
            continue
    return None
