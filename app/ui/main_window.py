"""Main desktop application for Solar Time–Distance Explorer."""

from __future__ import annotations

import logging
import re
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import matplotlib.dates as mdates
import numpy as np

from PySide6.QtCore import QEventLoop, QSettings, QTimer, Qt
from PySide6.QtGui import QAction, QColor, QKeySequence
from PySide6.QtWidgets import (
    QFileDialog,
    QApplication,
    QColorDialog,
    QDialog,
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QListWidgetItem,
    QMessageBox,
    QProgressDialog,
    QProgressBar,
    QPushButton,
    QSlider,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QToolBar,
    QToolButton,
    QMenu,
    QVBoxLayout,
    QWidget,
)

from app.animation.exporter import export_animation, export_region_histogram_animation
from app.version import __version__
from app.data.base import TimeSeriesDataset
from app.data.factory import open_from_descriptor
from app.data.fits_cube import FitsCubeDataset
from app.data.fits_folder import FitsFolderDataset
from app.data.fits_image import FitsImageDataset
from app.data.sav_cube import (
    SavCubeDataset,
    SavImageDataset,
    SavMapDataset,
    detect_sav_time_axis,
    inspect_sav,
)
from app.data.time_parser import manual_times
from app.paths.base import PathGeometry
from app.paths.geometry import sample_path_geometry
from app.plotting.export import export_figure, export_td_csv, export_td_fits, export_td_npz, export_td_txt
from app.plotting.region_export import export_region_result
from app.processing.region_analysis import (
    RegionHistogramResult,
    RegionHistogramSequence,
    RegionTrendResult,
    region_histograms,
)
from app.project.serializer import load_project, restore_times, save_project
from app.processing.td_generator import TDConfig, TDResult
from app.ui.dialogs import (
    AnimationExportDialog,
    HistogramAnimationExportDialog,
    ManualTimeDialog,
    PlotLayoutDialog,
    TimeAxisDialog,
    ViewExportDialog,
    show_error,
)
from app.ui.image_plot import ImageCanvas
from app.ui.panels import DatasetPanel, ImagePanel, PathPanel, RegionPanel
from app.ui.path_editor import PathEditor
from app.ui.region_dialogs import ManualRegionDialog
from app.ui.region_editor import RegionEditor
from app.ui.region_plot import RegionAnalysisCanvas
from app.ui.td_plot import TimeDistanceCanvas
from app.utils.logging import log_directory
from app.workers.td_worker import TDWorker
from app.workers.region_worker import RegionHistogramSequenceWorker, RegionTrendWorker
from app.regions.base import RegionGeometry
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT

LOG = logging.getLogger(__name__)
SLIT_COLORS = ("#00e5ff", "#ff4d8d", "#8cff66", "#ffd23f", "#b388ff", "#ff8c42")
REGION_COLORS = ("#ffcc33", "#00d4ff", "#ff5c8a", "#66e36f", "#b388ff", "#ff8c42")


