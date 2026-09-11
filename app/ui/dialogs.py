"""Small decision dialogs for genuinely ambiguous data configuration."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QSpinBox,
    QDoubleSpinBox,
    QTextBrowser,
    QVBoxLayout,
)

from app.i18n import translate_text


class HelpTextDialog(QDialog):
    """Scrollable, searchable-by-browser, copyable help and About content."""

    def __init__(
        self,
        title: str,
        content: str,
        parent: object | None = None,
        *,
        rich_text: bool = False,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(780, 650)
        layout = QVBoxLayout(self)
        self.browser = QTextBrowser(self)
        self.browser.setOpenExternalLinks(True)
        self.browser.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
            | Qt.TextInteractionFlag.LinksAccessibleByMouse
            | Qt.TextInteractionFlag.LinksAccessibleByKeyboard
        )
        if rich_text:
            self.browser.setHtml(content)
        else:
            self.browser.setPlainText(content)
        layout.addWidget(self.browser)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.clicked.connect(self.accept)
        layout.addWidget(buttons)


class AnimationExportDialog(QDialog):
    """Collect explicit movie geometry and encoder settings before choosing a file."""

    def __init__(
        self,
        source_shape: tuple[int, int],
        default_fps: float,
        parent: object | None = None,
        *,
        viewport_size: tuple[int, int] | None = None,
        n_frames: int = 1,
    ) -> None:
        super().__init__(parent)
        self._source_size = (int(source_shape[1]), int(source_shape[0]))
        self._viewport_size = viewport_size or self._source_size
        self.setWindowTitle("动画导出设置")
        layout = QFormLayout(self)
        self.resolution = QComboBox()
        self.resolution.addItems(["当前窗口分辨率", "原始图像分辨率", "1920 × 1080", "1280 × 720", "自定义"])
        self.width = QSpinBox(); self.width.setRange(16, 16384); self.width.setValue(self._viewport_size[0])
        self.height = QSpinBox(); self.height.setRange(16, 16384); self.height.setValue(self._viewport_size[1])
        self.fps = QDoubleSpinBox(); self.fps.setRange(0.1, 120.0); self.fps.setValue(default_fps); self.fps.setSuffix(" fps")
        self.codec = QComboBox(); self.codec.addItems(["libx264", "mpeg4"])
        self.bitrate = QLineEdit("8M")
        self.view_range = QComboBox()
        self.view_range.addItem("当前显示的坐标范围", "current")
        self.view_range.addItem("完整图像范围", "full")
        self.start_frame = QSpinBox(); self.start_frame.setRange(1, max(1, n_frames)); self.start_frame.setValue(1)
        self.end_frame = QSpinBox(); self.end_frame.setRange(1, max(1, n_frames)); self.end_frame.setValue(max(1, n_frames))
        self.frame_step = QSpinBox(); self.frame_step.setRange(1, max(1, n_frames)); self.frame_step.setValue(1)
        self.include_axes = QCheckBox("显示坐标轴与刻度"); self.include_axes.setChecked(True)
        self.include_timestamp = QCheckBox("显示实际观测时间"); self.include_timestamp.setChecked(True)
        self.include_title = QCheckBox("显示图像标题"); self.include_title.setChecked(False)
        self.include_colorbar = QCheckBox("显示 Colorbar"); self.include_colorbar.setChecked(True)
        self.include_slits = QCheckBox("显示已勾选 Slit"); self.include_slits.setChecked(True)
        self.include_regions = QCheckBox("显示已勾选 Region"); self.include_regions.setChecked(True)
        self.resolution.currentIndexChanged.connect(self._resolution_changed)
        layout.addRow("图像范围", self.view_range)
        layout.addRow("分辨率", self.resolution); layout.addRow("宽度", self.width)
        layout.addRow("高度", self.height); layout.addRow("帧率", self.fps)
        layout.addRow("起始帧", self.start_frame); layout.addRow("结束帧", self.end_frame)
        layout.addRow("帧步长", self.frame_step)
        layout.addRow("MP4 编码器", self.codec); layout.addRow("码率", self.bitrate)
        layout.addRow(self.include_axes); layout.addRow(self.include_timestamp)
        layout.addRow(self.include_title); layout.addRow(self.include_colorbar)
        layout.addRow(self.include_slits); layout.addRow(self.include_regions)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); layout.addRow(buttons)
        self._resolution_changed(0)

    def _resolution_changed(self, index: int) -> None:
        values = {
            0: self._viewport_size,
            1: self._source_size,
            2: (1920, 1080),
            3: (1280, 720),
        }.get(index)
        custom = index == 4
        self.width.setEnabled(custom); self.height.setEnabled(custom)
        if values:
            self.width.setValue(values[0]); self.height.setValue(values[1])

    def settings(self) -> dict[str, object]:
        return {
            "size": (self.width.value(), self.height.value()),
            "fps": self.fps.value(),
            "codec": self.codec.currentText(),
            "bitrate": self.bitrate.text().strip(),
            "view_range": self.view_range.currentData(),
            "start": self.start_frame.value() - 1,
            "end": self.end_frame.value() - 1,
            "step": self.frame_step.value(),
            "include_axes": self.include_axes.isChecked(),
            "include_timestamp": self.include_timestamp.isChecked(),
            "include_title": self.include_title.isChecked(),
            "include_colorbar": self.include_colorbar.isChecked(),
            "include_slits": self.include_slits.isChecked(),
            "include_regions": self.include_regions.isChecked(),
        }


class HistogramAnimationExportDialog(QDialog):
    """Collect movie settings parallel to the image-sequence exporter."""

    def __init__(
        self,
        default_fps: float,
        n_frames: int,
        viewport_size: tuple[int, int],
        parent: object | None = None,
    ) -> None:
        super().__init__(parent)
        self._viewport_size = viewport_size
        self.setWindowTitle("区域直方图动画导出设置")
        layout = QFormLayout(self)
        self.view_range = QComboBox()
        self.view_range.addItem("当前显示的坐标范围", "current")
        self.view_range.addItem("完整直方图范围", "full")
        self.resolution = QComboBox()
        self.resolution.addItems(["当前窗口分辨率", "1920 × 1080", "1280 × 720", "自定义"])
        self.width = QSpinBox(); self.width.setRange(320, 7680); self.width.setValue(viewport_size[0])
        self.height = QSpinBox(); self.height.setRange(240, 4320); self.height.setValue(viewport_size[1])
        self.fps = QDoubleSpinBox(); self.fps.setRange(0.1, 60.0)
        self.fps.setValue(default_fps); self.fps.setSuffix(" fps")
        self.start_frame = QSpinBox(); self.start_frame.setRange(1, max(1, n_frames)); self.start_frame.setValue(1)
        self.end_frame = QSpinBox(); self.end_frame.setRange(1, max(1, n_frames)); self.end_frame.setValue(max(1, n_frames))
        self.frame_step = QSpinBox(); self.frame_step.setRange(1, max(1, n_frames)); self.frame_step.setValue(1)
        self.codec = QComboBox(); self.codec.addItems(["libx264", "mpeg4"])
        self.bitrate = QLineEdit("8M")
        self.include_axes = QCheckBox("显示坐标轴与刻度"); self.include_axes.setChecked(True)
        self.include_timestamp = QCheckBox("显示实际观测时间"); self.include_timestamp.setChecked(True)
        self.include_title = QCheckBox("显示图像标题"); self.include_title.setChecked(True)
        self.include_legend = QCheckBox("显示 Legend"); self.include_legend.setChecked(True)
        self.include_grid = QCheckBox("显示 Grid"); self.include_grid.setChecked(True)
        self.resolution.currentIndexChanged.connect(self._resolution_changed)
        layout.addRow("图像范围", self.view_range)
        layout.addRow("分辨率", self.resolution)
        layout.addRow("宽度", self.width); layout.addRow("高度", self.height)
        layout.addRow("帧率", self.fps)
        layout.addRow("序列起始帧", self.start_frame); layout.addRow("序列结束帧", self.end_frame)
        layout.addRow("帧步长", self.frame_step)
        layout.addRow("MP4 编码器", self.codec); layout.addRow("码率", self.bitrate)
        layout.addRow(self.include_axes); layout.addRow(self.include_timestamp)
        layout.addRow(self.include_title); layout.addRow(self.include_legend)
        layout.addRow(self.include_grid)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject)
        layout.addRow(buttons)
        self._resolution_changed(0)

    def _resolution_changed(self, index: int) -> None:
        preset = {0: self._viewport_size, 1: (1920, 1080), 2: (1280, 720)}.get(index)
        custom = index == 3
        self.width.setEnabled(custom); self.height.setEnabled(custom)
        if preset:
            self.width.setValue(preset[0]); self.height.setValue(preset[1])

    def settings(self) -> dict[str, object]:
        return {
            "output_size": (self.width.value(), self.height.value()),
            "fps": self.fps.value(),
            "view_range": self.view_range.currentData(),
            "start": self.start_frame.value() - 1,
            "end": self.end_frame.value() - 1,
            "step": self.frame_step.value(),
            "codec": self.codec.currentText(),
            "bitrate": self.bitrate.text().strip(),
            "include_axes": self.include_axes.isChecked(),
            "include_timestamp": self.include_timestamp.isChecked(),
            "include_title": self.include_title.isChecked(),
            "include_legend": self.include_legend.isChecked(),
            "grid": self.include_grid.isChecked(),
        }


class ViewExportDialog(QDialog):
    """Choose which publication annotations are retained in a saved view."""

    def __init__(self, defaults: dict[str, object] | None = None, parent: object | None = None) -> None:
        super().__init__(parent)
        values = defaults or {}
        self.setWindowTitle("保存当前视图设置")
        layout = QFormLayout(self)
        note = QLabel("默认保存当前视图中的全部信息；以下选项可以独立组合。")
        note.setWordWrap(True)
        layout.addRow(note)
        self.include_axes = QCheckBox("Include axes, labels and ticks")
        self.include_title = QCheckBox("Include title")
        self.include_colorbar = QCheckBox("Include colorbar")
        self.transparent = QCheckBox("Transparent figure background")
        self.include_axes.setChecked(bool(values.get("include_axes", True)))
        self.include_title.setChecked(bool(values.get("include_title", True)))
        self.include_colorbar.setChecked(bool(values.get("include_colorbar", True)))
        self.transparent.setChecked(bool(values.get("transparent", False)))
        self.dpi = QSpinBox(); self.dpi.setRange(72, 1200)
        self.dpi.setValue(int(values.get("dpi", 300))); self.dpi.setSuffix(" dpi")
        layout.addRow(self.include_axes)
        layout.addRow(self.include_title)
        layout.addRow(self.include_colorbar)
        layout.addRow(self.transparent)
        layout.addRow("DPI", self.dpi)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def settings(self) -> dict[str, object]:
        return {
            "include_axes": self.include_axes.isChecked(),
            "include_title": self.include_title.isChecked(),
            "include_colorbar": self.include_colorbar.isChecked(),
            "transparent": self.transparent.isChecked(),
            "dpi": self.dpi.value(),
        }


class TimeAxisDialog(QDialog):
    """Require the user to confirm a cube axis when AUTO confidence is not high."""

    def __init__(self, detection_text: str, parent: object | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("时间轴设置")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(detection_text))
        layout.addWidget(QLabel("请选择 NumPy 数组中的时间维："))
        self.axis = QComboBox()
        self.axis.addItems(["轴 0", "轴 1", "轴 2"])
        layout.addWidget(self.axis)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected_axis(self) -> int:
        return self.axis.currentIndex()


class ManualTimeDialog(QDialog):
    """Offer frame-index or explicit start-plus-cadence configuration."""

    def __init__(self, parent: object | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("需要设置时间")
        layout = QFormLayout(self)
        self.mode = QComboBox()
        self.mode.addItems(["使用帧序号", "起始时间 + 固定间隔"])
        self.start = QLineEdit(datetime.now().strftime("%Y-%m-%dT%H:%M:%S"))
        self.cadence = QLineEdit("12")
        layout.addRow("时间轴", self.mode)
        layout.addRow("UTC 起始时间（ISO）", self.start)
        layout.addRow("时间间隔 [s]", self.cadence)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def configured_values(self) -> tuple[str | None, float | None]:
        if self.mode.currentIndex() == 0:
            return None, None
        try:
            return self.start.text().strip(), float(self.cadence.text())
        except ValueError:
            raise ValueError("时间间隔必须是以秒为单位的数值。")


class PlotLayoutDialog(QDialog):
    """Persistent, working replacement for Matplotlib's constrained-layout dialog."""

    def __init__(self, values: dict[str, float], parent: object | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("调整子图布局")
        layout = QFormLayout(self)
        note = QLabel(
            "这些数值控制绘图区在画布中的边距与多子图间距；应用后会关闭自动布局，"
            "并为该页面持久保存。"
        )
        note.setWordWrap(True)
        layout.addRow(note)
        self.controls: dict[str, QDoubleSpinBox] = {}
        labels = {
            "left": "左边距 Left", "right": "右边界 Right",
            "bottom": "下边距 Bottom", "top": "上边界 Top",
            "wspace": "水平子图间距 WSpace", "hspace": "垂直子图间距 HSpace",
        }
        for key, label in labels.items():
            control = QDoubleSpinBox()
            control.setRange(0.0, 1.0 if key in {"left", "right", "bottom", "top"} else 2.0)
            control.setDecimals(3)
            control.setSingleStep(0.01)
            control.setValue(float(values[key]))
            self.controls[key] = control
            layout.addRow(label, control)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept_values)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _accept_values(self) -> None:
        values = self.values()
        if values["left"] >= values["right"] or values["bottom"] >= values["top"]:
            QMessageBox.warning(self, "布局参数无效", "Left 必须小于 Right，Bottom 必须小于 Top。")
            return
        self.accept()

    def values(self) -> dict[str, float]:
        return {key: control.value() for key, control in self.controls.items()}


def show_error(parent: object, title: str, message: str, detail: str | None = None) -> None:
    """Show a courteous user message while tracebacks stay in the log."""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Critical)
    box.setWindowTitle(translate_text(title))
    box.setText(translate_text(message))
    if detail:
        box.setDetailedText(translate_text(detail))
    box.exec()
