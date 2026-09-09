"""Serializable scientific path state; display styling is intentionally separate."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

import numpy as np
from astropy.wcs import WCS


@dataclass
class PathGeometry:
    """A selected centre path and all scientific sampling settings.

    Pixel control points are always kept for project recovery. In World mode,
    sampled reference points are additionally stored as plain WCS world values;
    this makes project JSON stable and permits frame-by-frame WCS transformations
    without serializing a fragile SkyCoord frame object.
    """

    path_type: str
    control_points_pixel: np.ndarray = field(default_factory=lambda: np.empty((0, 2), dtype=float))
    name: str = "Path"
    id: str = field(default_factory=lambda: str(uuid4()))
    width: float = 1.0
    width_unit: str = "pixel"
    distance_unit: str = "pixel"
    normalize_exposure: bool = False
    integration_method: str = "mean"
    interpolation: str = "linear"
    sample_step_pixel: float = 1.0
    coordinate_mode: str = "pixel"
    tracking_mode: str = "pixel_fixed"
    smoothing: float = 0.0
    display_color: str = "#00e5ff"
    display_linewidth: float = 2.0
    display_linestyle: str = "-"
    display_alpha: float = 0.95
    show_width_boundaries: bool = True
    visible: bool = True
    show_label: bool = True
    label_position_pixel: tuple[float, float] | None = None
    label_color: str = "#00e5ff"
    label_background_color: str = "#000000"
    label_fontsize: float = 10.0
    world_sample_values: np.ndarray | None = None
    world_axis_units: tuple[str, str] | None = None
    _sample_points_pixel: np.ndarray | None = field(default=None, repr=False)

    @property
    def control_count(self) -> int:
        """Number of editable points."""
        return len(self.control_points_pixel)

    @property
    def complete(self) -> bool:
        """Whether this geometry has the minimum point count to be sampled."""
        return self.control_count >= 2

    def set_control_points(self, points: np.ndarray | list[tuple[float, float]]) -> None:
        """Validate and install editable image x,y control points."""
        value = np.asarray(points, dtype=float)
        if value.size == 0:
            value = np.empty((0, 2), dtype=float)
        if value.ndim != 2 or value.shape[1] != 2:
            raise ValueError("Path control points must be a N by 2 x,y array.")
        self.control_points_pixel = value
        self.world_sample_values = None
        self._sample_points_pixel = None

    def append_point(self, point: tuple[float, float]) -> None:
        """Add one mouse-selected point."""
        self.set_control_points(np.vstack((self.control_points_pixel, np.asarray(point, dtype=float))))

    def remove_last_point(self) -> None:
        """Remove the latest tentative curve point."""
        if self.control_count:
            self.set_control_points(self.control_points_pixel[:-1])

    def update_control_point(self, index: int, point: tuple[float, float]) -> None:
        """Move a handle after a drag and invalidate cached sampled points."""
        changed = self.control_points_pixel.copy()
        changed[index] = point
        self.set_control_points(changed)

    def cache_pixel_samples(self, samples: np.ndarray) -> None:
        """Retain generated samples until a control-point or settings edit occurs."""
        self._sample_points_pixel = np.asarray(samples, dtype=float)

    def pixel_samples(self) -> np.ndarray | None:
        """Return cached sampled centerline, if generated."""
        return self._sample_points_pixel

    def capture_world_samples(self, wcs: WCS, samples: np.ndarray) -> None:
        """Save image samples in plain WCS world values for world-fixed tracking."""
        if wcs is None:
            raise ValueError("Cannot choose World coordinates without valid WCS.")
        x = np.asarray(samples[:, 0], dtype=float)
        y = np.asarray(samples[:, 1], dtype=float)
        values = wcs.pixel_to_world_values(x, y)
        if not isinstance(values, tuple) or len(values) < 2:
            raise ValueError("The frame WCS did not yield two world coordinates.")
        self.world_sample_values = np.column_stack((np.asarray(values[0]), np.asarray(values[1])))
        units = getattr(wcs, "world_axis_units", ("", ""))
        self.world_axis_units = (str(units[0]), str(units[1]))
        self.coordinate_mode = "world"
        self.tracking_mode = "world_fixed"

    def pixel_samples_for_wcs(self, wcs: WCS | None) -> np.ndarray | None:
        """Transform retained world samples to an individual frame WCS.

        It returns None when World mode cannot be honoured, allowing callers to
        issue a clear warning and fall back only after user-configured policy.
        """
        if self.coordinate_mode != "world" or self.world_sample_values is None or wcs is None:
            return None
        try:
            x, y = wcs.world_to_pixel_values(
                self.world_sample_values[:, 0], self.world_sample_values[:, 1]
            )
            return np.column_stack((np.asarray(x, dtype=float), np.asarray(y, dtype=float)))
        except Exception:
            return None

    def to_dict(self) -> dict[str, Any]:
        """Encode scientific and display state in JSON-compatible primitives."""
        return {
            "id": self.id,
            "name": self.name,
            "path_type": self.path_type,
            "control_points_pixel": self.control_points_pixel.tolist(),
            "width": self.width,
            "width_unit": self.width_unit,
            "distance_unit": self.distance_unit,
            "normalize_exposure": self.normalize_exposure,
            "integration_method": self.integration_method,
            "interpolation": self.interpolation,
            "sample_step_pixel": self.sample_step_pixel,
            "coordinate_mode": self.coordinate_mode,
            "tracking_mode": self.tracking_mode,
            "smoothing": self.smoothing,
            "display_color": self.display_color,
            "display_linewidth": self.display_linewidth,
            "display_linestyle": self.display_linestyle,
            "display_alpha": self.display_alpha,
            "show_width_boundaries": self.show_width_boundaries,
            "visible": self.visible,
            "show_label": self.show_label,
            "label_position_pixel": list(self.label_position_pixel) if self.label_position_pixel else None,
            "label_color": self.label_color,
            "label_background_color": self.label_background_color,
            "label_fontsize": self.label_fontsize,
            "world_sample_values": (
                self.world_sample_values.tolist() if self.world_sample_values is not None else None
            ),
            "world_axis_units": list(self.world_axis_units) if self.world_axis_units else None,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PathGeometry":
        """Restore a project path without evaluating any source data."""
        geometry = cls(
            id=payload.get("id", str(uuid4())),
            name=payload.get("name", "Path"),
            path_type=payload["path_type"],
            control_points_pixel=np.asarray(payload.get("control_points_pixel", []), dtype=float),
            width=float(payload.get("width", 1.0)),
            width_unit=payload.get("width_unit", "pixel"),
            distance_unit=payload.get("distance_unit", "pixel"),
            normalize_exposure=bool(payload.get("normalize_exposure", False)),
            integration_method=payload.get("integration_method", "mean"),
            interpolation=payload.get("interpolation", "linear"),
            sample_step_pixel=float(payload.get("sample_step_pixel", 1.0)),
            coordinate_mode=payload.get("coordinate_mode", "pixel"),
            tracking_mode=payload.get("tracking_mode", "pixel_fixed"),
            smoothing=float(payload.get("smoothing", 0.0)),
            display_color=payload.get("display_color", "#00e5ff"),
            display_linewidth=float(payload.get("display_linewidth", 2.0)),
            display_linestyle=payload.get("display_linestyle", "-"),
            display_alpha=float(payload.get("display_alpha", 0.95)),
            show_width_boundaries=bool(payload.get("show_width_boundaries", True)),
            visible=bool(payload.get("visible", True)),
            show_label=bool(payload.get("show_label", True)),
            label_position_pixel=(
                tuple(float(value) for value in payload["label_position_pixel"])
                if payload.get("label_position_pixel") is not None else None
            ),
            label_color=payload.get("label_color", payload.get("display_color", "#00e5ff")),
            label_background_color=payload.get("label_background_color", "#000000"),
            label_fontsize=float(payload.get("label_fontsize", 10.0)),
        )
        world = payload.get("world_sample_values")
        if world is not None:
            geometry.world_sample_values = np.asarray(world, dtype=float)
        units = payload.get("world_axis_units")
        if units:
            geometry.world_axis_units = (str(units[0]), str(units[1]))
        return geometry
