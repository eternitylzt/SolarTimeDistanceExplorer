"""Mouse interaction controller for line, polyline, and smooth curve editing."""

from __future__ import annotations

from math import hypot

from PySide6.QtCore import QObject, Signal
from PySide6.QtCore import Qt
from matplotlib.backend_bases import MouseButton

from app.paths.base import PathGeometry
from app.ui.image_plot import ImageCanvas


class PathEditor(QObject):
    """Turn Matplotlib pointer events into independently editable scientific paths."""

    changed = Signal(object)
    finished = Signal(object)
    deselected = Signal()
    message = Signal(str)

    def __init__(self, canvas: ImageCanvas) -> None:
        super().__init__(canvas)
        self.canvas = canvas
        self.geometry: PathGeometry | None = None
        self.enabled = False
        self.drawing = False
        self._drag_index: int | None = None
        self._drag_label = False
        canvas.mouse_pressed.connect(self._press)
        canvas.mouse_moved.connect(self._move)
        canvas.mouse_released.connect(self._release)

    def begin(self, path_type: str, name: str) -> PathGeometry:
        """Create an empty path and enter click-to-draw state."""
        if path_type == "custom":
            raise ValueError("自定义函数目前仅为实验性扩展接口，尚未提供交互工具。")
        return self.begin_geometry(PathGeometry(path_type=path_type, name=name))

    def begin_geometry(self, geometry: PathGeometry) -> PathGeometry:
        """Enter drawing mode for the exact geometry stored by Path Manager."""
        self.enabled = True
        self.geometry = geometry
        self.drawing = True
        self._drag_index = None
        self._drag_label = False
        self.canvas.setCursor(Qt.CursorShape.CrossCursor)
        self.canvas.set_path(self.geometry)
        instructions = {
            "line": "直线切片：依次左键单击起点和终点。",
            "polyline": "折线切片：左键添加点；在原地双击或单击右键完成。",
            "smooth": "平滑曲线：左键添加控制点；在原地双击或单击右键完成。",
        }[geometry.path_type]
        self.message.emit(instructions)
        return self.geometry

    def set_geometry(self, geometry: PathGeometry | None) -> None:
        """Select an existing path for dragging and redraw it."""
        self.geometry = geometry
        self.drawing = False
        self._drag_index = None
        self._drag_label = False
        self.canvas.unsetCursor()
        self.canvas.set_path(geometry)

    def set_enabled(self, enabled: bool) -> None:
        """Enable this editor exclusively for the active left-side analysis tab."""
        self.enabled = enabled
        if not enabled:
            self.set_geometry(None)

    def finish(self) -> None:
        """Finish a multi-point path if it has a usable geometry."""
        if self.geometry is None or not self.geometry.complete:
            self.message.emit("切片至少需要两个点。")
            return
        self.drawing = False
        self.canvas.unsetCursor()
        self.canvas.set_path(self.geometry)
        self.finished.emit(self.geometry)
        self.message.emit("切片已完成；可拖动控制点或标签进行修改。")

    def cancel(self) -> None:
        """Cancel unfinished geometry without changing prior path records."""
        self.drawing = False
        self._drag_index = None
        self._drag_label = False
        self.canvas.unsetCursor()
        self.canvas.set_path(self.geometry if self.geometry and self.geometry.complete else None)
        self.message.emit("已取消切片绘制。")

    def _press(self, event: object) -> None:
        if not self.enabled or self.geometry is None:
            return
        button = getattr(event, "button", None)
        x, y = getattr(event, "xdata", None), getattr(event, "ydata", None)
        if x is None or y is None:
            return
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

        # Matplotlib reports the second press of a double click with dblclick=True.
        # The first press has already installed the final vertex, so finish before
        # appending an identical zero-length segment.
        if (
            bool(getattr(event, "dblclick", False))
            and self.geometry.path_type in {"polyline", "smooth"}
            and self.geometry.complete
        ):
            self.finish()
            return

        self.geometry.append_point((float(x), float(y)))
        self.canvas.set_path(self.geometry)
        self.changed.emit(self.geometry)
        if self.geometry.path_type == "line" and self.geometry.control_count == 2:
            self.finish()

    def _move(self, event: object) -> None:
        if self.geometry is None or (self._drag_index is None and not self._drag_label):
            return
        x, y = getattr(event, "xdata", None), getattr(event, "ydata", None)
        if x is None or y is None:
            return
        if self._drag_label:
            self.geometry.label_position_pixel = (float(x), float(y))
        else:
            assert self._drag_index is not None
            self.geometry.update_control_point(self._drag_index, (float(x), float(y)))
        self.canvas.set_path(self.geometry)
        self.changed.emit(self.geometry)

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
            point = self.geometry.control_points_pixel[0]
            position = (float(point[0] + 5.0), float(point[1] + 5.0))
        transform = self.canvas.axes.transData
        target = transform.transform((x, y))
        label = transform.transform(position)
        return hypot(label[0] - target[0], label[1] - target[1]) <= 18.0

    def _nearest_control(self, x: float, y: float) -> int | None:
        if self.geometry is None or not self.geometry.control_count:
            return None
        transform = self.canvas.axes.transData
        target = transform.transform((x, y))
        candidates = transform.transform(self.geometry.control_points_pixel)
        distances = [hypot(point[0] - target[0], point[1] - target[1]) for point in candidates]
        index = min(range(len(distances)), key=distances.__getitem__)
        return index if distances[index] <= 12.0 else None
