"""Compact, reusable Qt control panels for dataset, image, and path state."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMenu,
    QPushButton,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


def _items(combo: QComboBox, values: list[tuple[str, str]]) -> None:
    for text, value in values:
        combo.addItem(text, value)


class DatasetPanel(QWidget):
    """Dataset summary and reference-frame controls."""

    reference_changed = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        box = QGroupBox("数据集摘要")
        form = QFormLayout(box)
        self.summary = QLabel("尚未载入数据。")
        self.summary.setWordWrap(True)
        form.addRow(self.summary)
        self.reference = QSpinBox()
        self.reference.setMinimum(0)
        self.reference.valueChanged.connect(self.reference_changed)
        form.addRow("参考帧", self.reference)
        layout.addWidget(box)
        layout.addStretch(1)

    def set_summary(self, html: str, n_frames: int) -> None:
        self.summary.setText(html)
        self.reference.setMaximum(max(0, n_frames - 1))


class ImagePanel(QWidget):
    """Image display and animation controls."""

    changed = Signal()
    export_clicked = Signal()

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        box = QGroupBox("图像显示")
        form = QFormLayout(box)
        self.cmap = QComboBox()
        self.cmap.addItems(["gray", "viridis", "plasma", "inferno", "magma", "turbo", "hot", "coolwarm"])
        self.reverse = QCheckBox("Reverse colormap")
        self.normalization = QComboBox()
        _items(self.normalization, [("Percentile", "percentile"), ("Manual", "manual"), ("Min–Max", "minmax"), ("ZScale", "zscale")])
        self.stretch = QComboBox()
        _items(self.stretch, [("Linear", "linear"), ("Log", "log"), ("Sqrt", "sqrt"), ("Asinh", "asinh"), ("Power", "power")])
        self.vmin = QDoubleSpinBox()
        self.vmin.setRange(-1e30, 1e30)
        self.vmin.setDecimals(6)
        self.vmax = QDoubleSpinBox()
        self.vmax.setRange(-1e30, 1e30)
        self.vmax.setValue(1.0)
        self.vmax.setDecimals(6)
        self.percentile_low = QDoubleSpinBox()
        self.percentile_low.setRange(0.0, 99.999)
        self.percentile_low.setDecimals(3)
        self.percentile_low.setValue(1.0)
        self.percentile_low.setSuffix(" %")
        self.percentile_high = QDoubleSpinBox()
        self.percentile_high.setRange(0.001, 100.0)
        self.percentile_high.setDecimals(3)
        self.percentile_high.setValue(99.0)
        self.percentile_high.setSuffix(" %")
        self.fixed = QCheckBox("Fixed normalization for sequence")
        self.fixed.setChecked(True)
        self.cmap.currentIndexChanged.connect(self.changed)
        self.reverse.toggled.connect(self.changed)
        self.normalization.currentIndexChanged.connect(self._range_mode_changed)
        self.stretch.currentIndexChanged.connect(self.changed)
        self.vmin.valueChanged.connect(self.changed)
        self.vmax.valueChanged.connect(self.changed)
        self.percentile_low.valueChanged.connect(self._percentiles_changed)
        self.percentile_high.valueChanged.connect(self._percentiles_changed)
        self.fixed.toggled.connect(self.changed)
        self.normalization.setToolTip(
            "Percentile 使用下方百分位；Manual 使用 vmin/vmax；Min–Max 和 ZScale 自动计算。"
        )
        form.addRow("Colormap", self.cmap)
        form.addRow(self.reverse)
        form.addRow("Normalization（显示范围）", self.normalization)
        form.addRow("Stretch", self.stretch)
        form.addRow("vmin", self.vmin)
        form.addRow("vmax", self.vmax)
        form.addRow("Lower percentile", self.percentile_low)
        form.addRow("Upper percentile", self.percentile_high)
        form.addRow(self.fixed)
        self._range_mode_changed()
        layout.addWidget(box)

        animation = QGroupBox("动画")
        aform = QFormLayout(animation)
        self.speed = QDoubleSpinBox()
        self.speed.setRange(0.25, 60.0)
        self.speed.setValue(5.0)
        self.speed.setSuffix(" fps")
        self.export = QPushButton("导出 GIF / MP4")
        self.export.clicked.connect(self.export_clicked)
        aform.addRow("预览帧率", self.speed)
        aform.addRow(self.export)
        layout.addWidget(animation)
        layout.addStretch(1)

    def cmap_name(self) -> str:
        return f"{self.cmap.currentText()}_r" if self.reverse.isChecked() else self.cmap.currentText()

    def _range_mode_changed(self) -> None:
        """Expose only the parameters consumed by the selected normalization."""
        mode = str(self.normalization.currentData())
        manual = mode == "manual"
        percentile = mode == "percentile"
        self.vmin.setEnabled(manual)
        self.vmax.setEnabled(manual)
        self.percentile_low.setEnabled(percentile)
        self.percentile_high.setEnabled(percentile)
        self.changed.emit()

    def _percentiles_changed(self) -> None:
        """Keep a valid ordered percentile interval and request an immediate redraw."""
        low = self.percentile_low.value()
        high = self.percentile_high.value()
        if low >= high:
            sender = self.sender()
            if sender is self.percentile_low:
                self.percentile_high.blockSignals(True)
                self.percentile_high.setValue(min(100.0, low + 0.001))
                self.percentile_high.blockSignals(False)
            else:
                self.percentile_low.blockSignals(True)
                self.percentile_low.setValue(max(0.0, high - 0.001))
                self.percentile_low.blockSignals(False)
        self.changed.emit()


class PathPanel(QWidget):
    """Slit manager and scientific sampling settings."""

    new_path = Signal(str)
    delete_path = Signal()
    generate = Signal()
    active_changed = Signal(int)
    changed = Signal()
    help_clicked = Signal()
    visibility_changed = Signal(int, bool)

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        manager = QGroupBox("Slit Manager")
        mform = QFormLayout(manager)
        self.paths = QListWidget()
        self.path_type = QComboBox()
        _items(self.path_type, [("Line", "line"), ("Polyline", "polyline"), ("Smooth Curve", "smooth"), ("Custom Function (Experimental)", "custom")])
        self.new = QToolButton()
        self.new.setText("New Slit ▾")
        self.new.setMinimumWidth(118)
        self.new.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        new_menu = QMenu(self.new)
        for label, value in (("Line", "line"), ("Polyline", "polyline"), ("Smooth Curve", "smooth"), ("Custom Function (Experimental)", "custom")):
            action = new_menu.addAction(label)
            action.triggered.connect(lambda _checked=False, selected=value: self._request_new(selected))
        self.new.setMenu(new_menu)
        self.delete = QPushButton("Delete Selected")
        self.delete.setMinimumWidth(92)
        self.help = QPushButton("Help")
        self.help.setMaximumWidth(52)
        self.name = QLineEdit()
        self.color = QPushButton("#00e5ff")
        self.display_width = QDoubleSpinBox(); self.display_width.setRange(0.25, 12.0); self.display_width.setValue(2.0)
        self.show_label = QCheckBox("显示可拖动标签"); self.show_label.setChecked(True)
        self.label_color = QPushButton("#00e5ff")
        self.label_background = QPushButton("#000000")
        self.label_background_transparent = QCheckBox("Transparent")
        self.label_background_transparent.toggled.connect(self.label_background.setDisabled)
        self.label_background_transparent.toggled.connect(self.changed)
        self.label_size = QDoubleSpinBox(); self.label_size.setRange(6.0, 36.0); self.label_size.setValue(10.0); self.label_size.setSuffix(" pt")
        self.paths.currentRowChanged.connect(self.active_changed)
        self.paths.itemChanged.connect(
            lambda item: self.visibility_changed.emit(
                self.paths.row(item), item.checkState() == Qt.CheckState.Checked
            )
        )
        self.delete.clicked.connect(self.delete_path)
        self.help.clicked.connect(self.help_clicked)
        for widget in (
            self.name, self.color, self.display_width, self.show_label, self.label_color,
            self.label_background, self.label_size,
        ):
            signal = (
                getattr(widget, "editingFinished", None)
                or getattr(widget, "clicked", None)
                or getattr(widget, "valueChanged", None)
                or getattr(widget, "toggled", None)
            )
            signal.connect(self.changed)
        mform.addRow("Slits", self.paths)
        manager_buttons = QHBoxLayout()
        manager_buttons.addWidget(self.new, 4)
        manager_buttons.addWidget(self.delete, 3)
        manager_buttons.addStretch(1)
        manager_buttons.addWidget(self.help)
        mform.addRow(manager_buttons)
        mform.addRow("名称", self.name)
        mform.addRow("线条颜色", self.color)
        mform.addRow("显示线宽", self.display_width)
        mform.addRow(self.show_label)
        mform.addRow("标签文字颜色", self.label_color)
        label_background_row = QHBoxLayout()
        label_background_row.addWidget(self.label_background, 1)
        label_background_row.addWidget(self.label_background_transparent)
        mform.addRow("标签背景颜色", label_background_row)
        mform.addRow("标签文字大小", self.label_size)
        layout.addWidget(manager)

        scientific = QGroupBox("Slit Parameters")
        sform = QFormLayout(scientific)
        self.width = QDoubleSpinBox()
        self.width.setRange(0.01, 1e7)
        self.width.setValue(1.0)
        self.width.setDecimals(3)
        self.width.setMaximumWidth(110)
        self.width_unit = QComboBox()
        self.width_unit.addItems(["pixel", "arcsec", "km", "Mm"])
        self.width_unit.setMaximumWidth(88)
        self.show_width = QCheckBox("Show slit width")
        self.show_width.setChecked(True)
        self.show_width.setToolTip("在 Map 上用半透明带显示实际参与法向统计的 Slit 宽度。")
        self.integration = QComboBox()
        _items(self.integration, [("Mean", "mean"), ("Median", "median"), ("Sum", "sum"), ("Maximum", "maximum"), ("Minimum", "minimum")])
        self.interpolation = QComboBox()
        _items(self.interpolation, [("Linear", "linear"), ("Nearest", "nearest"), ("Cubic", "cubic")])
        self.coordinate_mode = QComboBox()
        _items(self.coordinate_mode, [("像素坐标", "pixel"), ("世界坐标/WCS", "world")])
        self.coordinate_mode.setCurrentIndex(self.coordinate_mode.findData("world"))
        self.tracking = QComboBox()
        _items(self.tracking, [("固定像素位置", "pixel_fixed"), ("固定世界坐标", "world_fixed"), ("太阳自转跟踪（实验）", "solar_rotation")])
        self.tracking.setCurrentIndex(self.tracking.findData("world_fixed"))
        self.step = QDoubleSpinBox()
        self.step.setRange(0.1, 1000)
        self.step.setValue(1.0)
        self.step.setSuffix(" pixel")
        self.distance_unit = QComboBox()
        self.distance_unit.addItems(["pixel", "arcsec", "km", "Mm"])
        self.distance_unit.setCurrentText("arcsec")
        self.normalize_exposure = QCheckBox("Normalize by exposure time")
        self.normalize_exposure.setChecked(True)
        self.smoothing = QDoubleSpinBox()
        self.smoothing.setRange(0.0, 1e8)
        self.smoothing.setDecimals(3)
        for control in (
            self.integration, self.interpolation, self.coordinate_mode,
            self.tracking, self.distance_unit,
        ):
            control.setMaximumWidth(190)
        self.step.setMaximumWidth(130)
        self.smoothing.setMaximumWidth(130)
        for widget in (
            self.width, self.width_unit, self.show_width, self.integration, self.interpolation, self.coordinate_mode,
            self.tracking, self.step, self.distance_unit, self.normalize_exposure, self.smoothing,
        ):
            signal = (
                getattr(widget, "currentIndexChanged", None)
                or getattr(widget, "toggled", None)
                or getattr(widget, "valueChanged")
            )
            signal.connect(self.changed)
        width_row = QHBoxLayout()
        width_row.addWidget(self.width, 1)
        width_row.addWidget(QLabel("Unit")); width_row.addWidget(self.width_unit)
        sform.addRow("Slit width", width_row)
        sform.addRow(self.show_width)
        sform.addRow("Width integration", self.integration)
        sform.addRow("Interpolation", self.interpolation)
        sform.addRow("Coordinate mode", self.coordinate_mode)
        sform.addRow("Frame tracking", self.tracking)
        sform.addRow("Spatial step", self.step)
        sform.addRow("TD distance unit", self.distance_unit)
        sform.addRow(self.normalize_exposure)
        sform.addRow("Curve smoothing", self.smoothing)
        self.generate_button = QPushButton("生成时距图")
        self.generate_button.clicked.connect(self.generate)
        sform.addRow(self.generate_button)
        layout.addWidget(scientific)
        layout.addStretch(1)

    def _request_new(self, path_type: str) -> None:
        """Start a slit using the type chosen in the New Slit menu."""
        self.path_type.setCurrentIndex(self.path_type.findData(path_type))
        self.new_path.emit(path_type)


class RegionPanel(QWidget):
    """Closed-region manager and statistical analysis controls."""

    new_region = Signal(str)
    manual_region = Signal()
    delete_region = Signal()
    active_changed = Signal(int)
    calculate_trend = Signal()
    calculate_histogram = Signal()
    export_data = Signal()
    changed = Signal()
    help_clicked = Signal()
    visibility_changed = Signal(int, bool)

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        manager = QGroupBox("Region Manager")
        form = QFormLayout(manager)
        self.regions = QListWidget()
        self.region_type = QComboBox(); _items(self.region_type, [("Circle", "circle"), ("Rectangle", "rectangle"), ("Polygon", "polygon")])
        self.coordinate_mode = QComboBox(); _items(self.coordinate_mode, [("像素固定", "pixel"), ("世界坐标固定", "world")])
        self.coordinate_mode.setCurrentIndex(self.coordinate_mode.findData("world"))
        self.new = QToolButton()
        self.new.setText("New Region ▾")
        self.new.setMinimumWidth(118)
        self.new.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        new_menu = QMenu(self.new)
        for label, value in (("Circle", "circle"), ("Rectangle", "rectangle"), ("Polygon", "polygon")):
            action = new_menu.addAction(label)
            action.triggered.connect(lambda _checked=False, selected=value: self._request_new(selected))
        self.new.setMenu(new_menu)
        self.manual = QPushButton("Manual circle / rectangle…")
        self.delete = QPushButton("Delete Selected")
        self.delete.setMinimumWidth(92)
        self.help = QPushButton("Help")
        self.help.setMaximumWidth(52)
        self.name = QLineEdit()
        self.color = QPushButton("#ffcc33")
        self.display_width = QDoubleSpinBox(); self.display_width.setRange(0.25, 12.0); self.display_width.setValue(2.0)
        self.show_label = QCheckBox("显示可拖动标签"); self.show_label.setChecked(True)
        self.label_color = QPushButton("#ffcc33")
        self.label_background = QPushButton("#000000")
        self.label_background_transparent = QCheckBox("Transparent")
        self.label_background_transparent.toggled.connect(self.label_background.setDisabled)
        self.label_background_transparent.toggled.connect(self.changed)
        self.label_size = QDoubleSpinBox(); self.label_size.setRange(6.0, 36.0); self.label_size.setValue(10.0); self.label_size.setSuffix(" pt")
        self.regions.currentRowChanged.connect(self.active_changed)
        self.regions.itemChanged.connect(
            lambda item: self.visibility_changed.emit(
                self.regions.row(item), item.checkState() == Qt.CheckState.Checked
            )
        )
        self.manual.clicked.connect(self.manual_region)
        self.delete.clicked.connect(self.delete_region)
        self.help.clicked.connect(self.help_clicked)
        for widget in (
            self.name, self.color, self.display_width, self.show_label, self.label_color,
            self.label_background, self.label_size,
        ):
            signal = (
                getattr(widget, "editingFinished", None)
                or getattr(widget, "clicked", None)
                or getattr(widget, "valueChanged", None)
                or getattr(widget, "toggled", None)
            )
            signal.connect(self.changed)
        form.addRow("Regions", self.regions)
        form.addRow("Coordinate mode", self.coordinate_mode)
        manager_buttons = QHBoxLayout()
        manager_buttons.addWidget(self.new, 4)
        manager_buttons.addWidget(self.delete, 3)
        manager_buttons.addStretch(1)
        manager_buttons.addWidget(self.help)
        form.addRow(manager_buttons)
        form.addRow(self.manual)
        form.addRow("名称", self.name); form.addRow("线条颜色", self.color)
        form.addRow("显示线宽", self.display_width); form.addRow(self.show_label)
        form.addRow("标签文字颜色", self.label_color)
        label_background_row = QHBoxLayout()
        label_background_row.addWidget(self.label_background, 1)
        label_background_row.addWidget(self.label_background_transparent)
        form.addRow("标签背景颜色", label_background_row)
        form.addRow("标签文字大小", self.label_size)
        layout.addWidget(manager)

        analysis = QGroupBox("区域分析")
        aform = QFormLayout(analysis)
        self.statistic = QComboBox(); _items(self.statistic, [("均值", "mean"), ("总和", "sum")])
        self.bin_width = QDoubleSpinBox(); self.bin_width.setRange(1e-12, 1e30)
        self.bin_width.setDecimals(6); self.bin_width.setValue(1.0)
        self.histogram_plot_type = QComboBox()
        _items(self.histogram_plot_type, [("柱状图", "bar"), ("线状图", "line")])
        self.histogram_y_unit = QComboBox()
        _items(self.histogram_y_unit, [("计数 Count", "count"), ("相对频率 Frequency", "frequency")])
        self.trend_plot_type = QComboBox()
        _items(self.trend_plot_type, [("线状图", "line"), ("柱状图", "bar")])
        trend = QPushButton("绘制已勾选区域的时间变化")
        histogram = QPushButton("绘制当前帧直方图")
        export = QPushButton("导出最近一次区域数据…")
        trend.clicked.connect(self.calculate_trend); histogram.clicked.connect(self.calculate_histogram)
        export.clicked.connect(self.export_data)
        aform.addRow("统计量", self.statistic); aform.addRow("直方图 bin 宽度", self.bin_width)
        aform.addRow("时间变化形式", self.trend_plot_type)
        aform.addRow("直方图形式", self.histogram_plot_type)
        aform.addRow("直方图纵轴", self.histogram_y_unit)
        aform.addRow(trend); aform.addRow(histogram); aform.addRow(export)
        layout.addWidget(analysis); layout.addStretch(1)

    def _request_new(self, region_type: str) -> None:
        """Start a region using the shape selected from the New Region menu."""
        self.region_type.setCurrentIndex(self.region_type.findData(region_type))
        self.new_region.emit(region_type)
