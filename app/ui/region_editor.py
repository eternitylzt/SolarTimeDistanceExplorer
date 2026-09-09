"""Mouse state machine for closed circle, rectangle, and polygon regions."""

from __future__ import annotations

from math import hypot

from matplotlib.backend_bases import MouseButton
from PySide6.QtCore import QObject, Qt, Signal

from app.regions.base import RegionGeometry
from app.ui.image_plot import ImageCanvas


class RegionEditor(QObject):
    changed = Signal(object)
    finished = Signal(object)
    deselected = Signal()
    message = Signal(str)

    def __init__(self, canvas: ImageCanvas) -> None:
        super().__init__(canvas)
        self.canvas = canvas
        self.geometry: RegionGeometry | None = None
        self.enabled = False
        self.drawing = False
        self._drag_index: int | None = None
        self._drag_label = False
        canvas.mouse_pressed.connect(self._press)
        canvas.mouse_moved.connect(self._move)
        canvas.mouse_released.connect(self._release)

    def begin_geometry(self, geometry: RegionGeometry) -> None:
        self.enabled = True
        self.geometry = geometry
        self.drawing = True
        self._drag_index = None
        self._drag_label = False
        self.canvas.setCursor(Qt.CursorShape.CrossCursor)
        self.canvas.set_region_preview(geometry, None)
        text = {
            "circle": "圆形：左键单击圆心，移动预览半径，再次单击完成。",
            "rectangle": "长方形：左键单击一条边的两个端点，移动预览高度，第三次单击完成。",
            "polygon": "多边形：左键添加顶点；在原地双击或单击右键完成。",
        }[geometry.region_type]
        self.message.emit(text)

    def set_geometry(self, geometry: RegionGeometry | None) -> None:
        self.geometry = geometry
        self.drawing = False
        self._drag_index = None
        self._drag_label = False
        self.canvas.unsetCursor()
        self.canvas.set_region_preview(None, None)

    def set_enabled(self, enabled: bool) -> None:
        """Enable this editor exclusively for the active left-side analysis tab."""
        self.enabled = enabled
        if not enabled:
            self.set_geometry(None)

    def finish(self) -> None:
        if self.geometry is None or not self.geometry.complete:
            self.message.emit("当前区域的控制点数量不足。")
            return
        self.drawing = False
        self.canvas.unsetCursor()
        self.canvas.set_region_preview(None, None)
        self.finished.emit(self.geometry)
        self.message.emit(f"{self.geometry.name} 已完成；可拖动控制点或标签修改。")

    def cancel(self) -> None:
        self.drawing = False
        self._drag_index = None
        self._drag_label = False
        self.canvas.unsetCursor()
        self.canvas.set_region_preview(None, None)
        self.message.emit("已取消区域绘制。")

    def _press(self, event: object) -> None:
        if not self.enabled or self.geometry is None:
            return
        x, y = getattr(event, "xdata", None), getattr(event, "ydata", None)
        if x is None or y is None:
            return
        button = getattr(event, "button", None)
        if button == MouseButton.RIGHT and self.drawing:
            self.finish()
            return
        if button != MouseButton.LEFT:
            return
        existing = self._nearest_control(float(x), float(y))
        if not self.drawing and self._near_label(float(x), float(y)):
            self._drag_label = True
            return
        if not self.drawing and existing is not None:
            self._drag_index = existing
            return
        if not self.drawing:
            self.deselected.emit()
            return
        if (
            bool(getattr(event, "dblclick", False))
            and self.geometry.region_type == "polygon"
            and self.geometry.complete
        ):
            self.finish()
            return
        self.geometry.append_point((float(x), float(y)))
        self.changed.emit(self.geometry)
        self.canvas.set_region_preview(self.geometry, None)
        if self.geometry.region_type in {"circle", "rectangle"} and self.geometry.complete:
            self.finish()

    def _move(self, event: object) -> None:
        if self.geometry is None:
            return
        x, y = getattr(event, "xdata", None), getattr(event, "ydata", None)
        if x is None or y is None:
            return
        point = (float(x), float(y))
        if self._drag_label:
            self.geometry.label_position_pixel = point
            self.changed.emit(self.geometry)
            return
        if self._drag_index is not None:
            self.geometry.update_control_point(self._drag_index, point)
            self.changed.emit(self.geometry)
            return
        if self.drawing:
            needs_preview = (
                self.geometry.region_type == "circle" and len(self.geometry.control_points_pixel) == 1
            ) or (
                self.geometry.region_type == "rectangle" and len(self.geometry.control_points_pixel) == 2
            )
            self.canvas.set_region_preview(self.geometry, point if needs_preview else None)

    def _release(self, event: object) -> None:
        if (self._drag_index is not None or self._drag_label) and self.geometry is not None:
            self._drag_index = None
            self._drag_label = False
            self.finished.emit(self.geometry)

    def _near_label(self, x: float, y: float) -> bool:
        if self.geometry is None or not self.geometry.show_label or not self.geometry.complete:
            return False
        position = self.geometry.label_position_pixel
        if position is None:
            point = self.geometry.outline_points()[0]
            position = (float(point[0] + 5.0), float(point[1] + 5.0))
        transform = self.canvas.axes.transData
        target = transform.transform((x, y))
        label = transform.transform(position)
        return hypot(label[0] - target[0], label[1] - target[1]) <= 18.0

    def _nearest_control(self, x: float, y: float) -> int | None:
        if self.geometry is None or not len(self.geometry.control_points_pixel):
            return None
        transform = self.canvas.axes.transData
        target = transform.transform((x, y))
        points = transform.transform(self.geometry.control_points_pixel)
        distances = [hypot(point[0] - target[0], point[1] - target[1]) for point in points]
        index = min(range(len(distances)), key=distances.__getitem__)
        return index if distances[index] <= 12.0 else None
