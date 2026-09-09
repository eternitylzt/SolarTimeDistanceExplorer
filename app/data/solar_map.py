"""SunPy Map construction and optional AIA level-1 registration."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import numpy as np
from astropy.time import Time

LOG = logging.getLogger(__name__)


def has_physical_spatial_metadata(header: Mapping[str, Any]) -> bool:
    """Return whether a header explicitly defines two meaningful spatial axes.

    SunPy can construct a permissive GenericMap from sparse metadata, but doing
    so must not make the GUI label an unknown detector array as helioprojective.
    We therefore require explicit CTYPE and a complete reference/scale set.
    """
    ctypes = (str(header.get("CTYPE1", "")).upper(), str(header.get("CTYPE2", "")).upper())
    if not all(ctypes):
        return False
    if not all(key in header for key in ("CRPIX1", "CRPIX2", "CRVAL1", "CRVAL2")):
        return False
    linear = all(key in header for key in ("CDELT1", "CDELT2")) or all(
        key in header for key in ("CD1_1", "CD1_2", "CD2_1", "CD2_2")
    )
    return linear


def make_solar_map(
    data: np.ndarray,
    header: Mapping[str, Any],
    *,
    observation_time: Time | None = None,
    prepare_aia: bool = True,
) -> tuple[Any | None, str | None, bool]:
    """Build the Python equivalent of ``fits2map`` and optionally AIA-prep it.

    Returns ``(map, notice, prepared)``.  AIA level-1 full-disk images are
    registered with :func:`aiapy.calibrate.register`, the maintained Python
    implementation derived from SSW ``aia_prep``.  Registration failure never
    hides otherwise readable pixels: the original SunPy map is returned with a
    user-facing notice.
    """
    if not has_physical_spatial_metadata(header):
        return None, "未找到完整的空间 WCS；将使用像素坐标显示。", False
    try:
        import sunpy.map

        map_header = dict(header)
        if observation_time is not None and not (map_header.get("DATE-OBS") or map_header.get("DATE_OBS")):
            map_header["DATE-OBS"] = observation_time.utc.isot
        smap = sunpy.map.Map((np.asarray(data), map_header))
    except Exception as exc:
        LOG.warning("SunPy could not construct a Map", exc_info=True)
        return None, f"SunPy 无法解释空间元数据（{exc}）；将使用像素坐标显示。", False

    try:
        if smap.coordinate_frame is None or not smap.wcs.has_celestial:
            return None, "元数据未定义 SunPy 支持的天球/太阳坐标系；将使用像素坐标显示。", False
    except Exception as exc:
        return None, f"Map 坐标系不完整（{exc}）；将使用像素坐标显示。", False

    if not prepare_aia or not _is_aia_level_one(smap):
        return smap, None, False

    try:
        # register() is explicitly documented by aiapy as the implementation
        # derived from the former SunPy/SSW aia_prep operation.  It uses the
        # image's level-1 pointing cards and does not require network access.
        from aiapy.calibrate import register

        prepared = register(smap, order=3, method="scipy")
        return prepared, "已使用 aiapy 将 AIA Level 1 图像配准到 Level 1.5 几何。", True
    except Exception as exc:
        LOG.warning("AIA level-1 registration failed; retaining original map", exc_info=True)
        return (
            smap,
            f"无法执行 AIA Level 1 配准（{exc}）。当前显示原始 SunPy Map。",
            False,
        )


def _is_aia_level_one(smap: Any) -> bool:
    """Conservatively identify an AIA level-1 map without hard version APIs."""
    if smap.__class__.__name__ != "AIAMap":
        return False
    try:
        level = smap.processing_level
        if level is not None:
            return abs(float(getattr(level, "value", level)) - 1.0) < 1e-6
    except Exception:
        pass
    for key in ("LVL_NUM", "LEVEL", "DATA_LEV"):
        try:
            value = smap.meta.get(key)
            if value is not None:
                return abs(float(value) - 1.0) < 1e-6
        except (TypeError, ValueError):
            continue
    return False
