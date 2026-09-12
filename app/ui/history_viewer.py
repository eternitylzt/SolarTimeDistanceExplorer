"""Isolated history viewing: never install old products into live editor state."""

from __future__ import annotations

from io import BytesIO
from typing import Any, Callable

import matplotlib.image as mpimg
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QSlider, QVBoxLayout

from app.i18n import tr
from app.processing.region_analysis import RegionTrendResult
from app.ui.region_plot import RegionAnalysisCanvas
from app.ui.td_plot import TimeDistanceCanvas


class HistoryViewer(QDialog):
    """View saved results with separate axes, navigation and sequence playback.

    Result arrays are shared read-only with bounded session history. Marker lists,
    active drawing, frame position and the live analysis canvases are untouched.
    """

    def __init__(self, entry: dict[str, Any], notice: str, parent: Any,
                 use_markers: Callable[[], None] | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("绘图历史 — ", "Plot History — ") + entry["description"])
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.resize(1050, 780)
        self.entry = entry
        self.result = entry.get("td_result") or entry.get("region_result")
        self.sequence = entry.get("histogram_sequence")
        self.position = 0
        self.timer = QTimer(self)
        self.timer.setInterval(200)
        self.timer.timeout.connect(self._advance)
        layout = QVBoxLayout(self)
        self.notice = QLabel(notice)
        self.notice.setWordWrap(True)
        self.notice.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.notice)
        if entry.get("td_result") is not None:
            self.canvas = TimeDistanceCanvas()
            self.canvas.show_result(self.result, **entry.get("plot_options", {}))
        elif self.sequence is not None or self.result is not None:
            self.canvas = RegionAnalysisCanvas()
            if self.sequence is None:
                self._render_region(self.result)
        else:
            figure = Figure(layout="constrained")
            self.canvas = FigureCanvasQTAgg(figure)
            axes = figure.add_subplot(111)
            axes.set_axis_off()
            preview = entry.get("map_preview")
            if preview:
                axes.imshow(mpimg.imread(BytesIO(preview), format="png"))
            else:
                axes.text(.5, .5, "No saved plot", ha="center", transform=axes.transAxes)
        layout.addWidget(NavigationToolbar2QT(self.canvas, self))
        layout.addWidget(self.canvas, 1)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.frame_label = QLabel()
        self.play = QPushButton(tr("▶ 播放 / 暂停", "▶ Play / Pause"))
        if self.sequence is not None:
            row = QHBoxLayout()
            row.addWidget(self.play)
            row.addWidget(self.slider, 1)
            row.addWidget(self.frame_label)
            layout.addLayout(row)
            self.slider.setRange(0, self.sequence.n_frames - 1)
            self.slider.setTracking(False)
            self.slider.valueChanged.connect(self.show_frame)
            self.play.clicked.connect(self._toggle)
            self.show_frame(entry.get("histogram_position", 0))
        controls = QHBoxLayout()
        if use_markers is not None:
            use_button = QPushButton(tr("选回当前匹配标记继续分析", "Use matching current markers"))
            use_button.clicked.connect(lambda: (self.close(), use_markers()))
            controls.addWidget(use_button)
        controls.addStretch()
        back = QPushButton(tr("回到最新状态", "Return to Latest State"))
        back.clicked.connect(self.close)
        controls.addWidget(back)
        layout.addLayout(controls)

    def _render_region(self, result: Any) -> None:
        options = self.entry.get("plot_options", {})
        if isinstance(result, RegionTrendResult):
            self.canvas.show_trends(result, **options)
        else:
            self.canvas.show_histograms(result, **options)

    def show_frame(self, position: int) -> None:
        """Reuse cached bins and retain a zoomed viewport across history frames."""
        if self.sequence is None:
            return
        limits = None
        if self.result is not None:
            limits = (self.canvas.axes.get_xlim(), self.canvas.axes.get_ylim())
        self.position = max(0, min(position, self.sequence.n_frames - 1))
        self.result = self.sequence.results[self.position]
        self._render_region(self.result)
        if limits is not None:
            self.canvas.axes.set_xlim(limits[0]); self.canvas.axes.set_ylim(limits[1])
        self.slider.blockSignals(True)
        self.slider.setValue(self.position)
        self.slider.blockSignals(False)
        time = self.result.time.utc.isot if self.result.time is not None else ""
        self.frame_label.setText(f"Frame {self.result.frame_index + 1}  {time}")
        self.canvas.draw_idle()

    def _advance(self) -> None:
        self.show_frame((self.position + 1) % self.sequence.n_frames)

    def _toggle(self) -> None:
        self.timer.stop() if self.timer.isActive() else self.timer.start()

    def done(self, result: int) -> None:
        self.timer.stop()
        super().done(result)

    def closeEvent(self, event: Any) -> None:
        self.timer.stop()
        super().closeEvent(event)