class MainWindow(QMainWindow):
    """The application shell; all scientific operations live in non-UI modules."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Solar Time–Distance Explorer")
        self.resize(1450, 900)
        self.dataset: TimeSeriesDataset | None = None
        self.current_frame = 0
        self.reference_frame = 0
        self.paths: list[PathGeometry] = []
        self.active_path_id: str | None = None
        self._next_slit_number = 1
        self.td_result: TDResult | None = None
        self.regions: list[RegionGeometry] = []
        self.active_region_id: str | None = None
        self._next_region_number = 1
        self.region_result: RegionTrendResult | RegionHistogramResult | None = None
        self._full_region_result: RegionTrendResult | RegionHistogramResult | None = None
        self._region_worker: RegionTrendWorker | RegionHistogramSequenceWorker | None = None
        self._region_progress: QProgressDialog | None = None
        self._region_hist_sequence: RegionHistogramSequence | None = None
        self._region_hist_position = 0
        self._region_hist_timer = QTimer(self)
        self._region_hist_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._region_hist_timer.timeout.connect(self._advance_region_histogram)
        self._fixed_norm: Any | None = None
        self._td_worker: TDWorker | None = None
        self._td_progress: QProgressDialog | None = None
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.timeout.connect(self._advance_animation)
        self.settings = QSettings("SolarPhysics", "SolarTimeDistanceExplorer")
        self.keep_cross_tab_overlays = bool(self.settings.value("keep_cross_tab_overlays", False, type=bool))
        self.frame_cache_size = int(self.settings.value("frame_cache_size", 12))
        self.history_limit = int(self.settings.value("history_limit", 20))
        self._history_entries: list[dict[str, Any]] = []
        self._history_marker_ids: set[str] = set()
        self._build_ui()
        self._build_actions()
        self._build_menus()
        self._build_toolbar()

    def _build_ui(self) -> None:
        self.dataset_panel = DatasetPanel()
        self.image_panel = ImagePanel()
        self.path_panel = PathPanel()
        self.region_panel = RegionPanel()
        self.image_panel.changed.connect(self._reset_image_norm)
        self.image_panel.speed.valueChanged.connect(self._animation_speed_changed)
        self.image_panel.export_clicked.connect(self.export_animation)
        self.dataset_panel.reference_changed.connect(self._reference_changed)
        self.path_panel.new_path.connect(self.new_path)
        self.path_panel.delete_path.connect(self.delete_active_path)
        self.path_panel.active_changed.connect(self._active_path_changed)
        self.path_panel.changed.connect(self._path_settings_changed)
        self.path_panel.generate.connect(self.generate_td)
        self.path_panel.help_clicked.connect(self.show_drawing_help)
        self.path_panel.visibility_changed.connect(self._path_visibility_changed)
        self.path_panel.color.clicked.connect(lambda: self._choose_marker_color("slit"))
        self.path_panel.label_color.clicked.connect(lambda: self._choose_marker_color("slit_label"))
        self.path_panel.label_background.clicked.connect(lambda: self._choose_marker_color("slit_background"))
        self.region_panel.new_region.connect(self.new_region)
        self.region_panel.manual_region.connect(self.manual_region)
        self.region_panel.delete_region.connect(self.delete_active_region)
        self.region_panel.active_changed.connect(self._active_region_changed)
        self.region_panel.calculate_trend.connect(self.calculate_region_trends)
        self.region_panel.calculate_histogram.connect(self.calculate_region_histograms)
        self.region_panel.calculate_histogram_range.connect(self.calculate_region_histogram_sequence)
        self.region_panel.use_td_time_range.connect(self.use_td_visible_time_range)
        self.region_panel.export_data.connect(self.export_region_data)
        self.region_panel.changed.connect(self._region_settings_changed)
        self.region_panel.help_clicked.connect(self.show_drawing_help)
        self.region_panel.visibility_changed.connect(self._region_visibility_changed)
        self.region_panel.color.clicked.connect(lambda: self._choose_marker_color("region"))
        self.region_panel.label_color.clicked.connect(lambda: self._choose_marker_color("region_label"))
        self.region_panel.label_background.clicked.connect(lambda: self._choose_marker_color("region_background"))

        self.left_tabs = QTabWidget()
        self.left_tabs.addTab(self.dataset_panel, "数据集")
        self.left_tabs.addTab(self.image_panel, "图像")
        self.left_tabs.addTab(self.path_panel, "切片")
        self.left_tabs.addTab(self.region_panel, "区域")
        self.left_tabs.currentChanged.connect(self._left_tab_changed)

        self.image_canvas = ImageCanvas()
        self.image_canvas.cursor_changed.connect(self._cursor_changed)
        self.path_editor = PathEditor(self.image_canvas)
        self.path_editor.changed.connect(self._path_changed)
        self.path_editor.finished.connect(self._path_finished)
        self.path_editor.deselected.connect(self._deselect_path)
        self.path_editor.message.connect(self.statusBar().showMessage)
        self.region_editor = RegionEditor(self.image_canvas)
        self.region_editor.changed.connect(self._region_changed)
        self.region_editor.finished.connect(self._region_finished)
        self.region_editor.deselected.connect(self._deselect_region)
        self.region_editor.message.connect(self.statusBar().showMessage)

        image_tab = QWidget()
        image_layout = QVBoxLayout(image_tab)
        controls = QHBoxLayout()
        previous = QPushButton("◀ 上一帧")
        self.play_button = QPushButton("▶ 播放")
        next_button = QPushButton("下一帧 ▶")
        previous.clicked.connect(lambda: self._move_frame(-1))
        self.play_button.clicked.connect(self.toggle_animation)
        next_button.clicked.connect(lambda: self._move_frame(1))
        self.frame_slider = QSlider(Qt.Horizontal)
        self.frame_slider.valueChanged.connect(self.set_current_frame)
        self.frame_label = QLabel("帧：—")
        self.time_label = QLabel("时间：—")
        controls.addWidget(previous)
        controls.addWidget(self.play_button)
        controls.addWidget(next_button)
        controls.addWidget(self.frame_slider, 1)
        controls.addWidget(self.frame_label)
        controls.addWidget(self.time_label)
        image_layout.addLayout(controls)
        self.image_navigation = NavigationToolbar2QT(self.image_canvas, image_tab, coordinates=False)
        navigation_text = {
            "Home": ("复位", "恢复完整视野"), "Back": ("后退", "返回上一个视野"),
            "Forward": ("前进", "前往下一个视野"), "Pan": ("平移", "拖动平移视野"),
            "Zoom": ("框选放大", "拖动矩形框放大子区域"), "Subplots": ("布局", "调整子图布局"),
            "Save": ("保存 Map", "保存当前 Map 图像"),
        }
        for action in self.image_navigation.actions():
            original = action.text()
            if original in navigation_text:
                action.setText(navigation_text[original][0])
                action.setToolTip(navigation_text[original][1])
        self._install_layout_action(self.image_navigation, self.image_canvas, "image")
        image_layout.addWidget(self.image_navigation)
        image_layout.addWidget(self.image_canvas, 1)

        self.td_canvas = TimeDistanceCanvas()
        self.td_canvas.slope_measured.connect(self.statusBar().showMessage)
        td_tab = QWidget()
        td_layout = QVBoxLayout(td_tab)
        td_controls = QHBoxLayout()
        self.td_cmap, _ = self._combo(["viridis", "gray", "plasma", "inferno", "magma", "turbo"])
        self.td_norm, _ = self._combo([
            ("Percentile", "percentile"), ("Manual", "manual"),
            ("Min–Max", "minmax"), ("ZScale", "zscale"),
        ])
        self.td_stretch, _ = self._combo([("Linear", "linear"), ("Log", "log"), ("Sqrt", "sqrt"), ("Asinh", "asinh"), ("Power", "power")])
        self.td_vmin = QDoubleSpinBox(); self.td_vmin.setRange(-1e30, 1e30); self.td_vmin.setDecimals(6)
        self.td_vmax = QDoubleSpinBox(); self.td_vmax.setRange(-1e30, 1e30); self.td_vmax.setDecimals(6); self.td_vmax.setValue(1.0)
        self.td_vmin.setMaximumWidth(125); self.td_vmax.setMaximumWidth(125)
        self.td_percentile_low = QDoubleSpinBox(); self.td_percentile_low.setRange(0, 99.999); self.td_percentile_low.setDecimals(3); self.td_percentile_low.setValue(1.0); self.td_percentile_low.setSuffix(" %")
        self.td_percentile_high = QDoubleSpinBox(); self.td_percentile_high.setRange(0.001, 100); self.td_percentile_high.setDecimals(3); self.td_percentile_high.setValue(99.0); self.td_percentile_high.setSuffix(" %")
        self.td_percentile_low.setMaximumWidth(105); self.td_percentile_high.setMaximumWidth(105)
        self.true_time, _ = self._checkbox("True observational time", True)
        self.td_time_format, _ = self._combo([
            ("时:分:秒", "HH:MM:SS"), ("时:分", "HH:MM"),
            ("年-月-日 时:分:秒", "YYYY-MM-DD HH:MM:SS"), ("自定义", "Custom"),
        ])
        self.td_custom_format = QLineEdit("%H:%M:%S")
        self.td_custom_format.setMaximumWidth(130)
        self.td_custom_format.setVisible(False)
        self.td_title = QLineEdit(); self.td_title.setPlaceholderText("Time–Distance Diagram — S1")
        self.td_x_label = QLineEdit(); self.td_x_label.setPlaceholderText("Observation Time [UTC]")
        self.td_y_label = QLineEdit(); self.td_y_label.setPlaceholderText("Distance Along Slit [arcsec]")
        self.td_cmap.currentIndexChanged.connect(self._redraw_td)
        self.td_norm.currentIndexChanged.connect(self._td_range_mode_changed)
        self.td_stretch.currentIndexChanged.connect(self._redraw_td)
        self.true_time.toggled.connect(self._redraw_td)
        self.td_time_format.currentIndexChanged.connect(self._redraw_td)
        self.td_time_format.currentIndexChanged.connect(
            lambda: self.td_custom_format.setVisible(self._combo_value(self.td_time_format) == "Custom")
        )
        self.td_custom_format.editingFinished.connect(self._redraw_td)
        for control in (self.td_title, self.td_x_label, self.td_y_label):
            control.editingFinished.connect(self._redraw_td)
        self.td_axis_label_size = QDoubleSpinBox(); self.td_axis_label_size.setRange(6, 36); self.td_axis_label_size.setValue(11); self.td_axis_label_size.setSuffix(" pt")
        self.td_tick_size = QDoubleSpinBox(); self.td_tick_size.setRange(6, 30); self.td_tick_size.setValue(9); self.td_tick_size.setSuffix(" pt")
        self.td_axis_label_size.setMaximumWidth(90); self.td_tick_size.setMaximumWidth(90)
        self.td_include_start, _ = self._checkbox("横轴标题包含起始时间", False)
        self.td_grid, _ = self._checkbox("Grid", False)
        self.td_colorbar, _ = self._checkbox("Colorbar", True)
        self.td_aspect, _ = self._combo([("Auto", "auto"), ("Equal", "equal")])
        self.slope_color = QPushButton("#ffffff")
        self.slope_text_color = QPushButton("#ffffff")
        self.slope_background = QPushButton("#000000")
        self.slope_background_transparent, _ = self._checkbox("Transparent", False)
        self.slope_auto_colors, _ = self._checkbox("Auto colors", True)
        self.slope_color.setDisabled(True); self.slope_text_color.setDisabled(True)
        self.slope_selection, _ = self._combo([("Next measurement", 0)])
        self.slope_selection.setFixedWidth(135)
        self.slope_velocity_unit, _ = self._combo([
            ("Same as distance axis", "auto"), ("pixel/s", "pixel"),
            ("arcsec/s", "arcsec"), ("km/s", "km"), ("Mm/s", "Mm"),
        ])
        self._set_combo_value(self.slope_velocity_unit, "km")
        self.slope_width = QDoubleSpinBox(); self.slope_width.setRange(0.5, 8); self.slope_width.setValue(1.5)
        self.slope_linestyle, _ = self._combo([("Solid", "-"), ("Dashed", "--"), ("Dash-dot", "-."), ("Dotted", ":")])
        self.slope_fontsize = QDoubleSpinBox(); self.slope_fontsize.setRange(6, 30); self.slope_fontsize.setValue(10); self.slope_fontsize.setSuffix(" pt")
        self.slope_precision = QSpinBox(); self.slope_precision.setRange(0, 6); self.slope_precision.setValue(1); self.slope_precision.setSuffix(" 位")
        self.slope_width.setMaximumWidth(80); self.slope_fontsize.setMaximumWidth(90); self.slope_precision.setMaximumWidth(80)
        self.slope_velocity_unit.setFixedWidth(150)
        self.slope_color.setFixedWidth(88)
        self.slope_text_color.setFixedWidth(88)
        self.slope_background.setFixedWidth(88)
        self.slope_linestyle.setFixedWidth(112)
        td_export = QPushButton("导出时距图")
        td_data = QPushButton("导出时距数据")
        slope = QPushButton("测量速度")
        clear_slope = QPushButton("清除斜率标记")
        td_export.clicked.connect(self.export_td_figure)
        td_data.clicked.connect(self.export_td_data)
        slope.clicked.connect(lambda: self.td_canvas.enable_slope_measurement(True))
        clear_slope.clicked.connect(self.td_canvas.clear_measurements)
        self.slope_color.clicked.connect(self._choose_slope_color)
        self.slope_text_color.clicked.connect(self._choose_slope_text_color)
        self.slope_background.clicked.connect(self._choose_slope_background)
        self.slope_selection.currentIndexChanged.connect(self._slope_selection_changed)
        self.td_canvas.measurements_changed.connect(self._refresh_slope_measurement_selector)
        self.td_canvas.measurement_selected.connect(self._select_slope_measurement)
        for widget in (self.td_vmin, self.td_vmax, self.td_percentile_low, self.td_percentile_high, self.td_axis_label_size, self.td_tick_size):
            widget.valueChanged.connect(self._redraw_td)
        self.td_include_start.toggled.connect(self._redraw_td)
        self.td_grid.toggled.connect(self._redraw_td)
        self.td_colorbar.toggled.connect(self._redraw_td)
        self.td_aspect.currentIndexChanged.connect(self._redraw_td)
        self.slope_width.valueChanged.connect(self._apply_slope_style)
        self.slope_linestyle.currentIndexChanged.connect(self._apply_slope_style)
        self.slope_fontsize.valueChanged.connect(self._slope_fontsize_changed)
        self.slope_precision.valueChanged.connect(self._apply_slope_style)
        self.slope_velocity_unit.currentIndexChanged.connect(self._apply_slope_style)
        self.slope_background_transparent.toggled.connect(self._slope_background_transparency_changed)
        self.slope_auto_colors.toggled.connect(self._slope_auto_colors_changed)
        td_controls.addWidget(QLabel("Colormap"))
        td_controls.addWidget(self.td_cmap)
        td_controls.addWidget(QLabel("Normalization"))
        td_controls.addWidget(self.td_norm)
        td_controls.addWidget(QLabel("Stretch")); td_controls.addWidget(self.td_stretch)
        td_controls.addStretch(1)
        td_layout.addLayout(td_controls)
        td_range_controls = QHBoxLayout()
        td_range_controls.addWidget(QLabel("vmin")); td_range_controls.addWidget(self.td_vmin)
        td_range_controls.addWidget(QLabel("vmax")); td_range_controls.addWidget(self.td_vmax)
        td_range_controls.addWidget(QLabel("Percentiles")); td_range_controls.addWidget(self.td_percentile_low); td_range_controls.addWidget(self.td_percentile_high)
        td_range_controls.addStretch(1)
        td_layout.addLayout(td_range_controls)
        td_time_controls = QHBoxLayout()
        td_time_controls.addWidget(self.true_time)
        td_time_controls.addWidget(QLabel("时间刻度"))
        td_time_controls.addWidget(self.td_time_format)
        td_time_controls.addWidget(self.td_custom_format)
        td_time_controls.addWidget(self.td_include_start)
        td_time_controls.addStretch(1)
        td_layout.addLayout(td_time_controls)
        td_labels = QHBoxLayout()
        td_labels.addWidget(QLabel("Title")); td_labels.addWidget(self.td_title, 1)
        td_labels.addWidget(QLabel("X label")); td_labels.addWidget(self.td_x_label, 1)
        td_labels.addWidget(QLabel("Y label")); td_labels.addWidget(self.td_y_label, 1)
        td_layout.addLayout(td_labels)
        td_style = QHBoxLayout()
        td_style.addWidget(QLabel("坐标标题字号")); td_style.addWidget(self.td_axis_label_size)
        td_style.addWidget(QLabel("刻度字号")); td_style.addWidget(self.td_tick_size)
        td_style.addWidget(self.td_grid); td_style.addWidget(self.td_colorbar)
        td_style.addWidget(QLabel("Aspect")); td_style.addWidget(self.td_aspect)
        td_style.addStretch(1)
        td_layout.addLayout(td_style)
        slope_group = QGroupBox("Velocity Measurement")
        slope_group_layout = QVBoxLayout(slope_group)
        slope_actions = QHBoxLayout()
        slope_actions.addWidget(self.slope_auto_colors)
        slope_actions.addWidget(QLabel("Selected")); slope_actions.addWidget(self.slope_selection)
        slope_actions.addStretch(1)
        slope_actions.addWidget(slope); slope_actions.addWidget(clear_slope)
        slope_group_layout.addLayout(slope_actions)
        slope_style = QHBoxLayout()
        slope_style.addWidget(QLabel("Line")); slope_style.addWidget(self.slope_color)
        slope_style.addWidget(QLabel("Width")); slope_style.addWidget(self.slope_width)
        slope_style.addWidget(QLabel("Style")); slope_style.addWidget(self.slope_linestyle)
        slope_style.addWidget(QLabel("Text")); slope_style.addWidget(self.slope_text_color)
        slope_style.addWidget(QLabel("Size")); slope_style.addWidget(self.slope_fontsize)
        slope_style.addStretch(1)
        slope_group_layout.addLayout(slope_style)
        slope_annotation_style = QHBoxLayout()
        slope_annotation_style.addWidget(QLabel("Text Background")); slope_annotation_style.addWidget(self.slope_background)
        slope_annotation_style.addWidget(self.slope_background_transparent)
        slope_annotation_style.addStretch(1)
        slope_annotation_style.addWidget(QLabel("Velocity unit")); slope_annotation_style.addWidget(self.slope_velocity_unit)
        slope_annotation_style.addWidget(QLabel("Decimals")); slope_annotation_style.addWidget(self.slope_precision)
        slope_group_layout.addLayout(slope_annotation_style)
        td_layout.addWidget(slope_group)
        td_actions = QHBoxLayout()
        td_actions.addWidget(td_export); td_actions.addWidget(td_data); td_actions.addStretch(1)
        td_layout.addLayout(td_actions)
        self._td_range_mode_changed()
        self._sync_selected_slope_controls()
        self.td_navigation = NavigationToolbar2QT(self.td_canvas, td_tab, coordinates=True)
        self._install_layout_action(self.td_navigation, self.td_canvas, "td")
        td_layout.addWidget(self.td_navigation)
        td_layout.addWidget(self.td_canvas, 1)

        self.region_canvas = RegionAnalysisCanvas()
        region_tab = QWidget(); region_layout = QVBoxLayout(region_tab)
        region_labels = QHBoxLayout()
        self.region_plot_title = QLineEdit(); self.region_plot_title.setPlaceholderText("Automatic English title")
        self.region_x_label = QLineEdit(); self.region_x_label.setPlaceholderText("Automatic English X label")
        self.region_y_label = QLineEdit(); self.region_y_label.setPlaceholderText("Automatic English Y label")
        region_labels.addWidget(QLabel("Title")); region_labels.addWidget(self.region_plot_title, 1)
        region_labels.addWidget(QLabel("X label")); region_labels.addWidget(self.region_x_label, 1)
        region_labels.addWidget(QLabel("Y label")); region_labels.addWidget(self.region_y_label, 1)
        region_layout.addLayout(region_labels)
        region_style = QHBoxLayout()
        self.region_time_format, _ = self._combo([("时:分:秒", "HH:MM:SS"), ("时:分", "HH:MM"), ("年-月-日 时:分:秒", "YYYY-MM-DD HH:MM:SS")])
        self.region_line_style, _ = self._combo([("Solid", "-"), ("Dashed", "--"), ("Dash-dot", "-."), ("Dotted", ":")])
        self.region_line_width = QDoubleSpinBox(); self.region_line_width.setRange(0.25, 8); self.region_line_width.setValue(1.5)
        self.region_marker, _ = self._combo([("Point", "."), ("Circle", "o"), ("Square", "s"), ("None", "None")])
        self.region_x_scale, _ = self._combo([("Linear", "linear"), ("Log", "log")])
        self.region_y_scale, _ = self._combo([("Linear", "linear"), ("Log", "log")])
        self.region_grid, _ = self._checkbox("Grid", True)
        self.region_axis_label_size = QDoubleSpinBox(); self.region_axis_label_size.setRange(6, 36); self.region_axis_label_size.setValue(11); self.region_axis_label_size.setSuffix(" pt")
        self.region_tick_size = QDoubleSpinBox(); self.region_tick_size.setRange(6, 30); self.region_tick_size.setValue(9); self.region_tick_size.setSuffix(" pt")
        self.region_title_size = QDoubleSpinBox(); self.region_title_size.setRange(6, 36); self.region_title_size.setValue(12); self.region_title_size.setSuffix(" pt")
        self.region_legend_size = QDoubleSpinBox(); self.region_legend_size.setRange(6, 30); self.region_legend_size.setValue(12); self.region_legend_size.setSuffix(" pt")
        for control in (
            self.region_line_width, self.region_axis_label_size, self.region_tick_size,
            self.region_title_size, self.region_legend_size,
        ):
            control.setMaximumWidth(90)
        self.region_sync_legend, _ = self._checkbox("Legend 与标题同字号", True)
        region_save = QPushButton("保存区域分析图…"); region_save.clicked.connect(self.export_region_figure)
        for label, control in (("时间刻度", self.region_time_format), ("Line style", self.region_line_style), ("Line width", self.region_line_width), ("Marker", self.region_marker)):
            region_style.addWidget(QLabel(label)); region_style.addWidget(control)
        region_style.addStretch(1)
        region_layout.addLayout(region_style)
        region_axes_style = QHBoxLayout()
        for label, control in (("X scale", self.region_x_scale), ("Y scale", self.region_y_scale)):
            region_axes_style.addWidget(QLabel(label)); region_axes_style.addWidget(control)
        region_axes_style.addWidget(self.region_grid); region_axes_style.addStretch(1)
        region_layout.addLayout(region_axes_style)
        region_font_style = QHBoxLayout()
        for label, control in (
            ("Title size", self.region_title_size), ("Axis label size", self.region_axis_label_size),
            ("Tick size", self.region_tick_size),
        ):
            region_font_style.addWidget(QLabel(label)); region_font_style.addWidget(control)
        region_font_style.addStretch(1)
        region_layout.addLayout(region_font_style)
        region_legend_style = QHBoxLayout()
        region_legend_style.addWidget(QLabel("Legend size")); region_legend_style.addWidget(self.region_legend_size)
        region_legend_style.addWidget(self.region_sync_legend)
        region_legend_style.addWidget(region_save); region_legend_style.addStretch(1)
        region_layout.addLayout(region_legend_style)
        self.region_histogram_player = QWidget()
        histogram_player_layout = QHBoxLayout(self.region_histogram_player)
        histogram_player_layout.setContentsMargins(0, 0, 0, 0)
        self.region_hist_previous = QPushButton("◀")
        self.region_hist_play = QPushButton("▶ 播放")
        self.region_hist_next = QPushButton("▶")
        self.region_hist_slider = QSlider(Qt.Orientation.Horizontal)
        self.region_hist_frame_label = QLabel("Histogram sequence: —")
        self.region_hist_export = QPushButton("导出直方图动画…")
        self.region_hist_previous.clicked.connect(lambda: self._move_region_histogram(-1))
        self.region_hist_play.clicked.connect(self.toggle_region_histogram_animation)
        self.region_hist_next.clicked.connect(lambda: self._move_region_histogram(1))
        self.region_hist_slider.valueChanged.connect(self.show_region_histogram_frame)
        self.region_hist_export.clicked.connect(self.export_region_histogram_movie)
        histogram_player_layout.addWidget(self.region_hist_previous)
        histogram_player_layout.addWidget(self.region_hist_play)
        histogram_player_layout.addWidget(self.region_hist_next)
        histogram_player_layout.addWidget(self.region_hist_slider, 1)
        histogram_player_layout.addWidget(self.region_hist_frame_label)
        histogram_player_layout.addWidget(self.region_hist_export)
        self.region_histogram_player.setVisible(False)
        region_layout.addWidget(self.region_histogram_player)
        for control in (self.region_plot_title, self.region_x_label, self.region_y_label):
            control.editingFinished.connect(self._redraw_region)
        for control in (self.region_time_format, self.region_line_style, self.region_marker, self.region_x_scale, self.region_y_scale):
            control.currentIndexChanged.connect(self._redraw_region)
        for control in (
            self.region_line_width, self.region_axis_label_size, self.region_tick_size,
            self.region_title_size, self.region_legend_size,
        ):
            control.valueChanged.connect(self._redraw_region)
        self.region_title_size.valueChanged.connect(self._sync_region_legend_size)
        self.region_sync_legend.toggled.connect(self._sync_region_legend_size)
        self.region_grid.toggled.connect(self._redraw_region)
        self.region_panel.histogram_plot_type.currentIndexChanged.connect(self._redraw_region)
        self.region_panel.histogram_y_unit.currentIndexChanged.connect(self._redraw_region)
        self.region_panel.trend_plot_type.currentIndexChanged.connect(self._redraw_region)
        self.region_panel.histogram_fps.valueChanged.connect(self._region_histogram_fps_changed)
        self.region_navigation = NavigationToolbar2QT(self.region_canvas, region_tab, coordinates=True)
        self._install_layout_action(self.region_navigation, self.region_canvas, "region")
        region_layout.addWidget(self.region_navigation)
        region_layout.addWidget(self.region_canvas, 1)

        self.main_tabs = QTabWidget()
        self.main_tabs.addTab(image_tab, "图像")
        self.main_tabs.addTab(td_tab, "时距图")
        self.main_tabs.addTab(region_tab, "区域分析")
        splitter = QSplitter()
        splitter.addWidget(self.left_tabs)
        splitter.addWidget(self.main_tabs)
        splitter.setStretchFactor(1, 1)
        splitter.setCollapsible(1, False)
        splitter.setSizes([315, 1135])
        self.setCentralWidget(splitter)
        self.load_progress = QProgressBar(self)
        self.load_progress.setMinimumWidth(260)
        self.load_progress.setTextVisible(True)
        self.load_progress.hide()
        self.statusBar().addPermanentWidget(self.load_progress)
        self.statusBar().showMessage("请打开单幅 FITS、FITS 文件夹/数据立方或 IDL SAV 数据。")

    @staticmethod
    def _combo(items: list[Any]) -> tuple[Any, Any]:
        from PySide6.QtWidgets import QComboBox

        control = QComboBox()
        for item in items:
            if isinstance(item, tuple):
                control.addItem(item[0], item[1])
            else:
                control.addItem(item)
        return control, None

    @staticmethod
    def _combo_value(control: Any) -> str:
        value = control.currentData()
        return str(value if value is not None else control.currentText())

    @staticmethod
    def _set_combo_value(control: Any, value: str) -> None:
        index = control.findData(value)
        if index < 0:
            index = control.findText(value)
        if index >= 0:
            control.setCurrentIndex(index)

    @staticmethod
    def _checkbox(text: str, checked: bool) -> tuple[Any, Any]:
        from PySide6.QtWidgets import QCheckBox

        control = QCheckBox(text)
        control.setChecked(checked)
        return control, None

    @staticmethod
    def _marker_item(name: str, visible: bool, marker_id: str | None = None) -> QListWidgetItem:
        item = QListWidgetItem(name)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEditable)
        item.setCheckState(Qt.CheckState.Checked if visible else Qt.CheckState.Unchecked)
        if marker_id is not None:
            item.setData(Qt.ItemDataRole.UserRole, marker_id)
        return item

    @staticmethod
    def _next_marker_name(prefix: str, names: list[str]) -> str:
        """Return the first unused S1/R1-style name after arbitrary deletions."""
        used = set(names)
        index = 1
        while f"{prefix}{index}" in used:
            index += 1
        return f"{prefix}{index}"

    def _allocate_marker_name(self, prefix: str, names: list[str]) -> str:
        """Allocate a session-monotonic S/R label that cannot reuse a live name."""
        attribute = "_next_slit_number" if prefix == "S" else "_next_region_number"
        number = max(1, int(getattr(self, attribute, 1)))
        occupied = {name.strip().casefold() for name in names if name.strip()}
        while f"{prefix}{number}".casefold() in occupied:
            number += 1
        setattr(self, attribute, number + 1)
        return f"{prefix}{number}"

    def _path_row(self, marker_id: str) -> int:
        """Find a Slit row by stable UUID, never by array-backed value equality."""
        return next((row for row, item in enumerate(self.paths) if item.id == marker_id), -1)

    def _region_row(self, marker_id: str) -> int:
        """Find a Region row by stable UUID, never by array-backed value equality."""
        return next((row for row, item in enumerate(self.regions) if item.id == marker_id), -1)

    def _install_layout_action(self, toolbar: NavigationToolbar2QT, canvas: Any, key: str) -> None:
        """Replace Matplotlib's ineffective constrained-layout control and restore saved margins."""
        for action in toolbar.actions():
            if action.text() not in {"Subplots", "布局"}:
                continue
            try:
                action.triggered.disconnect()
            except (RuntimeError, TypeError):
                pass
            action.setText("布局")
            action.setToolTip("调整并持久保存当前绘图页的子图边距")
            action.triggered.connect(
                lambda _checked=False, selected_canvas=canvas, selected_key=key:
                self.configure_plot_layout(selected_canvas, selected_key)
            )
            break
        self._restore_plot_layout(canvas, key)

    def _restore_plot_layout(self, canvas: Any, key: str) -> None:
        prefix = f"plot_layout/{key}"
        if not self.settings.contains(f"{prefix}/left"):
            return
        values = {
            name: float(self.settings.value(f"{prefix}/{name}"))
            for name in ("left", "right", "bottom", "top", "wspace", "hspace")
        }
        self._apply_plot_layout(canvas, values)

    @staticmethod
    def _apply_plot_layout(canvas: Any, values: dict[str, float]) -> None:
        canvas.figure.set_layout_engine(None)
        canvas.figure.subplots_adjust(**values)
        canvas.draw_idle()

    def configure_plot_layout(self, canvas: Any, key: str) -> None:
        """Apply layout values immediately and remember them per Image/TD/Region page."""
        subplot = canvas.figure.subplotpars
        current = {
            name: float(getattr(subplot, name))
            for name in ("left", "right", "bottom", "top", "wspace", "hspace")
        }
        dialog = PlotLayoutDialog(current, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        values = dialog.values()
        self._apply_plot_layout(canvas, values)
        for name, value in values.items():
            self.settings.setValue(f"plot_layout/{key}/{name}", value)
        self.settings.sync()

    def _deactivate_image_navigation(self) -> None:
        """Leave pan/zoom mode before a scientific drawing gesture begins."""
        mode = self.image_canvas.axes.get_navigate_mode()
        if mode == "ZOOM":
            self.image_navigation.zoom()
        elif mode == "PAN":
            self.image_navigation.pan()

    def _left_tab_changed(self, index: int) -> None:
        # Only the editor belonging to the active analysis tab may consume
        # mouse events. Checked overlays can still remain visible by setting,
        # but an invisible marker must never be draggable accidentally.
        if index != 2 and self.path_editor.drawing:
            self._discard_unfinished_path()
        if index != 3 and self.region_editor.drawing:
            self._discard_unfinished_region()
        self.path_editor.set_enabled(index == 2)
        self.region_editor.set_enabled(index == 3)
        if index == 2:
            self.path_editor.set_geometry(self.active_path())
        elif index == 3:
            self.region_editor.set_geometry(self.active_region())
        self._refresh_overlays()

    def _deselect_path(self) -> None:
        """Remove editing handles while leaving checked Slit overlays visible."""
        self.active_path_id = None
        self.path_panel.paths.setCurrentRow(-1)
        self.path_panel.paths.clearSelection()
        self.path_editor.set_geometry(None)
        self._refresh_overlays()

    def _deselect_region(self) -> None:
        """Remove editing handles while leaving checked Region overlays visible."""
        self.active_region_id = None
        self.region_panel.regions.setCurrentRow(-1)
        self.region_panel.regions.clearSelection()
        self.region_editor.set_geometry(None)
        self._refresh_overlays()

    def _refresh_overlays(self) -> None:
        """Apply list checkboxes and optional cross-tab retention to the canvas."""
        show_slits = self.keep_cross_tab_overlays or self.left_tabs.currentIndex() == 2
        show_regions = self.keep_cross_tab_overlays or self.left_tabs.currentIndex() == 3
        self.image_canvas.set_paths(self.paths if show_slits else [], self.active_path_id)
        self.image_canvas.set_regions(self.regions if show_regions else [], self.active_region_id)

    def _set_keep_overlays(self, checked: bool) -> None:
        self.keep_cross_tab_overlays = checked
        self.settings.setValue("keep_cross_tab_overlays", checked)
        self._refresh_overlays()

    def configure_cache_size(self) -> None:
        """Set the bounded in-memory FITS cache, applying it to an open folder."""
        value, accepted = QInputDialog.getInt(
            self,
            "内存缓存设置",
            "同时保留的完整帧/已配准 Map 数量（AIA 单帧可能占用数十 MB）：",
            self.frame_cache_size,
            2,
            20,
            1,
        )
        if not accepted:
            return
        self.frame_cache_size = value
        self.settings.setValue("frame_cache_size", value)
        if isinstance(self.dataset, FitsFolderDataset):
            self.dataset.set_cache_size(value)
        self.statusBar().showMessage(
            f"内存缓存已设为 {value} 帧；超出容量的 AIA 帧仍从会话临时 prep 缓存读取。",
            10000,
        )

    def clear_dataset_cache(self) -> None:
        """Release decoded/AIA-prepared frames without closing the current dataset."""
        if self.dataset is None:
            self.statusBar().showMessage("当前没有可清除的数据缓存。")
            return
        self._timer.stop()
        self.play_button.setText("▶ 播放")
        self.dataset.clear_cache(include_disk=True)
        self._fixed_norm = None
        self.statusBar().showMessage(
            "当前数据缓存已清除；已显示的帧仍保留，下一次访问其他帧时会重新读取/处理。",
            10000,
        )

    def _folder_load_progress(self, current: int, total: int, filename: str) -> None:
        """Render FITS header-scan progress in the status bar while excluding user input."""
        self.load_progress.setRange(0, max(1, total))
        self.load_progress.setValue(current)
        self.load_progress.setFormat(f"FITS {current}/{total}")
        self.load_progress.show()
        self.statusBar().showMessage(f"正在读取 FITS 时间/WCS：{filename}")
        QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)

    def _set_load_stage(self, message: str) -> None:
        self.load_progress.setRange(0, 0)
        self.load_progress.setFormat(message)
        self.load_progress.show()
        self.statusBar().showMessage(message)
        QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)

    def _finish_load_progress(self) -> None:
        self.load_progress.hide()
        self.load_progress.setRange(0, 1)
        self.load_progress.setValue(0)

    def _path_visibility_changed(self, row: int, checked: bool) -> None:
        item = self.path_panel.paths.item(row)
        marker_id = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        geometry = next((entry for entry in self.paths if entry.id == marker_id), None)
        if geometry is None and 0 <= row < len(self.paths):
            geometry = self.paths[row]
        if geometry is not None:
            geometry.visible = checked
            if item is not None and item.text().strip():
                geometry.name = item.text().strip()
                if geometry.id == self.active_path_id:
                    self.path_panel.name.setText(geometry.name)
            self._refresh_overlays()

    def _region_visibility_changed(self, row: int, checked: bool) -> None:
        item = self.region_panel.regions.item(row)
        marker_id = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        geometry = next((entry for entry in self.regions if entry.id == marker_id), None)
        if geometry is None and 0 <= row < len(self.regions):
            geometry = self.regions[row]
        if geometry is not None:
            geometry.visible = checked
            if item is not None and item.text().strip():
                geometry.name = item.text().strip()
                if geometry.id == self.active_region_id:
                    self.region_panel.name.setText(geometry.name)
            self._refresh_overlays()
            self._apply_region_result_visibility()

    def _apply_region_result_visibility(self) -> None:
        """Keep Region plots synchronized with the same checked markers shown on the Map."""
        source = self._full_region_result
        if source is None:
            return
        visible_ids = {item.id for item in self.regions if item.visible}
        indices = [index for index, region_id in enumerate(source.region_ids) if region_id in visible_ids]
        if not indices:
            self.region_result = None
            self.region_canvas.clear_plot()
            return
        if isinstance(source, RegionTrendResult):
            self.region_result = RegionTrendResult(
                times=source.times,
                frame_indices=source.frame_indices,
                region_ids=[source.region_ids[index] for index in indices],
                region_names=[source.region_names[index] for index in indices],
                values=source.values[indices],
                statistic=source.statistic,
                region_colors=[source.region_colors[index] for index in indices],
            )
        else:
            self.region_result = RegionHistogramResult(
                region_ids=[source.region_ids[index] for index in indices],
                region_names=[source.region_names[index] for index in indices],
                edges=[source.edges[index] for index in indices],
                counts=[source.counts[index] for index in indices],
                frame_index=source.frame_index,
                bin_width=source.bin_width,
                region_colors=[source.region_colors[index] for index in indices],
                time=source.time,
            )
        self._redraw_region()

    def _choose_marker_color(self, kind: str) -> None:
        is_slit = kind.startswith("slit")
        geometry = self.active_path() if is_slit else self.active_region()
        if geometry is None:
            return
        attribute = {
            "slit": "display_color", "region": "display_color",
            "slit_label": "label_color", "region_label": "label_color",
            "slit_background": "label_background_color",
            "region_background": "label_background_color",
        }[kind]
        previous = str(getattr(geometry, attribute))
        panel = self.path_panel if is_slit else self.region_panel
        initial = previous if previous.lower() != "transparent" else panel.label_background.text()
        color = QColorDialog.getColor(QColor(initial), self, "选择颜色")
        if not color.isValid():
            return
        setattr(geometry, attribute, color.name())
        # A newly created marker uses one colour for its line and label. Keep
        # that relationship when the line is recoloured, but preserve an
        # independently customised label colour.
        if attribute == "display_color" and geometry.label_color == previous:
            geometry.label_color = color.name()
            self._set_color_button(panel.label_color, color.name())
        button = {
            "display_color": panel.color,
            "label_color": panel.label_color,
            "label_background_color": panel.label_background,
        }[attribute]
        if attribute == "label_background_color":
            panel.label_background_transparent.blockSignals(True)
            panel.label_background_transparent.setChecked(False)
            panel.label_background_transparent.blockSignals(False)
            panel.label_background.setEnabled(True)
        button.setText(color.name())
        if attribute == "label_background_color":
            lightness = color.lightness()
            foreground = "#000000" if lightness > 145 else "#ffffff"
            button.setStyleSheet(
                f"QPushButton {{ background-color: {color.name()}; color: {foreground}; }}"
            )
        else:
            button.setStyleSheet(
                f"QPushButton {{ color: {color.name()}; background-color: #404040; }}"
            )
        self._refresh_overlays()

    @staticmethod
    def _set_color_button(button: QPushButton, value: str, *, background: bool = False) -> None:
        """Show a readable colour swatch on a marker-style button."""
        button.setText(value)
        if background:
            if value.lower() == "transparent":
                button.setText("#000000")
                button.setStyleSheet("QPushButton { background-color: #000000; color: #ffffff; }")
                return
            color = QColor(value)
            foreground = "#000000" if color.lightness() > 145 else "#ffffff"
            button.setStyleSheet(
                f"QPushButton {{ background-color: {value}; color: {foreground}; }}"
            )
        else:
            button.setStyleSheet(
                f"QPushButton {{ color: {value}; background-color: #404040; }}"
            )

    def _choose_slope_color(self) -> None:
        color = QColorDialog.getColor(QColor(self.slope_color.text()), self, "选择速度线颜色")
        if color.isValid():
            self._set_color_button(self.slope_color, color.name())
            # A line colour change deliberately resets its annotation text to
            # the same colour. The user may then customise Text independently.
            self._set_color_button(self.slope_text_color, color.name())
            index = int(self.slope_selection.currentData() or 0)
            if not self.slope_auto_colors.isChecked() and index != 0:
                self.td_canvas.set_measurement_style(
                    index, line_color=color.name(), text_color=color.name()
                )
            self._apply_slope_style()

    def _choose_slope_text_color(self) -> None:
        color = QColorDialog.getColor(
            QColor(self.slope_text_color.text()), self, "选择速度标注文字颜色"
        )
        if color.isValid():
            self._set_color_button(self.slope_text_color, color.name())
            index = int(self.slope_selection.currentData() or 0)
            if not self.slope_auto_colors.isChecked() and index != 0:
                self.td_canvas.set_measurement_style(index, text_color=color.name())
            self._apply_slope_style()

    def _choose_slope_background(self) -> None:
        color = QColorDialog.getColor(
            QColor(self.slope_background.text()), self, "选择速度标注背景颜色"
        )
        if color.isValid():
            self._set_color_button(self.slope_background, color.name(), background=True)
            self.slope_background_transparent.blockSignals(True)
            self.slope_background_transparent.setChecked(False)
            self.slope_background_transparent.blockSignals(False)
            index = int(self.slope_selection.currentData() or 0)
            if not self.slope_auto_colors.isChecked() and index != 0:
                self.td_canvas.set_measurement_style(index, background_color=color.name())
            self._apply_slope_style()
            self._sync_selected_slope_controls()

    def _slope_background_transparency_changed(self, checked: bool) -> None:
        """Apply transparency only to Next, All, or the selected velocity marker."""
        index = int(self.slope_selection.currentData() or 0)
        background = "transparent" if checked else self.slope_background.text()
        if not self.slope_auto_colors.isChecked() and index != 0:
            self.td_canvas.set_measurement_style(index, background_color=background)
        self._apply_slope_style()
        self._sync_selected_slope_controls()

    def _slope_fontsize_changed(self, value: float) -> None:
        """Apply annotation size to Next, All, or the selected velocity marker."""
        target = int(self.slope_selection.currentData() or 0)
        if self.slope_auto_colors.isChecked():
            self.td_canvas.set_measurement_style(-1, font_size=value)
        elif target != 0:
            self.td_canvas.set_measurement_style(target, font_size=value)
        self._apply_slope_style()

    def _slope_auto_colors_changed(self, checked: bool) -> None:
        self._apply_slope_style()
        self._sync_selected_slope_controls()

    def _refresh_slope_measurement_selector(self) -> None:
        """Rebuild the per-measurement selector after add, clear, or TD redraw."""
        count = self.td_canvas.measurement_count
        self.slope_selection.blockSignals(True)
        self.slope_selection.clear()
        self.slope_selection.addItem("Next measurement", 0)
        if count:
            self.slope_selection.addItem("All", -1)
        for index in range(1, count + 1):
            self.slope_selection.addItem(f"v_{index}", index)
        self.slope_selection.setCurrentIndex(
            self.slope_selection.findData(count) if count else 0
        )
        self.slope_selection.blockSignals(False)
        self._sync_selected_slope_controls()

    def _select_slope_measurement(self, index: int) -> None:
        combo_index = self.slope_selection.findData(index)
        if combo_index < 0:
            return
        self.slope_selection.blockSignals(True)
        self.slope_selection.setCurrentIndex(combo_index)
        self.slope_selection.blockSignals(False)
        self._sync_selected_slope_controls()

    def _slope_selection_changed(self) -> None:
        index = int(self.slope_selection.currentData() or 0)
        self.td_canvas.select_measurement(index)
        self._sync_selected_slope_controls()

    def _sync_selected_slope_controls(self) -> None:
        index = int(self.slope_selection.currentData() or 0)
        style = self.td_canvas.measurement_style(index)
        if style is not None:
            self._set_color_button(self.slope_color, style[0])
            self._set_color_button(self.slope_text_color, style[1])
            self._set_color_button(self.slope_background, style[2], background=True)
            self.slope_background_transparent.blockSignals(True)
            self.slope_background_transparent.setChecked(style[2].lower() == "transparent")
            self.slope_background_transparent.blockSignals(False)
            self.slope_fontsize.blockSignals(True)
            self.slope_fontsize.setValue(style[3])
            self.slope_fontsize.blockSignals(False)
        editable = not self.slope_auto_colors.isChecked() and style is not None
        self.slope_selection.setEnabled(not self.slope_auto_colors.isChecked())
        self.slope_color.setEnabled(editable)
        self.slope_text_color.setEnabled(editable)
        self.slope_background_transparent.setEnabled(editable)
        self.slope_fontsize.setEnabled(self.slope_auto_colors.isChecked() or editable)
        self.slope_background.setEnabled(
            editable and not self.slope_background_transparent.isChecked()
        )

    def _apply_slope_style(self) -> None:
        target = int(self.slope_selection.currentData() or 0)
        if self.slope_auto_colors.isChecked():
            target = 0
        defaults = self.td_canvas.measurement_style(0)
        assert defaults is not None
        if target == 0:
            line_color = self.slope_color.text()
            text_color = self.slope_text_color.text()
            background = (
                "transparent"
                if self.slope_background_transparent.isChecked()
                else self.slope_background.text()
            )
        else:
            line_color, text_color, background = defaults[:3]
        self.td_canvas.set_slope_style(
            line_color, self.slope_width.value(),
            self.slope_fontsize.value() if target == 0 else defaults[3],
            self._combo_value(self.slope_linestyle),
            text_color, self.slope_precision.value(), background,
            self._combo_value(self.slope_velocity_unit), self.slope_auto_colors.isChecked(),
        )

    def _sync_region_legend_size(self, *_args: object) -> None:
        if self.region_sync_legend.isChecked():
            self.region_legend_size.blockSignals(True)
            self.region_legend_size.setValue(self.region_title_size.value())
            self.region_legend_size.blockSignals(False)
        self._redraw_region()

    def _td_range_mode_changed(self) -> None:
        """Enable the TD range controls that are actually used and redraw."""
        mode = self._combo_value(self.td_norm)
        manual = mode == "manual"
        percentile = mode == "percentile"
        self.td_vmin.setEnabled(manual); self.td_vmax.setEnabled(manual)
        self.td_percentile_low.setEnabled(percentile); self.td_percentile_high.setEnabled(percentile)
        self._redraw_td()

    def show_drawing_help(self) -> None:
        QMessageBox.information(
            self,
            "切片/区域绘制与科学参数说明",
            "【缩放与绘制】先用图像上方放大镜拖框放大；再关闭放大镜，或直接点击“新建切片/绘制新区域”（程序会自动退出缩放模式）。\n\n"
            "【Slit】在 Slit Manager 最左侧点击“New Slit”并从下拉菜单直接选择 Line、Polyline 或 Smooth Curve。程序会切回图像页并独占 Slit 鼠标事件。直线依次单击起点和终点后自动完成；折线/平滑曲线逐点单击，在原地双击或单击右键完成。中间的 Delete Selected 只删除列表当前选中的 Slit，右侧 Help 打开本说明。完成后可拖动控制点和标签；在空白处左击可取消选择并隐藏控制点。标签背景可勾选 Transparent。\n\n"
            "【Region】在 Region Manager 点击“New Region”并直接选择形状。圆形：单击圆心，移动鼠标预览，再单击确定半径。长方形：先单击一条边的两个端点，再移动并单击确定高度。多边形：逐点单击，在原地双击或单击右键闭合。区域标签背景同样可设为 Transparent。区域列表的勾选状态同时控制 Map、时间变化和直方图；未勾选区域不参与新计算。范围直方图使用一基 Start/End 和 Step；也可先缩放 TD，再点击“使用 TD 当前时间范围”。完成后可用滑块、播放按钮逐帧检查，并导出 MP4/GIF。\n\n"
            "【切片坐标保存方式】“像素坐标”保存参考帧中的 x/y；“世界坐标/WCS”把切片保存为太阳物理坐标。它决定切片本身如何被记录。\n\n"
            "【逐帧跟踪方式】“固定像素位置”在每帧使用相同 x/y；“固定世界坐标”利用每帧 WCS 把同一太阳位置重新投影到像素，可适应 CRPIX/指向变化；“太阳自转跟踪”目前仍为实验功能。世界坐标保存通常应配合固定世界坐标跟踪。\n\n"
            "【时距图距离单位】只决定生成结果纵轴的累计弧长单位，可选 pixel、arcsec、km、Mm；不会改变切片保存或跟踪方式。km/Mm 仅在 WCS 与太阳距离足以可靠换算时可用。\n\n"
            "【速度测量】相关选项集中在 Velocity Measurement。每两次点击生成一条不带端点圆圈的速度线，自动标为 v₁、v₂…；文字可直接拖动，默认单位为 km/s。Auto colors 开启时各组自动配色且 Selected 不可用；关闭后可选择 All、v_n，或直接点击线/文字，分别设置 Line、Text 与 Text Background。修改 Line 时 Text 会先同步为同色，随后仍可单独调整 Text；Transparent 也只作用于当前选项。涉及 pixel 的换算只在结果保存了可靠 WCS 像素尺度时可用。\n\n"
            "【曲线平滑参数 s】仅用于平滑曲线。s=0 时样条经过控制点；s 越大，允许样条偏离控制点的平方残差越大，曲线通常越平滑。它不是像素宽度，也不是采样步长。建议先从 0 开始，小幅增加并观察预览。\n\n"
            "【Normalization】Percentile 按可设置的 Lower/Upper percentile 确定显示上下限（默认 1%/99%）；Manual 使用 vmin/vmax；Min–Max 使用当前数据极值；ZScale 使用天文图像常用的鲁棒线性范围。切换或修改参数会立即重绘，但不修改原数据。\n\n"
            "【动画导出】默认导出图像窗口当前显示的坐标范围；也可以改为完整图像。坐标轴、实际观测时间、标题、Colorbar、Slit 和 Region 均可分别选择是否写入每一帧。\n\n"
            "【缓存与保存视图】打开新的数据源时会自动释放上一个数据集的内存与 AIA 临时缓存；也可用“设置 → 清除当前数据缓存”手动释放。保存当前视图时可独立选择是否包含坐标轴、标题和 Colorbar。\n\n"
            "【绘图历史】“查看 → 绘图历史”按时间记录 Map 数据载入、已完成的 Slit/Region、TD、区域趋势、直方图和直方图序列；Region 结果保存轻量快照，因此共享画布被后续绘图覆盖后仍可恢复。点击可回到对应页面，同一数据源仍打开时还会重新选中标记。默认最多 20 条，可在历史菜单底部调整。\n\n"
            "【科学宽度阴影】勾选后，Map 上的半透明色带显示实际 Slit 宽度，并随数值/单位实时更新；它对应法向取样范围。显示线宽只改变中心线的屏幕粗细，两者完全独立。\n\n"
            "【绘图页布局】Image、Time–Distance 和 Region 工具栏中的“布局”用于设置 Left/Right/Top/Bottom/WSpace/HSpace。设置会立即应用并按页面保存；这些参数是画布边距/子图间距，不是数据网格刻度间隔。",
        )

    def show_feature_overview(self) -> None:
        QMessageBox.information(
            self,
            "Solar Time–Distance Explorer — 主要功能",
            "本软件可打开单幅 FITS、FITS 文件夹、三维 FITS 和 SSW Map SAV；显示太阳 WCS 坐标；浏览及导出动画；绘制有限宽度直线/折线/平滑切片；使用真实观测时间生成时距图；测量传播速度；分析多个闭合区域的时间变化与直方图；并导出科研图像和数值数据。\n\n"
            "图像上方的上一帧/播放暂停/下一帧按钮用于快速浏览。图像工具栏提供复位、前进/后退、平移和矩形框选放大；动画可导出当前视口，并选择坐标、观测时间、Colorbar 与标记。设置菜单可调整内存缓存帧数；AIA 首次配准仍需要计算，之后优先使用内存或会话临时缓存。TD 与区域分析页可编辑英文标题、坐标标题、刻度字号、网格、线型/尺度，并直接导出 PDF/PNG/EPS/SVG/TIFF。区域直方图显示实际帧时间，并可选柱状图或线状图。主工具栏“保存当前视图”会根据右侧当前页自动保存 Map、TD 或区域图。所有科研图内文字保持英文。详细鼠标操作与参数说明见“帮助 → 切片/区域绘制与科学参数说明”。",
        )

    def _build_actions(self) -> None:
        self.open_image_action = QAction("打开单幅 FITS 图像…", self, triggered=self.open_fits_image)
        self.open_folder_action = QAction("打开 FITS 文件夹…", self, triggered=self.open_folder)
        self.open_cube_action = QAction("打开三维 FITS 数据立方…", self, triggered=self.open_fits_cube)
        self.open_sav_action = QAction("打开 IDL SAV…", self, triggered=self.open_sav)
        self.open_project_action = QAction("打开项目…", self, triggered=self.open_project)
        self.save_project_action = QAction("保存项目…", self, triggered=self.save_project)
        self.save_current_view_action = QAction("保存当前视图…", self, triggered=self.save_current_view)
        self.save_map_action = QAction("保存 Map 图像…", self, triggered=self.save_current_frame)
        self.save_td_action = QAction("保存 Time–Distance 图…", self, triggered=self.export_td_figure)
        self.save_region_action = QAction("保存区域分析图…", self, triggered=self.export_region_figure)
        self.exit_action = QAction("退出", self, triggered=self.close)
        self.metadata_action = QAction("当前 FITS 元数据…", self, triggered=self.show_metadata)
        self.new_path_action = QAction("新建切片", self, triggered=self.new_path)
        self.generate_action = QAction("生成时距图", self, triggered=self.generate_td)
        self.about_action = QAction("关于", self, triggered=self.show_about)
        self.log_action = QAction("打开日志文件夹", self, triggered=self.open_log_folder)
        self.feature_help_action = QAction("主要功能简介", self, triggered=self.show_feature_overview)
        self.drawing_help_action = QAction("切片/区域绘制与科学参数说明", self, triggered=self.show_drawing_help)
        self.keep_overlays_action = QAction("切换切片/区域页时保留已勾选标记", self)
        self.keep_overlays_action.setCheckable(True)
        self.keep_overlays_action.setChecked(self.keep_cross_tab_overlays)
        self.keep_overlays_action.toggled.connect(self._set_keep_overlays)
        self.cache_size_action = QAction("内存缓存帧数…", self, triggered=self.configure_cache_size)
        self.clear_cache_action = QAction("清除当前数据缓存", self, triggered=self.clear_dataset_cache)
        self.history_limit_action = QAction("设置历史记录条数…", self, triggered=self.configure_history_limit)
        self.clear_history_action = QAction("清除绘图历史", self, triggered=self.clear_history)

        for action, shortcut in (
            (self.new_path_action, "N"),
            (self.generate_action, "Ctrl+G"),
        ):
            action.setShortcut(QKeySequence(shortcut))
            self.addAction(action)
        for key, callback in (
            ("Left", lambda: self._move_frame(-1)),
            ("Right", lambda: self._move_frame(1)),
            ("PageUp", lambda: self._move_frame(-10)),
            ("PageDown", lambda: self._move_frame(10)),
            ("Space", self.toggle_animation),
            ("Return", self.finish_active_drawing),
            ("Escape", self.cancel_active_drawing),
            ("Delete", self.delete_active_path),
        ):
            shortcut = QAction(self)
            shortcut.setShortcut(QKeySequence(key))
            shortcut.triggered.connect(callback)
            self.addAction(shortcut)

    def _build_menus(self) -> None:
        file_menu = self.menuBar().addMenu("文件(&F)")
        file_menu.addActions([self.open_image_action, self.open_folder_action, self.open_cube_action, self.open_sav_action])
        file_menu.addSeparator()
        file_menu.addActions([self.open_project_action, self.save_project_action])
        file_menu.addSeparator()
        export_menu = file_menu.addMenu("保存科研图像")
        export_menu.addActions([
            self.save_current_view_action, self.save_map_action,
            self.save_td_action, self.save_region_action,
        ])
        file_menu.addAction(self.exit_action)
        view_menu = self.menuBar().addMenu("查看(&V)")
        view_menu.addAction(self.metadata_action)
        self.history_menu = view_menu.addMenu("绘图历史")
        self._rebuild_history_menu()
        animation_menu = self.menuBar().addMenu("动画(&A)")
        animation_menu.addAction("播放/暂停", self.toggle_animation, QKeySequence("Space"))
        animation_menu.addAction("导出 GIF / MP4…", self.export_animation)
        td_menu = self.menuBar().addMenu("时距图(&T)")
        td_menu.addAction("导出图像…", self.export_td_figure)
        td_menu.addAction("导出数值数据…", self.export_td_data)
        td_menu.addAction("测量速度", lambda: self.td_canvas.enable_slope_measurement(True))
        td_menu.addAction("清除斜率标记", self.td_canvas.clear_measurements)
        settings_menu = self.menuBar().addMenu("设置(&S)")
        settings_menu.addAction(self.keep_overlays_action)
        settings_menu.addAction(self.cache_size_action)
        settings_menu.addAction(self.clear_cache_action)
        help_menu = self.menuBar().addMenu("帮助(&H)")
        help_menu.addActions([self.feature_help_action, self.drawing_help_action, self.about_action, self.log_action])

    def _record_history(
        self,
        description: str,
        *,
        main_tab: int,
        left_tab: int | None = None,
        marker_kind: str | None = None,
        marker_id: str | None = None,
        frame: int | None = None,
        region_result: RegionTrendResult | RegionHistogramResult | None = None,
        histogram_sequence: RegionHistogramSequence | None = None,
        histogram_position: int = 0,
    ) -> None:
        """Record navigation plus lightweight Region result snapshots.

        Dataset frames are never copied. Region curves and histogram bins are
        retained so two results rendered in the shared canvas remain independently
        recoverable from the bounded history menu.
        """
        self._history_entries.insert(
            0,
            {
                "id": str(uuid4()),
                "time": datetime.now().strftime("%H:%M:%S"),
                "description": description,
                "main_tab": main_tab,
                "left_tab": left_tab,
                "marker_kind": marker_kind,
                "marker_id": marker_id,
                "frame": self.current_frame if frame is None else frame,
                "source": str(self.dataset.source) if self.dataset is not None else None,
                "region_result": deepcopy(region_result),
                "histogram_sequence": deepcopy(histogram_sequence),
                "histogram_position": int(histogram_position),
            },
        )
        del self._history_entries[max(1, self.history_limit):]
        if hasattr(self, "history_menu"):
            self._rebuild_history_menu()

    def _rebuild_history_menu(self) -> None:
        self.history_menu.clear()
        if not self._history_entries:
            empty = self.history_menu.addAction("暂无绘图历史")
            empty.setEnabled(False)
        else:
            for entry in self._history_entries:
                action = self.history_menu.addAction(
                    f"[{entry['time']}] {entry['description']}"
                )
                action.triggered.connect(
                    lambda _checked=False, entry_id=entry["id"]: self._open_history_entry(entry_id)
                )
        self.history_menu.addSeparator()
        self.history_menu.addAction(self.history_limit_action)
        self.history_menu.addAction(self.clear_history_action)

    def configure_history_limit(self) -> None:
        value, accepted = QInputDialog.getInt(
            self, "绘图历史", "最多保留的历史条数：", self.history_limit, 5, 200, 1
        )
        if not accepted:
            return
        self.history_limit = value
        self.settings.setValue("history_limit", value)
        del self._history_entries[value:]
        self._rebuild_history_menu()

    def clear_history(self) -> None:
        self._history_entries.clear()
        self._history_marker_ids.clear()
        self._rebuild_history_menu()
        self.statusBar().showMessage("绘图历史已清除。")

    def _open_history_entry(self, entry_id: str) -> None:
        entry = next((item for item in self._history_entries if item["id"] == entry_id), None)
        if entry is None:
            return
        current_source = str(self.dataset.source) if self.dataset is not None else None
        if entry.get("source") and entry["source"] != current_source:
            self.statusBar().showMessage("该历史项属于先前的数据源；请先重新打开对应数据。", 8000)
            return
        frame = entry.get("frame")
        if self.dataset is not None and isinstance(frame, int) and 0 <= frame < self.dataset.n_frames:
            self.set_current_frame(frame)
        left_tab = entry.get("left_tab")
        if isinstance(left_tab, int):
            self.left_tabs.setCurrentIndex(left_tab)
        self.main_tabs.setCurrentIndex(int(entry["main_tab"]))
        sequence = entry.get("histogram_sequence")
        snapshot = entry.get("region_result")
        if isinstance(sequence, RegionHistogramSequence):
            self._install_region_histogram_sequence(
                deepcopy(sequence), int(entry.get("histogram_position", 0)), record=False
            )
        elif isinstance(snapshot, (RegionTrendResult, RegionHistogramResult)):
            self._region_hist_timer.stop()
            self.region_hist_play.setText("▶ 播放")
            self.region_histogram_player.setVisible(False)
            self._region_hist_sequence = None
            self._full_region_result = deepcopy(snapshot)
            self._apply_region_result_visibility()
        marker_id = entry.get("marker_id")
        if entry.get("marker_kind") == "slit" and marker_id:
            row = next((i for i, item in enumerate(self.paths) if item.id == marker_id), -1)
            if row >= 0:
                self.path_panel.paths.setCurrentRow(row)
                self._active_path_changed(row)
        elif entry.get("marker_kind") == "region" and marker_id:
            row = next((i for i, item in enumerate(self.regions) if item.id == marker_id), -1)
            if row >= 0:
                self.region_panel.regions.setCurrentRow(row)
                self._active_region_changed(row)
        self.statusBar().showMessage(f"已跳转：{entry['description']}")

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("常用操作")
        toolbar.setMovable(False)
        toolbar.addActions([
            self.open_image_action, self.open_folder_action,
            self.open_cube_action, self.open_sav_action,
        ])
        save_button = QToolButton(toolbar)
        save_button.setDefaultAction(self.save_current_view_action)
        save_menu = QMenu(save_button)
        save_menu.addActions([
            self.save_current_view_action, self.save_map_action,
            self.save_td_action, self.save_region_action,
        ])
        save_button.setMenu(save_menu)
        save_button.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        save_button.setToolTip("单击保存当前页；点右侧箭头可明确选择 Map、TD 或区域图。")
        toolbar.addWidget(save_button)
        self.addToolBar(toolbar)

    def open_fits_image(self) -> None:
        """Open one 2-D FITS file as a WCS-aware scientific image preview."""
        path, _ = QFileDialog.getOpenFileName(
            self, "打开单幅 FITS 图像", filter="FITS (*.fits *.fit *.fts)"
        )
        if not path:
            return
        try:
            dataset = FitsImageDataset(path, prepare_aia=True)
            self._install_dataset(dataset)
            self._show_coordinate_notice(dataset)
        except Exception as exc:
            LOG.exception("Single FITS image open failed")
            show_error(self, "无法打开 FITS 图像", str(exc))

    def open_folder(self) -> None:
        """Choose and scan a FITS folder without reading all image arrays."""
        folder = QFileDialog.getExistingDirectory(self, "打开 FITS 文件夹")
        if not folder:
            return
        self._set_load_stage("正在准备 FITS 文件夹扫描…")
        try:
            dataset = FitsFolderDataset(
                folder,
                cache_size=self.frame_cache_size,
                progress=self._folder_load_progress,
            )
            if not self._confirm_or_configure_time(dataset):
                return
            self._set_load_stage("正在准备首帧图像与 WCS…")
            self._install_dataset(dataset)
            self._show_coordinate_notice(dataset)
        except Exception as exc:
            LOG.exception("Folder open failed")
            show_error(self, "无法打开 FITS 文件夹", str(exc))
        finally:
            self._finish_load_progress()

    def open_fits_cube(self) -> None:
        """Open a 3-D FITS cube and force a decision for low-confidence axes."""
        path, _ = QFileDialog.getOpenFileName(self, "打开三维 FITS 数据立方", filter="FITS (*.fits *.fit *.fts)")
        if not path:
            return
        try:
            detection = FitsCubeDataset.inspect(path)
            axis = detection.axis
            if detection.confidence != "High":
                confidence = {"High": "高", "Low": "低", "Uncertain": "不确定"}.get(
                    detection.confidence, detection.confidence
                )
                reason = {
                    "Unique smallest dimension heuristic.": "依据唯一最小维度进行启发式判断。",
                    "More than one FITS axis looks temporal.": "多个 FITS 轴都可能是时间轴。",
                    "No time CTYPE and spatial dimensions are ambiguous.": "未找到时间 CTYPE，且空间维度存在歧义。",
                }.get(detection.reason, detection.reason)
                dialog = TimeAxisDialog(
                    f"检测到的时间轴：{axis if axis is not None else '不确定'}；"
                    f"置信度：{confidence}。\n{reason}",
                    self,
                )
                if dialog.exec() != QDialog.DialogCode.Accepted:
                    return
                axis = dialog.selected_axis()
            if axis is None:
                return
            dataset = FitsCubeDataset(path, axis)
            if not self._confirm_or_configure_time(dataset):
                return
            self._install_dataset(dataset)
        except Exception as exc:
            LOG.exception("FITS cube open failed")
            show_error(self, "无法打开 FITS 数据立方", str(exc))

    def open_sav(self) -> None:
        """Open an SSW map structure, numeric image, or numeric image cube."""
        path, _ = QFileDialog.getOpenFileName(self, "打开 IDL SAV", filter="IDL SAV (*.sav)")
        if not path:
            return
        try:
            variables = inspect_sav(path)
            supported = {"SSW map structure", "candidate cube", "candidate image (pixel axes)"}
            candidates = [name for name, info in variables.items() if info[2] in supported]
            if not candidates:
                raise ValueError(
                    "未找到标准 SSW Map 结构体或二维/三维数值图像变量。"
                )
            category_labels = {
                "SSW map structure": "标准 SSW Map 结构体",
                "candidate cube": "候选三维图像立方",
                "candidate image (pixel axes)": "候选二维图像（像素坐标）",
            }
            variable, accepted = QInputDialog.getItem(
                self,
                "选择图像变量",
                "变量：",
                [
                    f"{name}: {category_labels[variables[name][2]]}，"
                    f"{variables[name][0]} {variables[name][1]}"
                    for name in candidates
                ],
                0,
                False,
            )
            if not accepted:
                return
            selected = variable.split(":", 1)[0]
            category = variables[selected][2]
            if category == "SSW map structure":
                dataset = SavMapDataset(path, selected)
                if dataset.n_frames > 1 and not self._confirm_or_configure_time(dataset):
                    return
                self._install_dataset(dataset)
                self._show_coordinate_notice(dataset)
                return
            if category == "candidate image (pixel axes)":
                dataset = SavImageDataset(path, selected)
                self._install_dataset(dataset)
                self._show_coordinate_notice(dataset)
                return
            from scipy.io import readsav
            import numpy as np

            raw = readsav(path, python_dict=True)
            detection = detect_sav_time_axis(np.asarray(raw[selected]))
            confidence = {"High": "高", "Low": "低", "Uncertain": "不确定"}.get(
                detection.confidence, detection.confidence
            )
            reason = {
                "Unique smallest dimension heuristic.": "依据唯一最小维度进行启发式判断。",
                "SAV has no FITS CTYPE; select an axis.": "SAV 没有 FITS CTYPE，请手动选择时间轴。",
            }.get(detection.reason, detection.reason)
            axis_dialog = TimeAxisDialog(
                f"检测到的时间轴：{detection.axis if detection.axis is not None else '不确定'}；"
                f"置信度：{confidence}。\n{reason}",
                self,
            )
            if detection.axis is not None:
                axis_dialog.axis.setCurrentIndex(detection.axis)
            if axis_dialog.exec() != QDialog.DialogCode.Accepted:
                return
            time_candidates = [
                name
                for name, info in variables.items()
                if len(info[1]) == 1 and any(token in name.lower() for token in ("time", "date", "utc", "t_obs"))
            ]
            time_variable: str | None = None
            if time_candidates:
                choice, accepted = QInputDialog.getItem(
                    self,
                    "可选的 SAV 时间变量",
                    "时间变量：",
                    ["（无）"] + time_candidates,
                    0,
                    False,
                )
                if accepted and choice != "（无）":
                    time_variable = choice
            dataset = SavCubeDataset(path, selected, axis_dialog.selected_axis(), time_variable)
            if not self._confirm_or_configure_time(dataset):
                return
            self._install_dataset(dataset)
            self._show_coordinate_notice(dataset)
        except Exception as exc:
            LOG.exception("SAV open failed")
            show_error(self, "无法打开 IDL SAV", str(exc))

    def _confirm_or_configure_time(self, dataset: TimeSeriesDataset) -> bool:
        """Ask explicitly only when sources supply no defensible time array."""
        if dataset.times is not None:
            return True
        dialog = ManualTimeDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False
        try:
            start, cadence = dialog.configured_values()
            dataset.set_times(manual_times(dataset.n_frames, start, cadence))
            return True
        except Exception as exc:
            show_error(self, "时间设置无效", str(exc))
            return False

    def _show_coordinate_notice(self, dataset: TimeSeriesDataset) -> None:
        """Explain coordinate fallback or AIA registration without hiding pixels."""
        notice = getattr(dataset, "map_notice", None)
        if not notice:
            return
        if getattr(dataset, "aia_prepared", False):
            self.statusBar().showMessage(str(notice), 12000)
            return
        QMessageBox.warning(
            self,
            "坐标 / Map 信息",
            f"{notice}\n\n图像仍可预览，并可使用像素坐标切片。",
        )

    def _install_dataset(self, dataset: TimeSeriesDataset) -> None:
        """Replace only source-specific state; paths/results do not leak across datasets."""
        previous = self.dataset
        previous_cache_cleared = previous is not None and previous is not dataset
        if previous_cache_cleared:
            try:
                previous.close()
            except Exception:
                LOG.warning("Could not fully clear the previous dataset cache", exc_info=True)
        self.dataset = dataset
        self.current_frame = 0
        self.reference_frame = 0
        self.paths.clear()
        self.active_path_id = None
        self._next_slit_number = 1
        self.td_result = None
        self.regions.clear()
        self.active_region_id = None
        self._next_region_number = 1
        self.region_result = None
        self._full_region_result = None
        self._region_hist_timer.stop()
        self._region_hist_sequence = None
        self._region_hist_position = 0
        self.region_histogram_player.setVisible(False)
        self.region_hist_play.setText("▶ 播放")
        self._fixed_norm = None
        self.path_panel.paths.clear()
        self.region_panel.regions.clear()
        self.region_panel.set_frame_range(dataset.n_frames)
        self.image_canvas.set_paths([])
        self.image_canvas.set_regions([])
        self.frame_slider.blockSignals(True)
        self.frame_slider.setRange(0, dataset.n_frames - 1)
        self.frame_slider.setValue(0)
        self.frame_slider.blockSignals(False)
        first_map = dataset.get_map(0)
        first_wcs = first_map.wcs if first_map is not None else dataset.get_wcs(0)
        world_available = bool(first_wcs is not None and first_wcs.has_celestial)
        self._set_combo_value(self.path_panel.coordinate_mode, "world" if world_available else "pixel")
        self._set_combo_value(self.path_panel.tracking, "world_fixed" if world_available else "pixel_fixed")
        self.path_panel.width_unit.setCurrentText("arcsec" if world_available else "pixel")
        self.path_panel.distance_unit.setCurrentText("arcsec" if world_available else "pixel")
        self.path_panel.normalize_exposure.setChecked(True)
        self._set_combo_value(self.region_panel.coordinate_mode, "world" if world_available else "pixel")
        summary = dataset.summary()
        start = summary.start.isot if summary.start is not None else "未设置（帧序号）"
        end = summary.end.isot if summary.end is not None else "未设置"
        cadence_type = {"nearly uniform": "近似均匀", "irregular": "不均匀"}.get(
            summary.cadence_type, summary.cadence_type
        )
        cadence = (
            f"{summary.median_cadence_s:.4g} s; range {summary.min_cadence_s:.4g}–"
            f"{summary.max_cadence_s:.4g} s；{cadence_type}"
            if summary.median_cadence_s is not None
            else "未知 / 帧序号"
        )
        source_label = {
            "fits_image": "单幅 FITS 图像",
            "fits_folder": "FITS 文件夹序列",
            "fits_cube": "三维 FITS 数据立方",
            "sav_cube": "SAV 图像立方",
            "sav_image": "SAV 二维图像",
            "sav_ssw_map": "SSW Map SAV",
        }.get(summary.source_type, summary.source_type)
        self.dataset_panel.set_summary(
            f"<b>{source_label}</b><br>帧数：{summary.n_frames}<br>"
            f"图像尺寸：{summary.shape[1]} × {summary.shape[0]}<br>"
            f"起始时间：{start}<br>结束时间：{end}<br>时间间隔：{cadence}<br>"
            f"坐标：{'太阳/世界 WCS' if world_available else '像素（无可靠 WCS）'}",
            dataset.n_frames,
        )
        self.set_current_frame(0)
        cache_note = "；已清除上一数据集缓存" if previous_cache_cleared else ""
        self.statusBar().showMessage(
            f"已从 {dataset.source} 加载 {dataset.n_frames} 帧{cache_note}"
        )
        self._record_history(
            f"Opened map data: {Path(str(dataset.source)).name}", main_tab=0, left_tab=0, frame=0
        )

    def set_current_frame(self, index: int) -> None:
        """Render current source frame; only this one image needs RAM for a folder."""
        if self.dataset is None:
            return
        index = max(0, min(index, self.dataset.n_frames - 1))
        self.current_frame = index
        self.frame_slider.blockSignals(True)
        self.frame_slider.setValue(index)
        self.frame_slider.blockSignals(False)
        frame = self.dataset.get_frame(index)
        solar_map = self.dataset.get_map(index)
        display_wcs = solar_map.wcs if solar_map is not None else self.dataset.get_wcs(index)
        time = self.dataset.get_time(index)
        time_text = time.isot if time is not None else f"Frame {index + 1}"
        plot_kind = "Solar Map" if display_wcs is not None and display_wcs.has_celestial else "Image"
        norm = self._fixed_norm if self.image_panel.fixed.isChecked() else None
        rendered_norm = self.image_canvas.show_frame(
            frame,
            display_wcs,
            f"{plot_kind} — {time_text}",
            cmap=self.image_panel.cmap_name(),
            normalization_mode=self._combo_value(self.image_panel.normalization),
            stretch=self._combo_value(self.image_panel.stretch),
            vmin=self.image_panel.vmin.value(),
            vmax=self.image_panel.vmax.value(),
            low_percent=self.image_panel.percentile_low.value(),
            high_percent=self.image_panel.percentile_high.value(),
            fixed_norm=norm,
            solar_map=solar_map,
        )
        if self.image_panel.fixed.isChecked() and self._fixed_norm is None:
            self._fixed_norm = rendered_norm
        self._refresh_overlays()
        self.frame_label.setText(f"帧：{index + 1} / {self.dataset.n_frames}")
        self.time_label.setText(f"时间：{time_text}")

    def _move_frame(self, delta: int) -> None:
        if self.dataset is not None:
            self.set_current_frame(self.current_frame + delta)

    def _reference_changed(self, index: int) -> None:
        self.reference_frame = index
        if self.dataset is not None:
            self.set_current_frame(index)
            self.statusBar().showMessage(f"参考帧已设为第 {index + 1} 帧。")

    def _reset_image_norm(self) -> None:
        """Apply range settings immediately without rereading or re-preparing FITS."""
        self._fixed_norm = None
        rendered = self.image_canvas.update_display(
            self.image_panel.cmap_name(),
            self._combo_value(self.image_panel.normalization),
            self._combo_value(self.image_panel.stretch),
            self.image_panel.vmin.value(),
            self.image_panel.vmax.value(),
            low_percent=self.image_panel.percentile_low.value(),
            high_percent=self.image_panel.percentile_high.value(),
        )
        if self.image_panel.fixed.isChecked():
            self._fixed_norm = rendered

    def toggle_animation(self) -> None:
        """Start/stop a lightweight preview timer; exporting uses source data separately."""
        if self.dataset is None:
            return
        if self._timer.isActive():
            self._timer.stop()
            self.play_button.setText("▶ 播放")
        else:
            self._animation_speed_changed(self.image_panel.speed.value())
            self._timer.start()
            self.play_button.setText("⏸ 暂停")

    def _animation_speed_changed(self, fps: float) -> None:
        """Keep the live image preview timer synchronized with the Animation panel."""
        self._timer.setInterval(max(1, round(1000.0 / max(float(fps), 0.01))))

    def _advance_animation(self) -> None:
        if self.dataset is None:
            return
        self.set_current_frame((self.current_frame + 1) % self.dataset.n_frames)

    def new_path(self, selected_type: str | None = None) -> None:
        """Begin mouse selection of a new centreline with controls from Path panel."""
        if self.dataset is None:
            self.statusBar().showMessage("请先加载数据，再选择切片。")
            return
        self.main_tabs.setCurrentIndex(0)
        self.left_tabs.setCurrentIndex(2)
        self.path_editor.set_enabled(True)
        self._discard_unfinished_path()
        self._deactivate_image_navigation()
        self.region_editor.set_geometry(None)
        path_type = selected_type or self._combo_value(self.path_panel.path_type)
        if path_type == "custom":
            QMessageBox.information(
                self,
                "自定义函数",
                "自定义函数是本版本预留的实验性 PathProvider 扩展接口。",
            )
            return
        geometry = PathGeometry(
            path_type=path_type,
            name=self._allocate_marker_name("S", [item.name for item in self.paths]),
        )
        geometry.display_color = SLIT_COLORS[len(self.paths) % len(SLIT_COLORS)]
        geometry.label_color = geometry.display_color
        self._apply_path_panel_settings(geometry, include_name=False)
        self.paths.append(geometry)
        self.active_path_id = geometry.id
        self.path_panel.paths.blockSignals(True)
        self.path_panel.paths.addItem(self._marker_item(geometry.name, geometry.visible, geometry.id))
        self.path_panel.paths.setCurrentRow(len(self.paths) - 1)
        self.path_panel.paths.blockSignals(False)
        self._load_path_settings(geometry)
        self.path_editor.begin_geometry(geometry)
        # A native menu/list selection can deliver a queued current-row event
        # after the QAction returns. Reassert drawing once the event queue is
        # drained so a stale selection can never cancel a freshly created Slit.
        QTimer.singleShot(0, lambda marker_id=geometry.id: self._ensure_new_path_drawing(marker_id))

    def _ensure_new_path_drawing(self, marker_id: str) -> None:
        geometry = next((item for item in self.paths if item.id == marker_id), None)
        if geometry is None or geometry.id != self.active_path_id or geometry.control_count:
            return
        if not self.path_editor.drawing or self.path_editor.geometry is not geometry:
            self.path_editor.set_enabled(True)
            self.path_editor.begin_geometry(geometry)

    def _discard_unfinished_path(self) -> None:
        """Remove a half-drawn slit before another New Slit command starts."""
        geometry = self.path_editor.geometry if hasattr(self, "path_editor") else None
        if not self.path_editor.drawing or geometry is None:
            return
        if geometry.complete:
            self.path_editor.finish()
            return
        self.path_editor.cancel()
        row = self._path_row(geometry.id)
        if row >= 0:
            self.paths.pop(row)
            self.path_panel.paths.blockSignals(True)
            self.path_panel.paths.takeItem(row)
            self.path_panel.paths.blockSignals(False)
        self.active_path_id = None
        self.path_editor.set_geometry(None)
        self._refresh_overlays()

    def finish_active_drawing(self) -> None:
        """Route Enter to whichever scientific geometry is currently being drawn."""
        if self.region_editor.drawing:
            self.region_editor.finish()
        else:
            self.path_editor.finish()

    def cancel_active_drawing(self) -> None:
        if self.region_editor.drawing:
            self.region_editor.cancel()
        else:
            self.path_editor.cancel()

    def new_region(self, selected_type: str | None = None) -> None:
        """Begin interactive selection of a closed scientific region."""
        if self.dataset is None:
            self.statusBar().showMessage("请先加载图像或序列，再绘制区域。")
            return
        self.main_tabs.setCurrentIndex(0)
        self.left_tabs.setCurrentIndex(3)
        self.region_editor.set_enabled(True)
        self._discard_unfinished_region()
        self._deactivate_image_navigation()
        self.path_editor.set_geometry(None)
        region_type = selected_type or self._combo_value(self.region_panel.region_type)
        geometry = RegionGeometry(
            region_type,
            name=self._allocate_marker_name("R", [item.name for item in self.regions]),
        )
        geometry.display_color = REGION_COLORS[len(self.regions) % len(REGION_COLORS)]
        geometry.label_color = geometry.display_color
        geometry.coordinate_mode = self._combo_value(self.region_panel.coordinate_mode)
        self.regions.append(geometry); self.active_region_id = geometry.id
        self.region_panel.regions.addItem(self._marker_item(geometry.name, geometry.visible, geometry.id))
        self.region_panel.regions.setCurrentRow(len(self.regions) - 1)
        self.image_canvas.set_regions(self.regions, geometry.id)
        self.region_editor.begin_geometry(geometry)

    def _discard_unfinished_region(self) -> None:
        """Remove a half-drawn region before a new shape is selected."""
        geometry = self.region_editor.geometry if hasattr(self, "region_editor") else None
        if not self.region_editor.drawing or geometry is None:
            return
        if geometry.complete:
            self.region_editor.finish()
            return
        self.region_editor.cancel()
        row = self._region_row(geometry.id)
        if row >= 0:
            self.regions.pop(row)
            self.region_panel.regions.takeItem(row)
        self.active_region_id = None

    def manual_region(self) -> None:
        """Create a reproducible circle/rectangle from numeric pixel geometry."""
        if self.dataset is None:
            self.statusBar().showMessage("请先加载图像。")
            return
        name = self._allocate_marker_name("R", [item.name for item in self.regions])
        dialog = ManualRegionDialog(
            name,
            lambda preview: self.image_canvas.set_regions(self.regions + [preview], preview.id),
            self,
        )
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        self.image_canvas.set_regions(self.regions, self.active_region_id)
        if not accepted:
            return
        try:
            geometry = dialog.geometry()
            geometry.display_color = REGION_COLORS[len(self.regions) % len(REGION_COLORS)]
            geometry.label_color = geometry.display_color
            geometry.coordinate_mode = self._combo_value(self.region_panel.coordinate_mode)
            self.regions.append(geometry); self.active_region_id = geometry.id
            self.region_panel.regions.addItem(self._marker_item(geometry.name, geometry.visible, geometry.id))
            self.region_panel.regions.setCurrentRow(len(self.regions) - 1)
            self._region_finished(geometry)
        except Exception as exc:
            show_error(self, "手动区域参数无效", str(exc))

    def active_region(self) -> RegionGeometry | None:
        return next((item for item in self.regions if item.id == self.active_region_id), None)

    def _active_region_changed(self, row: int) -> None:
        item = self.region_panel.regions.item(row)
        marker_id = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        geometry = next((entry for entry in self.regions if entry.id == marker_id), None)
        if geometry is None and marker_id is None and 0 <= row < len(self.regions):
            geometry = self.regions[row]
        if geometry is None:
            self.active_region_id = None; self.region_editor.set_geometry(None)
        else:
            self.active_region_id = geometry.id
            self.path_editor.set_enabled(False)
            self.region_editor.set_enabled(self.left_tabs.currentIndex() == 3)
            self.region_editor.set_geometry(geometry if self.region_editor.enabled else None)
            self._load_region_settings(geometry)
        self._refresh_overlays()

    def _load_region_settings(self, geometry: RegionGeometry) -> None:
        widgets = (
            self.region_panel.name, self.region_panel.display_width,
            self.region_panel.show_label, self.region_panel.label_size,
            self.region_panel.label_background_transparent,
        )
        for widget in widgets:
            widget.blockSignals(True)
        self.region_panel.name.setText(geometry.name)
        self.region_panel.display_width.setValue(geometry.display_linewidth)
        self.region_panel.show_label.setChecked(geometry.show_label)
        self._set_color_button(self.region_panel.color, geometry.display_color)
        self._set_color_button(self.region_panel.label_color, geometry.label_color)
        self._set_color_button(
            self.region_panel.label_background, geometry.label_background_color, background=True
        )
        self.region_panel.label_background_transparent.setChecked(
            geometry.label_background_color.lower() == "transparent"
        )
        self.region_panel.label_size.setValue(geometry.label_fontsize)
        for widget in widgets:
            widget.blockSignals(False)

    def _region_settings_changed(self) -> None:
        geometry = self.active_region()
        if geometry is None:
            return
        new_name = self.region_panel.name.text().strip()
        if new_name:
            geometry.name = new_name
            row = self._region_row(geometry.id)
            item = self.region_panel.regions.item(row)
            if row >= 0 and item is not None and item.text() != new_name:
                item.setText(new_name)
        geometry.display_linewidth = self.region_panel.display_width.value()
        geometry.show_label = self.region_panel.show_label.isChecked()
        geometry.label_fontsize = self.region_panel.label_size.value()
        geometry.label_background_color = (
            "transparent"
            if self.region_panel.label_background_transparent.isChecked()
            else self.region_panel.label_background.text()
        )
        self._refresh_overlays()

    def _region_changed(self, geometry: RegionGeometry) -> None:
        self._refresh_overlays()

    def _region_finished(self, geometry: RegionGeometry) -> None:
        if self.dataset is not None and geometry.coordinate_mode == "world":
            try:
                wcs = self.dataset.get_wcs(self.reference_frame)
                if wcs is None:
                    raise ValueError("参考帧没有可靠 WCS")
                geometry.capture_world_outline(wcs)
            except Exception as exc:
                geometry.coordinate_mode = "pixel"
                self._set_combo_value(self.region_panel.coordinate_mode, "pixel")
                self.statusBar().showMessage(f"世界坐标区域不可用，已保留像素区域：{exc}")
        self._refresh_overlays()
        self.statusBar().showMessage(f"{geometry.name}: {geometry.description()}")
        if geometry.id not in self._history_marker_ids and geometry.complete:
            self._history_marker_ids.add(geometry.id)
            self._record_history(
                f"Region {geometry.name} ({geometry.region_type})",
                main_tab=0,
                left_tab=3,
                marker_kind="region",
                marker_id=geometry.id,
            )

    def delete_active_region(self) -> None:
        active = self.active_region()
        if active is None:
            row = self.region_panel.regions.currentRow()
            item = self.region_panel.regions.item(row)
            marker_id = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
            active = next((entry for entry in self.regions if entry.id == marker_id), None)
        if active is None:
            return
        row = self._region_row(active.id)
        if row < 0:
            self.statusBar().showMessage("区域列表状态异常；请重新选择区域。")
            return
        self.region_editor.set_geometry(None)
        self.region_panel.regions.blockSignals(True)
        self.regions.pop(row); self.region_panel.regions.takeItem(row)
        next_row = min(row, len(self.regions) - 1)
        self.region_panel.regions.setCurrentRow(next_row)
        self.region_panel.regions.blockSignals(False)
        if self.regions:
            selected = self.regions[next_row]
            self.active_region_id = selected.id
            self.region_editor.set_enabled(self.left_tabs.currentIndex() == 3)
            self.region_editor.set_geometry(selected if self.region_editor.enabled else None)
            self._load_region_settings(selected)
        else:
            self.active_region_id = None; self.region_editor.set_geometry(None)
        self._refresh_overlays()

    def calculate_region_trends(self) -> None:
        """Compute all region curves in a worker thread and overlay them."""
        if self.dataset is None:
            return
        completed = [item for item in self.regions if item.complete and item.visible]
        if not completed:
            self.statusBar().showMessage("请至少勾选一个已完成的闭合区域。")
            return
        self._region_worker = RegionTrendWorker(
            self.dataset, completed, self._combo_value(self.region_panel.statistic)
        )
        self._region_progress = QProgressDialog(
            "正在计算闭合区域的时间变化…", "取消", 0, self.dataset.n_frames, self
        )
        self._region_progress.setWindowModality(Qt.WindowModal)
        self._region_progress.canceled.connect(self._region_worker.request_cancel)
        self._region_worker.progress.connect(self._region_progress.setValue)
        self._region_worker.completed.connect(self._region_trends_finished)
        self._region_worker.failed.connect(self._region_failed)
        self._region_worker.cancelled.connect(lambda: self.statusBar().showMessage("区域分析已取消。"))
        self._region_worker.finished.connect(self._cleanup_region_worker)
        self._region_worker.start(); self._region_progress.show()

    def _region_trends_finished(self, result: RegionTrendResult) -> None:
        self._region_hist_timer.stop()
        self._region_hist_sequence = None
        self.region_histogram_player.setVisible(False)
        self._full_region_result = result
        self._apply_region_result_visibility()
        self.main_tabs.setCurrentIndex(2)
        self.statusBar().showMessage(
            f"已计算 {len(result.region_names)} 个区域的{result.statistic}时间变化。"
        )
        self._record_history(
            f"Region trend: {', '.join(result.region_names)}", main_tab=2, left_tab=3,
            region_result=result,
        )

    def calculate_region_histograms(self) -> None:
        if self.dataset is None:
            return
        try:
            frame = self.dataset.get_frame(self.current_frame)
            result = region_histograms(
                frame, self.regions, self.dataset.get_wcs(self.current_frame),
                self.current_frame, self.region_panel.bin_width.value(),
                time=self.dataset.get_time(self.current_frame),
            )
            if not result.region_names:
                raise ValueError("请至少勾选一个已完成的闭合区域。")
            self._region_hist_timer.stop()
            self._region_hist_sequence = None
            self.region_histogram_player.setVisible(False)
            self._full_region_result = result
            self._apply_region_result_visibility()
            self.main_tabs.setCurrentIndex(2)
            self._record_history(
                f"Region histogram: {', '.join(result.region_names)}",
                main_tab=2,
                left_tab=3,
                region_result=result,
            )
        except Exception as exc:
            show_error(self, "无法计算区域直方图", str(exc))

    def use_td_visible_time_range(self) -> None:
        """Copy the currently zoomed TD x-range into Region frame controls."""
        if self.dataset is None or self.td_result is None:
            self.statusBar().showMessage("请先生成时距图，再缩放到所需时间范围。", 7000)
            return
        left, right = sorted(self.td_canvas.axes.get_xlim())
        if self.td_canvas._true_time and self.dataset.times is not None:
            centers = np.asarray(mdates.date2num(self.dataset.times.utc.to_datetime()), dtype=float)
        else:
            centers = np.arange(self.dataset.n_frames, dtype=float)
        inside = np.flatnonzero((centers >= left) & (centers <= right))
        if inside.size:
            start, end = int(inside[0]), int(inside[-1])
        else:
            start = int(np.argmin(np.abs(centers - left)))
            end = int(np.argmin(np.abs(centers - right)))
            start, end = sorted((start, end))
        self.region_panel.histogram_start.setValue(start + 1)
        self.region_panel.histogram_end.setValue(end + 1)
        self.statusBar().showMessage(
            f"已采用 TD 当前可见范围：Frame {start + 1}–{end + 1}。", 7000
        )

    def calculate_region_histogram_sequence(self) -> None:
        """Calculate an inclusive histogram frame range without blocking the GUI."""
        if self.dataset is None:
            return
        completed = [item for item in self.regions if item.complete and item.visible]
        if not completed:
            self.statusBar().showMessage("请至少勾选一个已完成的闭合区域。")
            return
        start = self.region_panel.histogram_start.value() - 1
        end = self.region_panel.histogram_end.value() - 1
        step = self.region_panel.histogram_step.value()
        total = len(range(min(start, end), max(start, end) + 1, max(1, step)))
        self._region_worker = RegionHistogramSequenceWorker(
            self.dataset, completed, start, end, step, self.region_panel.bin_width.value()
        )
        self._region_progress = QProgressDialog(
            "正在计算区域直方图序列…", "取消", 0, max(1, total), self
        )
        self._region_progress.setWindowModality(Qt.WindowModal)
        self._region_progress.canceled.connect(self._region_worker.request_cancel)
        self._region_worker.progress.connect(self._region_progress.setValue)
        self._region_worker.completed.connect(self._region_histogram_sequence_finished)
        self._region_worker.failed.connect(self._region_failed)
        self._region_worker.cancelled.connect(
            lambda: self.statusBar().showMessage("区域直方图序列计算已取消。")
        )
        self._region_worker.finished.connect(self._cleanup_region_worker)
        self._region_worker.start(); self._region_progress.show()

    def _region_histogram_sequence_finished(self, result: RegionHistogramSequence) -> None:
        self._install_region_histogram_sequence(result, 0, record=True)

    def _install_region_histogram_sequence(
        self, result: RegionHistogramSequence, position: int = 0, *, record: bool
    ) -> None:
        """Install a sequence into the shared Region canvas and playback strip."""
        self._region_hist_timer.stop()
        self.region_hist_play.setText("▶ 播放")
        self._region_hist_sequence = result
        self.region_hist_slider.blockSignals(True)
        self.region_hist_slider.setRange(0, max(0, result.n_frames - 1))
        self.region_hist_slider.setValue(max(0, min(position, result.n_frames - 1)))
        self.region_hist_slider.blockSignals(False)
        self.region_histogram_player.setVisible(True)
        self.show_region_histogram_frame(self.region_hist_slider.value())
        self.main_tabs.setCurrentIndex(2)
        if record:
            names = ", ".join(result.results[0].region_names) if result.results else ""
            self._record_history(
                f"Region histogram sequence: {names} (Frames {result.start_frame + 1}–{result.end_frame + 1})",
                main_tab=2, left_tab=3, histogram_sequence=result, histogram_position=0,
            )
        self.statusBar().showMessage(
            f"已生成 {result.n_frames} 帧区域直方图序列。", 7000
        )

    def show_region_histogram_frame(self, position: int) -> None:
        sequence = self._region_hist_sequence
        if sequence is None or not sequence.results:
            return
        position = max(0, min(int(position), sequence.n_frames - 1))
        self._region_hist_position = position
        self.region_hist_slider.blockSignals(True)
        self.region_hist_slider.setValue(position)
        self.region_hist_slider.blockSignals(False)
        result = sequence.results[position]
        self._full_region_result = result
        self._apply_region_result_visibility()
        observation = result.time.utc.isot if result.time is not None else "no time metadata"
        self.region_hist_frame_label.setText(
            f"Frame {result.frame_index + 1} / {self.dataset.n_frames if self.dataset else '?'} · {observation}"
        )

    def _move_region_histogram(self, offset: int) -> None:
        sequence = self._region_hist_sequence
        if sequence is None or not sequence.results:
            return
        self.show_region_histogram_frame((self._region_hist_position + offset) % sequence.n_frames)

    def toggle_region_histogram_animation(self) -> None:
        if self._region_hist_sequence is None:
            return
        if self._region_hist_timer.isActive():
            self._region_hist_timer.stop(); self.region_hist_play.setText("▶ 播放")
        else:
            self._region_histogram_fps_changed()
            self._region_hist_timer.start(); self.region_hist_play.setText("⏸ 暂停")

    def _region_histogram_fps_changed(self, *_args: object) -> None:
        interval = max(1, round(1000.0 / self.region_panel.histogram_fps.value()))
        self._region_hist_timer.setInterval(interval)

    def _advance_region_histogram(self) -> None:
        self._move_region_histogram(1)

    def export_region_histogram_movie(self) -> None:
        sequence = self._region_hist_sequence
        if sequence is None:
            self.statusBar().showMessage("请先生成帧范围直方图序列。")
            return
        dialog = HistogramAnimationExportDialog(self.region_panel.histogram_fps.value(), self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "导出区域直方图动画", "region_histograms.mp4", "MP4 (*.mp4);;GIF (*.gif)"
        )
        if not path:
            return
        settings = dialog.settings()
        progress = QProgressDialog(
            "正在渲染区域直方图动画…", "", 0, sequence.n_frames + 1, self
        )
        progress.setCancelButton(None); progress.setWindowModality(Qt.WindowModal); progress.show()
        try:
            export_region_histogram_animation(
                sequence, path, float(settings["fps"]), settings["size"],
                plot_type=self._combo_value(self.region_panel.histogram_plot_type),
                y_unit=self._combo_value(self.region_panel.histogram_y_unit),
                line_width=self.region_line_width.value(),
                line_style=self._combo_value(self.region_line_style),
                title_size=self.region_title_size.value(),
                axis_label_size=self.region_axis_label_size.value(),
                tick_label_size=self.region_tick_size.value(),
                legend_fontsize=self.region_legend_size.value(),
                grid=self.region_grid.isChecked(),
                progress=lambda current, total: (
                    progress.setMaximum(total), progress.setValue(current), QApplication.processEvents()
                ),
            )
            self.statusBar().showMessage(f"区域直方图动画已保存：{path}", 9000)
        except Exception as exc:
            LOG.exception("Region histogram movie export failed")
            show_error(self, "无法导出区域直方图动画", str(exc))
        finally:
            progress.close()

    def _region_failed(self, message: str, trace: str) -> None:
        LOG.error("Region worker failed: %s\n%s", message, trace)
        show_error(self, "闭合区域分析失败", message, trace)

    def _cleanup_region_worker(self) -> None:
        if self._region_progress is not None:
            self._region_progress.close(); self._region_progress = None
        if self._region_worker is not None:
            self._region_worker.deleteLater(); self._region_worker = None

    def _redraw_region(self) -> None:
        """Re-render the current region result from the editable publication style."""
        if self.region_result is None:
            return
        formats = {
            "HH:MM:SS": "%H:%M:%S",
            "HH:MM": "%H:%M",
            "YYYY-MM-DD HH:MM:SS": "%Y-%m-%d %H:%M:%S",
        }
        common = {
            "title": self.region_plot_title.text(),
            "x_label": self.region_x_label.text(),
            "y_label": self.region_y_label.text(),
            "line_style": self._combo_value(self.region_line_style),
            "line_width": self.region_line_width.value(),
            "marker": self._combo_value(self.region_marker),
            "grid": self.region_grid.isChecked(),
            "y_scale": self._combo_value(self.region_y_scale),
            "axis_label_size": self.region_axis_label_size.value(),
            "tick_label_size": self.region_tick_size.value(),
            "title_size": self.region_title_size.value(),
            "legend_fontsize": self.region_legend_size.value(),
        }
        if isinstance(self.region_result, RegionTrendResult):
            self.region_canvas.show_trends(
                self.region_result,
                time_format=formats[self._combo_value(self.region_time_format)],
                plot_type=self._combo_value(self.region_panel.trend_plot_type),
                **common,
            )
        else:
            x_limits = None
            y_limits = None
            if self._region_hist_sequence is not None:
                visible_ids = {item.id for item in self.regions if item.visible}
                edges: list[np.ndarray] = []
                maximum = 0.0
                frequency = self._combo_value(self.region_panel.histogram_y_unit) == "frequency"
                for frame_result in self._region_hist_sequence.results:
                    for index, region_id in enumerate(frame_result.region_ids):
                        if region_id not in visible_ids:
                            continue
                        edges.append(frame_result.edges[index])
                        counts = np.asarray(frame_result.counts[index], dtype=float)
                        if frequency and counts.sum() > 0:
                            counts = counts / counts.sum()
                        if counts.size:
                            maximum = max(maximum, float(np.nanmax(counts)))
                if edges:
                    x_limits = (
                        min(float(np.nanmin(item)) for item in edges),
                        max(float(np.nanmax(item)) for item in edges),
                    )
                    if self._combo_value(self.region_y_scale) == "linear":
                        y_limits = (0.0, maximum * 1.08 if maximum > 0 else 1.0)
            self.region_canvas.show_histograms(
                self.region_result,
                x_scale=self._combo_value(self.region_x_scale),
                plot_type=self._combo_value(self.region_panel.histogram_plot_type),
                y_unit=self._combo_value(self.region_panel.histogram_y_unit),
                x_limits=x_limits,
                y_limits=y_limits,
                **common,
            )

    def export_region_data(self) -> None:
        if self.region_result is None:
            self.statusBar().showMessage("请先计算区域时间变化或直方图。")
            return
        names = "_".join(
            re.sub(r"[^A-Za-z0-9_-]+", "_", name).strip("_") or f"R{index + 1}"
            for index, name in enumerate(self.region_result.region_names)
        )
        kind = "trend" if isinstance(self.region_result, RegionTrendResult) else "histogram"
        path, _ = QFileDialog.getSaveFileName(
            self, "导出区域数据", f"{names}_{kind}.fits",
            "FITS (*.fits);;CSV (*.csv);;文本 (*.txt);;IDL SAV (*.sav)",
        )
        if not path:
            return
        try:
            export_region_result(self.region_result, path)
            self.statusBar().showMessage(f"区域数据已保存：{path}")
        except Exception as exc:
            show_error(self, "无法导出区域数据", str(exc))

    def active_path(self) -> PathGeometry | None:
        """Return active multiple-path entry by persistent ID."""
        return next((item for item in self.paths if item.id == self.active_path_id), None)

    def _active_path_changed(self, row: int) -> None:
        self.region_editor.set_enabled(False)
        item = self.path_panel.paths.item(row)
        marker_id = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        geometry = next((entry for entry in self.paths if entry.id == marker_id), None)
        if geometry is None and marker_id is None and 0 <= row < len(self.paths):
            geometry = self.paths[row]
        if geometry is None:
            self.active_path_id = None
            self.path_editor.set_geometry(None)
            self._refresh_overlays()
            return
        self.active_path_id = geometry.id
        self.path_editor.set_enabled(self.left_tabs.currentIndex() == 2)
        self.path_editor.set_geometry(geometry if self.path_editor.enabled else None)
        self._load_path_settings(geometry)

    def _load_path_settings(self, geometry: PathGeometry) -> None:
        """Reflect selected path values in controls without feeding changes back."""
        widgets = (
            self.path_panel.width,
            self.path_panel.width_unit,
            self.path_panel.show_width,
            self.path_panel.integration,
            self.path_panel.interpolation,
            self.path_panel.coordinate_mode,
            self.path_panel.tracking,
            self.path_panel.step,
            self.path_panel.distance_unit,
            self.path_panel.normalize_exposure,
            self.path_panel.smoothing,
            self.path_panel.name,
            self.path_panel.display_width,
            self.path_panel.show_label,
            self.path_panel.label_size,
            self.path_panel.label_background_transparent,
        )
        for widget in widgets:
            widget.blockSignals(True)
        self.path_panel.width.setValue(geometry.width)
        self.path_panel.width_unit.setCurrentText(geometry.width_unit)
        self.path_panel.show_width.setChecked(geometry.show_width_boundaries)
        self._set_combo_value(self.path_panel.integration, geometry.integration_method)
        self._set_combo_value(self.path_panel.interpolation, geometry.interpolation)
        self._set_combo_value(self.path_panel.coordinate_mode, geometry.coordinate_mode)
        self._set_combo_value(self.path_panel.tracking, geometry.tracking_mode)
        self.path_panel.step.setValue(geometry.sample_step_pixel)
        self.path_panel.distance_unit.setCurrentText(
            getattr(geometry, "distance_unit", geometry.width_unit)
        )
        self.path_panel.normalize_exposure.setChecked(geometry.normalize_exposure)
        self.path_panel.smoothing.setValue(geometry.smoothing)
        self.path_panel.name.setText(geometry.name)
        self._set_color_button(self.path_panel.color, geometry.display_color)
        self.path_panel.display_width.setValue(geometry.display_linewidth)
        self.path_panel.show_label.setChecked(geometry.show_label)
        self._set_color_button(self.path_panel.label_color, geometry.label_color)
        self._set_color_button(
            self.path_panel.label_background, geometry.label_background_color, background=True
        )
        self.path_panel.label_background_transparent.setChecked(
            geometry.label_background_color.lower() == "transparent"
        )
        self.path_panel.label_size.setValue(geometry.label_fontsize)
        for widget in widgets:
            widget.blockSignals(False)

    def _apply_path_panel_settings(
        self, geometry: PathGeometry, *, include_name: bool = True
    ) -> None:
        """Copy controls into one Slit without leaking a prior Slit's identity."""
        geometry.width = self.path_panel.width.value()
        geometry.width_unit = self.path_panel.width_unit.currentText()
        geometry.show_width_boundaries = self.path_panel.show_width.isChecked()
        geometry.distance_unit = self.path_panel.distance_unit.currentText()
        geometry.normalize_exposure = self.path_panel.normalize_exposure.isChecked()
        geometry.integration_method = self._combo_value(self.path_panel.integration)
        geometry.interpolation = self._combo_value(self.path_panel.interpolation)
        geometry.coordinate_mode = self._combo_value(self.path_panel.coordinate_mode)
        geometry.tracking_mode = self._combo_value(self.path_panel.tracking)
        geometry.sample_step_pixel = self.path_panel.step.value()
        geometry.smoothing = self.path_panel.smoothing.value()
        new_name = self.path_panel.name.text().strip() if include_name else ""
        if include_name and new_name:
            geometry.name = new_name
            row = self._path_row(geometry.id)
            item = self.path_panel.paths.item(row)
            if row >= 0 and item is not None and item.text() != new_name:
                item.setText(new_name)
        geometry.display_linewidth = self.path_panel.display_width.value()
        geometry.show_label = self.path_panel.show_label.isChecked()
        geometry.label_fontsize = self.path_panel.label_size.value()
        geometry.label_background_color = (
            "transparent"
            if self.path_panel.label_background_transparent.isChecked()
            else self.path_panel.label_background.text()
        )
        if geometry.coordinate_mode == "pixel" and geometry.tracking_mode == "world_fixed":
            geometry.tracking_mode = "pixel_fixed"
            self._set_combo_value(self.path_panel.tracking, "pixel_fixed")

    def _path_settings_changed(self) -> None:
        geometry = self.active_path()
        if geometry is None:
            return
        self._apply_path_panel_settings(geometry)
        self._refresh_overlays()

    def _path_changed(self, geometry: PathGeometry) -> None:
        self._refresh_overlays()

    def _path_finished(self, geometry: PathGeometry) -> None:
        """Capture world samples at reference WCS only after geometry is complete."""
        if self.dataset is not None and geometry.coordinate_mode == "world":
            try:
                samples, _ = sample_path_geometry(geometry)
                geometry.capture_world_samples(self.dataset.get_wcs(self.reference_frame), samples)  # type: ignore[arg-type]
            except Exception as exc:
                geometry.coordinate_mode = "pixel"
                geometry.tracking_mode = "pixel_fixed"
                self._set_combo_value(self.path_panel.coordinate_mode, "pixel")
                self._set_combo_value(self.path_panel.tracking, "pixel_fixed")
                self.statusBar().showMessage(f"世界坐标切片不可用，已保留像素切片：{exc}")
        self._refresh_overlays()
        if geometry.id not in self._history_marker_ids and geometry.complete:
            self._history_marker_ids.add(geometry.id)
            self._record_history(
                f"Slit {geometry.name} ({geometry.path_type})",
                main_tab=0,
                left_tab=2,
                marker_kind="slit",
                marker_id=geometry.id,
            )

    def delete_active_path(self) -> None:
        """Remove the selected path only; no source data are ever deleted."""
        active = self.active_path()
        if active is None:
            row = self.path_panel.paths.currentRow()
            item = self.path_panel.paths.item(row)
            marker_id = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
            active = next((entry for entry in self.paths if entry.id == marker_id), None)
        if active is None:
            self.statusBar().showMessage("请先在 Slit 列表中选择要删除的切片。")
            return
        row = self._path_row(active.id)
        if row < 0:
            self.statusBar().showMessage("Slit 列表状态异常；请重新选择切片。")
            return
        self.path_editor.set_geometry(None)
        self.path_panel.paths.blockSignals(True)
        self.paths.pop(row)
        self.path_panel.paths.takeItem(row)
        next_row = min(row, len(self.paths) - 1)
        self.path_panel.paths.setCurrentRow(next_row)
        self.path_panel.paths.blockSignals(False)
        if self.paths:
            selected = self.paths[next_row]
            self.active_path_id = selected.id
            self.path_editor.set_enabled(self.left_tabs.currentIndex() == 2)
            self.path_editor.set_geometry(selected if self.path_editor.enabled else None)
            self._load_path_settings(selected)
        else:
            self.active_path_id = None
            self.path_editor.set_geometry(None)
            self.path_panel.name.blockSignals(True)
            self.path_panel.name.clear()
            self.path_panel.name.blockSignals(False)
        self._refresh_overlays()
        self.statusBar().showMessage(f"已删除切片 {active.name}。")

    def generate_td(self) -> None:
        """Dispatch expensive TD computation to QThread and provide cancellation."""
        if self.dataset is None:
            self.statusBar().showMessage("请先加载数据。")
            return
        path = self.active_path()
        if path is None or not path.complete:
            self.statusBar().showMessage("请先选择并完成一个活动切片。")
            return
        if path.coordinate_mode == "world" and path.world_sample_values is None:
            self._path_finished(path)
        distance_unit = path.distance_unit
        config = TDConfig(
            distance_unit=distance_unit,
            tracking_mode=path.tracking_mode,
            normalize_exposure=path.normalize_exposure,
        )
        self._td_worker = TDWorker(self.dataset, path, config)
        self._td_progress = QProgressDialog("正在生成时距图…", "取消", 0, self.dataset.n_frames, self)
        self._td_progress.setWindowModality(Qt.WindowModal)
        self._td_progress.canceled.connect(self._td_worker.request_cancel)
        self._td_worker.progress.connect(self._td_progress.setValue)
        self._td_worker.completed.connect(self._td_finished)
        self._td_worker.failed.connect(self._td_failed)
        self._td_worker.cancelled.connect(self._td_cancelled)
        self._td_worker.finished.connect(self._cleanup_td_worker)
        self._td_worker.start()
        self._td_progress.show()

    def _td_finished(self, result: TDResult) -> None:
        self.td_result = result
        self._redraw_td()
        self.main_tabs.setCurrentIndex(1)
        self.statusBar().showMessage(f"时距图已完成：{result.shape[0]} 个距离采样 × {result.shape[1]} 个时刻。")
        slit = self.active_path()
        self._record_history(
            f"Time–Distance: {slit.name if slit is not None else 'Slit'}",
            main_tab=1,
            left_tab=2,
            marker_kind="slit" if slit is not None else None,
            marker_id=slit.id if slit is not None else None,
        )

    def _td_failed(self, message: str, trace: str) -> None:
        LOG.error("TD worker failed: %s\n%s", message, trace)
        show_error(
            self,
            "时距图生成失败",
            f"{message}\n\n请检查切片单位、WCS 和源数据。",
            trace,
        )

    def _td_cancelled(self) -> None:
        self.statusBar().showMessage("时距图生成已取消。")

    def _cleanup_td_worker(self) -> None:
        if self._td_progress is not None:
            self._td_progress.close()
            self._td_progress = None
        if self._td_worker is not None:
            self._td_worker.deleteLater()
            self._td_worker = None

    def _redraw_td(self) -> None:
        if self.td_result is None:
            return
        formats = {
            "HH:MM:SS": "%H:%M:%S",
            "HH:MM": "%H:%M",
            "YYYY-MM-DD HH:MM:SS": "%Y-%m-%d %H:%M:%S",
        }
        selected = self._combo_value(self.td_time_format)
        time_format = self.td_custom_format.text().strip() if selected == "Custom" else formats[selected]
        path_name = str(self.td_result.metadata.get("path", {}).get("name", ""))
        automatic_title = f"Time–Distance Diagram — {path_name}" if path_name else "Time–Distance Diagram"
        self.td_canvas.show_result(
            self.td_result,
            cmap=self.td_cmap.currentText(),
            normalization_mode=self._combo_value(self.td_norm),
            stretch=self._combo_value(self.td_stretch),
            true_time=self.true_time.isChecked(),
            title=self.td_title.text().strip() or automatic_title,
            time_format=time_format or "%H:%M:%S",
            axis_label_size=self.td_axis_label_size.value(),
            tick_label_size=self.td_tick_size.value(),
            include_start_time=self.td_include_start.isChecked(),
            x_label=self.td_x_label.text(),
            y_label=self.td_y_label.text(),
            grid=self.td_grid.isChecked(),
            show_colorbar=self.td_colorbar.isChecked(),
            aspect=self._combo_value(self.td_aspect),
            vmin=self.td_vmin.value(),
            vmax=self.td_vmax.value(),
            low_percent=self.td_percentile_low.value(),
            high_percent=self.td_percentile_high.value(),
        )

    def save_current_view(self) -> None:
        """Save whichever scientific canvas is visible in the right-hand tabs."""
        handlers = (self.save_current_frame, self.export_td_figure, self.export_region_figure)
        index = self.main_tabs.currentIndex()
        if 0 <= index < len(handlers):
            handlers[index]()

    def _view_export_settings(self) -> dict[str, object] | None:
        defaults = {
            "include_axes": self.settings.value("view_export/include_axes", True, type=bool),
            "include_title": self.settings.value("view_export/include_title", True, type=bool),
            "include_colorbar": self.settings.value("view_export/include_colorbar", True, type=bool),
            "transparent": self.settings.value("view_export/transparent", False, type=bool),
            "dpi": int(self.settings.value("view_export/dpi", 300)),
        }
        dialog = ViewExportDialog(defaults, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        values = dialog.settings()
        for key, value in values.items():
            self.settings.setValue(f"view_export/{key}", value)
        return values

    def _export_canvas_figure(self, canvas: Any, path: str, options: dict[str, object]) -> None:
        export_figure(
            canvas.figure,
            path,
            dpi=int(options["dpi"]),
            transparent=bool(options["transparent"]),
            main_axes=canvas.axes,
            include_axes=bool(options["include_axes"]),
            include_title=bool(options["include_title"]),
            include_colorbar=bool(options["include_colorbar"]),
        )

    def save_current_frame(self) -> None:
        """Export the Map canvas at publication quality, never a GUI screenshot."""
        if self.dataset is None:
            return
        options = self._view_export_settings()
        if options is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "保存 Map 图像",
            "frame.png",
            "PNG (*.png);;PDF (*.pdf);;EPS (*.eps);;SVG (*.svg);;TIFF (*.tiff *.tif);;JPEG (*.jpg *.jpeg)",
        )
        if not path:
            return
        try:
            self.image_canvas.set_full_resolution_display(True)
            self._export_canvas_figure(self.image_canvas, path, options)
            self.statusBar().showMessage(f"当前图像已保存：{path}")
        except Exception as exc:
            LOG.exception("Frame export failed")
            show_error(self, "无法保存 Map 图像", str(exc))
        finally:
            self.image_canvas.set_full_resolution_display(False)

    def export_animation(self) -> None:
        """Export complete current range with fixed/dynamic normalization policy."""
        if self.dataset is None:
            return
        dialog = AnimationExportDialog(
            self.dataset.shape,
            self.image_panel.speed.value(),
            self,
            viewport_size=(max(16, self.image_canvas.width()), max(16, self.image_canvas.height())),
            n_frames=self.dataset.n_frames,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        settings = dialog.settings()
        path, _ = QFileDialog.getSaveFileName(
            self, "导出动画", "animation.mp4", "MP4 (*.mp4);;GIF (*.gif);;AVI (*.avi)"
        )
        if not path:
            return
        start = int(settings["start"])
        end = int(settings["end"])
        step = int(settings["step"])
        frame_count = len(range(start, end + 1, max(1, step)))
        progress = QProgressDialog("正在导出动画…", "取消", 0, max(1, frame_count + 1), self)
        progress.setWindowModality(Qt.WindowModal)
        progress.show()
        try:
            export_animation(
                self.dataset,
                path,
                start,
                end,
                step,
                float(settings["fps"]),
                self.image_panel.cmap_name(),
                self._combo_value(self.image_panel.normalization),
                self.image_panel.fixed.isChecked(),
                progress=lambda current, total: (progress.setMaximum(total), progress.setValue(current)),
                output_size=settings["size"],
                codec=str(settings["codec"]),
                bitrate=str(settings["bitrate"]),
                low_percent=self.image_panel.percentile_low.value(),
                high_percent=self.image_panel.percentile_high.value(),
                stretch=self._combo_value(self.image_panel.stretch),
                vmin=self.image_panel.vmin.value(),
                vmax=self.image_panel.vmax.value(),
                viewport_limits=(
                    (tuple(float(value) for value in self.image_canvas.axes.get_xlim()),
                     tuple(float(value) for value in self.image_canvas.axes.get_ylim()))
                    if settings["view_range"] == "current" else None
                ),
                include_axes=bool(settings["include_axes"]),
                include_timestamp=bool(settings["include_timestamp"]),
                include_title=bool(settings["include_title"]),
                include_colorbar=bool(settings["include_colorbar"]),
                paths=self.paths if settings["include_slits"] else (),
                regions=self.regions if settings["include_regions"] else (),
            )
            self.statusBar().showMessage(f"动画已保存：{path}")
        except Exception as exc:
            LOG.exception("Animation export failed")
            show_error(self, "无法导出动画", str(exc))
        finally:
            progress.close()

    def export_td_figure(self) -> None:
        """Export TD plot via Matplotlib, preserving PDF/SVG vector output."""
        if self.td_result is None:
            return
        options = self._view_export_settings()
        if options is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "导出时距图", "time_distance.pdf", "PDF (*.pdf);;PNG (*.png);;EPS (*.eps);;SVG (*.svg);;TIFF (*.tiff *.tif)"
        )
        if not path:
            return
        try:
            self._export_canvas_figure(self.td_canvas, path, options)
            self.statusBar().showMessage(f"时距图已保存：{path}")
        except Exception as exc:
            LOG.exception("TD figure export failed")
            show_error(self, "无法导出时距图", str(exc))

    def export_region_figure(self) -> None:
        """Export the latest region trend/histogram using its editable style."""
        if self.region_result is None:
            self.statusBar().showMessage("请先绘制区域时间变化或直方图。")
            return
        options = self._view_export_settings()
        if options is None:
            return
        names = "_".join(
            re.sub(r"[^A-Za-z0-9_-]+", "_", name).strip("_") or f"R{index + 1}"
            for index, name in enumerate(self.region_result.region_names)
        )
        kind = "trend" if isinstance(self.region_result, RegionTrendResult) else "histogram"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "保存区域分析图",
            f"{names}_{kind}.pdf",
            "PDF (*.pdf);;PNG (*.png);;EPS (*.eps);;SVG (*.svg);;TIFF (*.tiff *.tif)",
        )
        if not path:
            return
        try:
            self._export_canvas_figure(self.region_canvas, path, options)
            self.statusBar().showMessage(f"区域分析图已保存：{path}")
        except Exception as exc:
            LOG.exception("Region figure export failed")
            show_error(self, "无法保存区域分析图", str(exc))

    def export_td_data(self) -> None:
        """Write TD array along with time/distance coordinates and a JSON sidecar."""
        if self.td_result is None:
            return
        path, selected_filter = QFileDialog.getSaveFileName(
            self, "导出时距数值数据", "time_distance.fits",
            "FITS (*.fits);;NPZ (*.npz);;CSV (*.csv);;文本 (*.txt)"
        )
        if not path:
            return
        try:
            suffix = Path(path).suffix.lower()
            if suffix == ".fits" or "FITS" in selected_filter:
                export_td_fits(self.td_result, path)
            elif suffix == ".csv" or "CSV" in selected_filter:
                export_td_csv(self.td_result, path)
            elif suffix == ".txt" or "文本" in selected_filter:
                export_td_txt(self.td_result, path)
            else:
                export_td_npz(self.td_result, path)
            self.statusBar().showMessage(f"时距数据已保存：{path}")
        except Exception as exc:
            LOG.exception("TD data export failed")
            show_error(self, "无法导出时距数据", str(exc))

    def save_project(self) -> None:
        """Save re-openable source references and reproducible path/display choices."""
        if self.dataset is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "保存项目", "analysis.stdproj", "STDE 项目 (*.stdproj)")
        if not path:
            return
        try:
            save_project(
                path,
                self.dataset,
                self.paths,
                self.active_path_id,
                self.reference_frame,
                self._image_settings(),
                self._td_settings(),
                self.regions,
            )
            self.statusBar().showMessage(f"项目已保存：{path}")
        except Exception as exc:
            LOG.exception("Project save failed")
            show_error(self, "无法保存项目", str(exc))

    def open_project(self) -> None:
        """Reopen source data, restore times/paths and leave missing paths user-locatable."""
        path, _ = QFileDialog.getOpenFileName(self, "打开项目", filter="STDE 项目 (*.stdproj)")
        if not path:
            return
        try:
            payload = load_project(path)
            try:
                dataset = open_from_descriptor(payload["dataset"])
            except FileNotFoundError:
                replacement, _ = QFileDialog.getOpenFileName(
                    self, "源数据已移动：请重新定位（或取消）", filter="FITS/SAV (*.fits *.fit *.fts *.sav)"
                )
                if not replacement:
                    raise
                descriptor = payload["dataset"].copy()
                descriptor["source"] = replacement
                dataset = open_from_descriptor(descriptor)
            restore_times(dataset, payload)
            self._install_dataset(dataset)
            self.paths = [PathGeometry.from_dict(item) for item in payload.get("paths", [])]
            self.regions = [RegionGeometry.from_dict(item) for item in payload.get("regions", [])]
            self.path_panel.paths.clear()
            for geometry in self.paths:
                self.path_panel.paths.addItem(self._marker_item(geometry.name, geometry.visible, geometry.id))
            self.region_panel.regions.clear()
            for geometry in self.regions:
                self.region_panel.regions.addItem(self._marker_item(geometry.name, geometry.visible, geometry.id))
            if self.regions:
                self.active_region_id = self.regions[0].id
                self.region_panel.regions.setCurrentRow(0)
            self._refresh_overlays()
            self.reference_frame = int(payload.get("reference_frame", 0))
            self.dataset_panel.reference.setValue(self.reference_frame)
            self.active_path_id = payload.get("active_path_id")
            found = next(
                (index for index, item in enumerate(self.paths) if item.id == self.active_path_id),
                0 if self.paths else -1,
            )
            if found >= 0:
                self.path_panel.paths.setCurrentRow(found)
            self._apply_image_settings(payload.get("display_settings", {}))
            self._apply_td_settings(payload.get("td_display_settings", {}))
            self.statusBar().showMessage(f"项目已恢复：{path}")
        except Exception as exc:
            LOG.exception("Project open failed")
            show_error(self, "无法打开项目", str(exc))

    def _image_settings(self) -> dict[str, Any]:
        return {
            "cmap": self.image_panel.cmap.currentText(),
            "reverse": self.image_panel.reverse.isChecked(),
            "normalization": self._combo_value(self.image_panel.normalization),
            "stretch": self._combo_value(self.image_panel.stretch),
            "vmin": self.image_panel.vmin.value(),
            "vmax": self.image_panel.vmax.value(),
            "percentile_low": self.image_panel.percentile_low.value(),
            "percentile_high": self.image_panel.percentile_high.value(),
            "fixed": self.image_panel.fixed.isChecked(),
            "preview_fps": self.image_panel.speed.value(),
        }

    def _td_settings(self) -> dict[str, Any]:
        return {
            "cmap": self.td_cmap.currentText(),
            "normalization": self._combo_value(self.td_norm),
            "stretch": self._combo_value(self.td_stretch),
            "true_time": self.true_time.isChecked(),
            "time_format": self._combo_value(self.td_time_format),
            "custom_time_format": self.td_custom_format.text(),
            "title": self.td_title.text(),
            "x_label": self.td_x_label.text(),
            "y_label": self.td_y_label.text(),
            "vmin": self.td_vmin.value(),
            "vmax": self.td_vmax.value(),
            "percentile_low": self.td_percentile_low.value(),
            "percentile_high": self.td_percentile_high.value(),
            "axis_label_size": self.td_axis_label_size.value(),
            "tick_label_size": self.td_tick_size.value(),
            "include_start_time": self.td_include_start.isChecked(),
            "grid": self.td_grid.isChecked(),
            "colorbar": self.td_colorbar.isChecked(),
            "aspect": self._combo_value(self.td_aspect),
            "slope_color": self.slope_color.text(),
            "slope_width": self.slope_width.value(),
            "slope_linestyle": self._combo_value(self.slope_linestyle),
            "slope_fontsize": self.slope_fontsize.value(),
            "slope_text_color": self.slope_text_color.text(),
            "slope_background": self.slope_background.text(),
            "slope_background_transparent": self.slope_background_transparent.isChecked(),
            "slope_velocity_unit": self._combo_value(self.slope_velocity_unit),
            "slope_auto_colors": self.slope_auto_colors.isChecked(),
            "slope_precision": self.slope_precision.value(),
            "region_plot": {
                "time_format": self._combo_value(self.region_time_format),
                "title": self.region_plot_title.text(),
                "x_label": self.region_x_label.text(),
                "y_label": self.region_y_label.text(),
                "line_style": self._combo_value(self.region_line_style),
                "line_width": self.region_line_width.value(),
                "marker": self._combo_value(self.region_marker),
                "x_scale": self._combo_value(self.region_x_scale),
                "y_scale": self._combo_value(self.region_y_scale),
                "grid": self.region_grid.isChecked(),
                "axis_label_size": self.region_axis_label_size.value(),
                "tick_label_size": self.region_tick_size.value(),
                "title_size": self.region_title_size.value(),
                "legend_fontsize": self.region_legend_size.value(),
                "sync_legend": self.region_sync_legend.isChecked(),
                "trend_plot_type": self._combo_value(self.region_panel.trend_plot_type),
                "histogram_plot_type": self._combo_value(self.region_panel.histogram_plot_type),
                "histogram_y_unit": self._combo_value(self.region_panel.histogram_y_unit),
            },
        }

    def _apply_image_settings(self, settings: dict[str, Any]) -> None:
        self.image_panel.cmap.setCurrentText(settings.get("cmap", "gray"))
        self.image_panel.reverse.setChecked(bool(settings.get("reverse", False)))
        self._set_combo_value(self.image_panel.normalization, settings.get("normalization", "percentile"))
        self._set_combo_value(self.image_panel.stretch, settings.get("stretch", "linear"))
        self.image_panel.vmin.setValue(float(settings.get("vmin", 0.0)))
        self.image_panel.vmax.setValue(float(settings.get("vmax", 1.0)))
        self.image_panel.percentile_low.setValue(float(settings.get("percentile_low", 1.0)))
        self.image_panel.percentile_high.setValue(float(settings.get("percentile_high", 99.0)))
        self.image_panel.fixed.setChecked(bool(settings.get("fixed", True)))
        self.image_panel.speed.setValue(float(settings.get("preview_fps", 5.0)))
        self.image_panel._range_mode_changed()
        self._reset_image_norm()

    def _apply_td_settings(self, settings: dict[str, Any]) -> None:
        self.td_cmap.setCurrentText(settings.get("cmap", "viridis"))
        self._set_combo_value(self.td_norm, settings.get("normalization", "percentile"))
        self._set_combo_value(self.td_stretch, settings.get("stretch", "linear"))
        self.true_time.setChecked(bool(settings.get("true_time", True)))
        self._set_combo_value(self.td_time_format, settings.get("time_format", "HH:MM:SS"))
        self.td_custom_format.setText(settings.get("custom_time_format", "%H:%M:%S"))
        self.td_title.setText(settings.get("title", ""))
        self.td_x_label.setText(settings.get("x_label", ""))
        self.td_y_label.setText(settings.get("y_label", ""))
        self.td_vmin.setValue(float(settings.get("vmin", 0.0)))
        self.td_vmax.setValue(float(settings.get("vmax", 1.0)))
        self.td_percentile_low.setValue(float(settings.get("percentile_low", 1.0)))
        self.td_percentile_high.setValue(float(settings.get("percentile_high", 99.0)))
        self.td_axis_label_size.setValue(float(settings.get("axis_label_size", 11.0)))
        self.td_tick_size.setValue(float(settings.get("tick_label_size", 9.0)))
        self.td_include_start.setChecked(bool(settings.get("include_start_time", False)))
        self.td_grid.setChecked(bool(settings.get("grid", False)))
        self.td_colorbar.setChecked(bool(settings.get("colorbar", True)))
        self._set_combo_value(self.td_aspect, settings.get("aspect", "auto"))
        slope_color = str(settings.get("slope_color", "#ffffff"))
        self.slope_color.setText(slope_color)
        self.slope_color.setStyleSheet(f"QPushButton {{ color: {slope_color}; }}")
        self.slope_width.setValue(float(settings.get("slope_width", 1.5)))
        self._set_combo_value(self.slope_linestyle, settings.get("slope_linestyle", "-"))
        self.slope_fontsize.setValue(float(settings.get("slope_fontsize", 10.0)))
        slope_text_color = str(settings.get("slope_text_color", slope_color))
        self._set_color_button(self.slope_text_color, slope_text_color)
        slope_background = str(settings.get("slope_background", "#000000"))
        self._set_color_button(self.slope_background, slope_background, background=True)
        self.slope_background_transparent.setChecked(
            bool(settings.get("slope_background_transparent", False))
        )
        self._set_combo_value(
            self.slope_velocity_unit, str(settings.get("slope_velocity_unit", "km"))
        )
        self.slope_auto_colors.setChecked(bool(settings.get("slope_auto_colors", True)))
        self.slope_precision.setValue(int(settings.get("slope_precision", 1)))
        region = settings.get("region_plot", {})
        self._set_combo_value(self.region_time_format, region.get("time_format", "HH:MM:SS"))
        self.region_plot_title.setText(region.get("title", ""))
        self.region_x_label.setText(region.get("x_label", ""))
        self.region_y_label.setText(region.get("y_label", ""))
        self._set_combo_value(self.region_line_style, region.get("line_style", "-"))
        self.region_line_width.setValue(float(region.get("line_width", 1.5)))
        self._set_combo_value(self.region_marker, region.get("marker", "."))
        self._set_combo_value(self.region_x_scale, region.get("x_scale", "linear"))
        self._set_combo_value(self.region_y_scale, region.get("y_scale", "linear"))
        self.region_grid.setChecked(bool(region.get("grid", True)))
        self.region_axis_label_size.setValue(float(region.get("axis_label_size", 11.0)))
        self.region_tick_size.setValue(float(region.get("tick_label_size", 9.0)))
        self.region_title_size.setValue(float(region.get("title_size", 12.0)))
        self.region_legend_size.setValue(float(region.get("legend_fontsize", self.region_title_size.value())))
        self.region_sync_legend.setChecked(bool(region.get("sync_legend", True)))
        self._set_combo_value(self.region_panel.trend_plot_type, region.get("trend_plot_type", "line"))
        self._set_combo_value(self.region_panel.histogram_plot_type, region.get("histogram_plot_type", "bar"))
        self._set_combo_value(self.region_panel.histogram_y_unit, region.get("histogram_y_unit", "count"))
        self._td_range_mode_changed()
        self._apply_slope_style()
        self._redraw_region()

    def show_metadata(self) -> None:
        """Show current header values in a searchable-enough monospaced dialog."""
        if self.dataset is None:
            return
        from PySide6.QtWidgets import QDialog, QPlainTextEdit, QVBoxLayout

        dialog = QDialog(self)
        dialog.setWindowTitle("当前元数据")
        dialog.resize(720, 600)
        layout = QVBoxLayout(dialog)
        text = QPlainTextEdit()
        text.setReadOnly(True)
        items = self.dataset.get_header(self.current_frame).items()
        text.setPlainText("\n".join(f"{key:>10} = {value}" for key, value in sorted(items)))
        layout.addWidget(text)
        dialog.exec()

    def _cursor_changed(self, details: dict[str, Any]) -> None:
        world = details["world"]
        unit = details.get("world_unit") or ""
        world_text = f"；世界坐标=({world[0]:.6g}, {world[1]:.6g}) {unit}" if world else ""
        value = details["value"]
        value_text = "NaN/图外" if value is None else f"{value:.6g}"
        self.statusBar().showMessage(
            f"像素：x={details['x']:.2f}, y={details['y']:.2f}；数值={value_text}{world_text}"
        )

    def show_about(self) -> None:
        """Show software and scientific runtime versions."""
        import astropy
        import aiapy
        import matplotlib
        import numpy
        import scipy
        import sunpy

        QMessageBox.about(
            self,
            "关于 Solar Time–Distance Explorer",
            f"Solar Time–Distance Explorer {__version__}\n\n"
            "FITS/SAV 时序、有限宽度曲线切片、真实观测时间时距图。\n\n"
            "作者：Zhentong Li\n"
            "Email: eternitylzt@gmail.com\n"
            "GitHub: https://github.com/eternitylzt\n\n"
            f"Python 运行时；SunPy {sunpy.__version__}；aiapy {aiapy.__version__}；Astropy {astropy.__version__}；"
            f"NumPy {numpy.__version__}; SciPy {scipy.__version__}; Matplotlib {matplotlib.__version__}.",
        )

    def open_log_folder(self) -> None:
        """Open logged diagnostics in Windows Explorer."""
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl

        QDesktopServices.openUrl(QUrl.fromLocalFile(str(log_directory())))
