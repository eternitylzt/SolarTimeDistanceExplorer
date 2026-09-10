"""Serializable circle, rotated-rectangle, and polygon region geometry."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

import numpy as np
from astropy.wcs import WCS
from matplotlib.path import Path as MplPath


@dataclass(eq=False)
class RegionGeometry:
    """A closed scientific region, separate from slit/path geometry."""

    region_type: str
    name: str = "Region"
    id: str = field(default_factory=lambda: str(uuid4()))
    control_points_pixel: np.ndarray = field(default_factory=lambda: np.empty((0, 2), dtype=float))
    coordinate_mode: str = "pixel"
    display_color: str = "#ffcc33"
    display_linewidth: float = 2.0
    display_alpha: float = 0.95
    visible: bool = True
    show_label: bool = True
    label_position_pixel: tuple[float, float] | None = None
    label_color: str = "#ffcc33"
    label_background_color: str = "#000000"
    label_fontsize: float = 10.0
    world_outline_values: np.ndarray | None = None

    @property
    def required_points(self) -> int:
        return {"circle": 2, "rectangle": 3, "polygon": 3}[self.region_type]

    @property
    def complete(self) -> bool:
        points = self.control_points_pixel
        if len(points) < self.required_points:
            return False
        if self.region_type == "circle":
            return float(np.hypot(*(points[1] - points[0]))) > 1e-9
        if self.region_type == "rectangle":
            edge = points[1] - points[0]
            edge_length = float(np.hypot(*edge))
            height_vector = points[2] - points[1]
            area = float(edge[0] * height_vector[1] - edge[1] * height_vector[0])
            return edge_length > 1e-9 and abs(area) > 1e-9
        x, y = points[:, 0], points[:, 1]
        area_twice = float(abs(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1))))
        return area_twice > 1e-9

    def append_point(self, point: tuple[float, float]) -> None:
        self.set_control_points(np.vstack((self.control_points_pixel, np.asarray(point, dtype=float))))

    def remove_last_point(self) -> None:
        if len(self.control_points_pixel):
            self.set_control_points(self.control_points_pixel[:-1])

    def update_control_point(self, index: int, point: tuple[float, float]) -> None:
        points = self.control_points_pixel.copy()
        points[index] = point
        self.set_control_points(points)

    def set_control_points(self, points: np.ndarray) -> None:
        value = np.asarray(points, dtype=float)
        if value.size == 0:
            value = np.empty((0, 2), dtype=float)
        if value.ndim != 2 or value.shape[1] != 2:
            raise ValueError("Region points must be an N by 2 x,y array.")
        self.control_points_pixel = value
        self.world_outline_values = None

    def outline_points(self, preview_point: tuple[float, float] | None = None, samples: int = 181) -> np.ndarray:
        """Return a closed pixel boundary, optionally using a live cursor point."""
        points = self.control_points_pixel
        if preview_point is not None:
            points = np.vstack((points, np.asarray(preview_point, dtype=float)))
        if self.region_type == "circle":
            if len(points) < 2:
                return points
            center, edge = points[:2]
            radius = float(np.hypot(*(edge - center)))
            theta = np.linspace(0.0, 2.0 * np.pi, samples)
            return center + radius * np.column_stack((np.cos(theta), np.sin(theta)))
        if self.region_type == "rectangle":
            if len(points) < 2:
                return points
            p0, p1 = points[:2]
            if len(points) < 3:
                return np.vstack((p0, p1))
            edge = p1 - p0
            length = float(np.hypot(*edge))
            if length == 0:
                return points[:3]
            normal = np.array([-edge[1], edge[0]]) / length
            height = float(np.dot(points[2] - p1, normal))
            offset = height * normal
            return np.vstack((p0, p1, p1 + offset, p0 + offset, p0))
        if len(points) < 2:
            return points
        return np.vstack((points, points[0]))

    def capture_world_outline(self, wcs: WCS) -> None:
        outline = self.outline_points()
        x, y = wcs.pixel_to_world_values(outline[:, 0], outline[:, 1])
        self.world_outline_values = np.column_stack((np.asarray(x), np.asarray(y)))
        self.coordinate_mode = "world"

    def outline_for_wcs(self, wcs: WCS | None) -> np.ndarray:
        if self.coordinate_mode != "world" or self.world_outline_values is None:
            return self.outline_points()
        if wcs is None:
            raise ValueError(f"{self.name} needs WCS for world-coordinate tracking.")
        x, y = wcs.world_to_pixel_values(self.world_outline_values[:, 0], self.world_outline_values[:, 1])
        return np.column_stack((np.asarray(x, dtype=float), np.asarray(y, dtype=float)))

    def mask(self, shape: tuple[int, int], wcs: WCS | None = None) -> np.ndarray:
        """Return a pixel-centre inclusion mask; out-of-frame area is excluded."""
        outline = self.outline_for_wcs(wcs)
        if len(outline) < 4:
            return np.zeros(shape, dtype=bool)
        xmin = max(0, int(np.floor(np.nanmin(outline[:, 0]))))
        xmax = min(shape[1] - 1, int(np.ceil(np.nanmax(outline[:, 0]))))
        ymin = max(0, int(np.floor(np.nanmin(outline[:, 1]))))
        ymax = min(shape[0] - 1, int(np.ceil(np.nanmax(outline[:, 1]))))
        mask = np.zeros(shape, dtype=bool)
        if xmin > xmax or ymin > ymax:
            return mask
        yy, xx = np.mgrid[ymin : ymax + 1, xmin : xmax + 1]
        inside = MplPath(outline, closed=True).contains_points(
            np.column_stack((xx.ravel(), yy.ravel())), radius=1e-9
        )
        mask[ymin : ymax + 1, xmin : xmax + 1] = inside.reshape(xx.shape)
        return mask

    @classmethod
    def circle(cls, name: str, center: tuple[float, float], radius: float) -> "RegionGeometry":
        if radius <= 0:
            raise ValueError("Circle radius must be positive.")
        center_array = np.asarray(center, dtype=float)
        return cls("circle", name=name, control_points_pixel=np.vstack((center_array, center_array + (radius, 0))))

    @classmethod
    def rectangle(
        cls, name: str, center: tuple[float, float], width: float, height: float, angle_deg: float = 0.0
    ) -> "RegionGeometry":
        if width <= 0 or height <= 0:
            raise ValueError("Rectangle width and height must be positive.")
        angle = np.deg2rad(angle_deg)
        tangent = np.array([np.cos(angle), np.sin(angle)])
        normal = np.array([-tangent[1], tangent[0]])
        center_array = np.asarray(center, dtype=float)
        p0 = center_array - width / 2 * tangent - height / 2 * normal
        p1 = p0 + width * tangent
        p2 = p1 + height * normal
        return cls("rectangle", name=name, control_points_pixel=np.vstack((p0, p1, p2)))

    def description(self) -> str:
        if self.region_type == "circle" and self.complete:
            radius = np.hypot(*(self.control_points_pixel[1] - self.control_points_pixel[0]))
            return f"center=({self.control_points_pixel[0,0]:.2f}, {self.control_points_pixel[0,1]:.2f}), r={radius:.2f} px"
        if self.region_type == "rectangle" and self.complete:
            p0, p1, p2 = self.control_points_pixel[:3]
            edge = p1 - p0; height_vector = p2 - p1
            area = abs(edge[0] * height_vector[1] - edge[1] * height_vector[0])
            return f"edge={np.hypot(*edge):.2f} px, height={area/max(np.hypot(*edge),1e-12):.2f} px"
        return f"{len(self.control_points_pixel)} vertices"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "name": self.name, "region_type": self.region_type,
            "control_points_pixel": self.control_points_pixel.tolist(),
            "coordinate_mode": self.coordinate_mode, "display_color": self.display_color,
            "display_linewidth": self.display_linewidth, "display_alpha": self.display_alpha,
            "visible": self.visible, "show_label": self.show_label,
            "label_position_pixel": list(self.label_position_pixel) if self.label_position_pixel else None,
            "label_color": self.label_color, "label_background_color": self.label_background_color,
            "label_fontsize": self.label_fontsize,
            "world_outline_values": self.world_outline_values.tolist() if self.world_outline_values is not None else None,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RegionGeometry":
        result = cls(
            payload["region_type"], name=payload.get("name", "Region"),
            id=payload.get("id", str(uuid4())),
            control_points_pixel=np.asarray(payload.get("control_points_pixel", []), dtype=float),
            coordinate_mode=payload.get("coordinate_mode", "pixel"),
            display_color=payload.get("display_color", "#ffcc33"),
            display_linewidth=float(payload.get("display_linewidth", 2.0)),
            display_alpha=float(payload.get("display_alpha", 0.95)),
            visible=bool(payload.get("visible", True)),
            show_label=bool(payload.get("show_label", True)),
            label_position_pixel=(
                tuple(float(value) for value in payload["label_position_pixel"])
                if payload.get("label_position_pixel") is not None else None
            ),
            label_color=payload.get("label_color", payload.get("display_color", "#ffcc33")),
            label_background_color=payload.get("label_background_color", "#000000"),
            label_fontsize=float(payload.get("label_fontsize", 10.0)),
        )
        world = payload.get("world_outline_values")
        if world is not None:
            result.world_outline_values = np.asarray(world, dtype=float)
        return result
