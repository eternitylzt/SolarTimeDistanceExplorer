from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import matplotlib.dates as mdates
from matplotlib.backend_bases import MouseEvent
from matplotlib.lines import Line2D
from astropy.time import Time
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from app.paths.base import PathGeometry
from app.animation.exporter import export_animation
from app.data.base import TimeSeriesDataset
from app.data.metadata import FrameMetadata
from app.plotting.export import export_figure
from app.processing.td_generator import TDResult
from app.regions.base import RegionGeometry
from app.ui.td_plot import TimeDistanceCanvas
from app.ui.region_plot import RegionAnalysisCanvas
from app.ui.main_window import MainWindow
from app.processing.region_analysis import RegionHistogramResult, RegionTrendResult
from types import SimpleNamespace


def _application() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_pdf_backend_time_format_and_slope_clear(tmp_path: Path) -> None:
    _application()
    result = TDResult(
        matrix=np.arange(12, dtype=float).reshape(3, 4),
        times=Time(["2026-01-01T12:50:00", "2026-01-01T12:50:10", "2026-01-01T12:50:25", "2026-01-01T12:51:00"]),
        frame_indices=np.arange(4),
        distance=np.array([0.0, 1.0, 2.0]),
        distance_unit="arcsec",
        path_id="test",
        metadata={"path": {"name": "S1"}},
    )
    canvas = TimeDistanceCanvas()
    canvas.show_result(result, time_format="%H:%M:%S", title="Time–Distance Diagram — S1")
    canvas.draw()
    labels = [item.get_text() for item in canvas.axes.get_xticklabels() if item.get_text()]
    assert labels and all(label.count(":") == 2 for label in labels)
    canvas._measurement_artists.extend(canvas.axes.plot([0, 1], [0, 1]))
    canvas.clear_measurements()
    assert canvas._measurement_artists == []
    canvas.enable_slope_measurement(True)
    canvas.set_slope_style(
        "#ff0000", 2.0, 13.0, "--", "#00ff00", 2, auto_colors=False
    )
    x1, x2 = mdates.date2num(result.times.to_datetime()[[0, 2]])
    canvas._on_press(SimpleNamespace(inaxes=canvas.axes, xdata=x1, ydata=0.25))
    canvas._on_press(SimpleNamespace(inaxes=canvas.axes, xdata=x2, ydata=1.75))
    assert any(item.get_gid() == "slope_measurement" for item in canvas.axes.texts)
    assert any("v_{1}" in item.get_text() for item in canvas.axes.texts)
    annotation = next(item for item in canvas.axes.texts if "v_{1}" in item.get_text())
    assert annotation.get_color() == "#00ff00"
    assert annotation.get_fontsize() == 13.0
    assert "0.06" in annotation.get_text()
    canvas.clear_measurements()
    assert not any(item.get_gid() == "slope_measurement" for item in canvas.axes.lines)
    assert not any(item.get_gid() == "slope_measurement" for item in canvas.axes.texts)
    output = tmp_path / "td.pdf"
    export_figure(canvas.figure, output)
    assert output.read_bytes().startswith(b"%PDF")
    eps = tmp_path / "td.eps"
    export_figure(canvas.figure, eps)
    assert eps.read_bytes().startswith(b"%!PS-Adobe")


def test_td_zoom_updates_start_label_and_multiple_velocity_units() -> None:
    _application()
    result = TDResult(
        matrix=np.arange(12, dtype=float).reshape(3, 4),
        times=Time(["2026-01-01T12:50:00", "2026-01-01T12:50:10", "2026-01-01T12:50:25", "2026-01-01T12:51:00"]),
        frame_indices=np.arange(4), distance=np.array([0.0, 1.0, 2.0]),
        distance_unit="arcsec", path_id="test",
        metadata={"path": {"name": "S1"}, "reference_pixel_scale_arcsec": 0.6},
    )
    canvas = TimeDistanceCanvas()
    canvas.show_result(result, include_start_time=True)
    x = mdates.date2num(result.times.to_datetime())
    canvas.axes.set_xlim(x[1], x[3])
    assert "2026-01-01T12:50:10" in canvas.axes.get_xlabel()

    canvas.set_slope_style(
        "#ffffff", 1.5, 10.0, "-", "#ffffff", 1,
        "transparent", "km", True,
    )
    for first, second in (((x[0], 0.0), (x[1], 1.0)), ((x[1], 0.5), (x[2], 2.0))):
        canvas.enable_slope_measurement(True)
        canvas._on_press(SimpleNamespace(inaxes=canvas.axes, xdata=first[0], ydata=first[1]))
        canvas._on_press(SimpleNamespace(inaxes=canvas.axes, xdata=second[0], ydata=second[1]))
    labels = [item for item in canvas.axes.texts if item.get_gid() == "slope_measurement"]
    assert any("v_{1}" in item.get_text() and "km/s" in item.get_text() for item in labels)
    assert any("v_{2}" in item.get_text() and "km/s" in item.get_text() for item in labels)
    assert labels[0].get_color() != labels[1].get_color()
    assert all(item.get_bbox_patch().get_alpha() == 0.0 for item in labels)
    canvas.close()


def test_slope_markers_have_no_endpoints_and_keep_individual_colors() -> None:
    app = _application()
    result = TDResult(
        matrix=np.arange(12, dtype=float).reshape(3, 4),
        times=Time(["2026-01-01T12:50:00", "2026-01-01T12:50:10", "2026-01-01T12:50:25", "2026-01-01T12:51:00"]),
        frame_indices=np.arange(4), distance=np.array([0.0, 2.0, 4.0]),
        distance_unit="arcsec", path_id="test", metadata={"path": {"name": "S1"}},
    )
    canvas = TimeDistanceCanvas()
    canvas.show_result(result, true_time=True)
    left, right = canvas.axes.get_xlim()
    for points in (((0.2, 1.0), (0.8, 4.0)), ((0.25, 4.0), (0.75, 2.0))):
        canvas.enable_slope_measurement(True)
        for fraction, y in points:
            canvas._on_press(
                SimpleNamespace(
                    inaxes=canvas.axes,
                    xdata=left + fraction * (right - left),
                    ydata=y,
                )
            )
    slope_lines = [
        item for item in canvas.axes.lines
        if isinstance(item, Line2D) and item.get_gid() == "slope_measurement"
    ]
    assert len(slope_lines) == 2
    assert all(item.get_marker() in {"None", "none", "", None} for item in slope_lines)

    canvas.set_slope_style("#ffffff", 2.0, 10.0, auto_colors=False)
    canvas.set_measurement_colors(1, line_color="#ff0000", text_color="#00ff00")
    canvas.set_measurement_colors(2, line_color="#0000ff", text_color="#ffff00")
    assert canvas.measurement_colors(1) == ("#ff0000", "#00ff00")
    assert canvas.measurement_colors(2) == ("#0000ff", "#ffff00")

    first = canvas._measurement_groups[0]
    label = first["label"]
    canvas.draw()
    old_position = label.get_position()
    x_pixel, y_pixel = canvas.axes.transData.transform(old_position)
    canvas._on_press(MouseEvent("button_press_event", canvas, x_pixel, y_pixel, button=1))
    target = (old_position[0], old_position[1] + 0.8)
    target_x, target_y = canvas.axes.transData.transform(target)
    canvas._on_motion(MouseEvent("motion_notify_event", canvas, target_x, target_y, button=1))
    canvas._on_release(MouseEvent("button_release_event", canvas, target_x, target_y, button=1))
    assert label.get_position()[1] > old_position[1] + 0.5
    canvas.close(); app.processEvents()


def test_velocity_ui_supports_all_and_per_marker_background(monkeypatch) -> None:
    app = _application()
    window = MainWindow()
    result = TDResult(
        matrix=np.arange(12, dtype=float).reshape(3, 4),
        times=Time(["2026-01-01T12:50:00", "2026-01-01T12:50:10", "2026-01-01T12:50:25", "2026-01-01T12:51:00"]),
        frame_indices=np.arange(4), distance=np.array([0.0, 2.0, 4.0]),
        distance_unit="arcsec", path_id="test", metadata={"path": {"name": "S1"}},
    )
    window.td_canvas.show_result(result, true_time=True)
    left, right = window.td_canvas.axes.get_xlim()
    for first_y, second_y in ((1.0, 4.0), (4.0, 2.0)):
        window.td_canvas.enable_slope_measurement(True)
        window.td_canvas._on_press(SimpleNamespace(inaxes=window.td_canvas.axes, xdata=left, ydata=first_y))
        window.td_canvas._on_press(SimpleNamespace(inaxes=window.td_canvas.axes, xdata=right, ydata=second_y))

    window.slope_auto_colors.setChecked(False)
    assert window.slope_selection.findData(-1) >= 0
    assert window.slope_selection.isEnabled()
    window.slope_selection.setCurrentIndex(window.slope_selection.findData(1))

    monkeypatch.setattr("app.ui.main_window.QColorDialog.getColor", lambda *_args, **_kwargs: QColor("#ff0000"))
    window._choose_slope_color()
    assert window.td_canvas.measurement_style(1)[:2] == ("#ff0000", "#ff0000")
    second_before = window.td_canvas.measurement_style(2)

    monkeypatch.setattr("app.ui.main_window.QColorDialog.getColor", lambda *_args, **_kwargs: QColor("#00ff00"))
    window._choose_slope_text_color()
    assert window.td_canvas.measurement_style(1)[:2] == ("#ff0000", "#00ff00")
    assert window.td_canvas.measurement_style(2) == second_before

    window.slope_background_transparent.setChecked(True)
    assert window.td_canvas.measurement_style(1)[2] == "transparent"
    assert window.td_canvas.measurement_style(2)[2] != "transparent"

    window.slope_selection.setCurrentIndex(window.slope_selection.findData(1))
    window.slope_fontsize.setValue(17.0)
    assert window.td_canvas.measurement_style(1)[3] == 17.0
    assert window.td_canvas.measurement_style(2)[3] != 17.0

    window.slope_selection.setCurrentIndex(window.slope_selection.findData(-1))
    window.slope_fontsize.setValue(13.0)
    assert all(window.td_canvas.measurement_style(i)[3] == 13.0 for i in (1, 2))

    window.slope_selection.setCurrentIndex(window.slope_selection.findData(-1))
    monkeypatch.setattr("app.ui.main_window.QColorDialog.getColor", lambda *_args, **_kwargs: QColor("#123456"))
    window._choose_slope_background()
    assert all(window.td_canvas.measurement_style(i)[2] == "#123456" for i in (1, 2))
    assert window.slope_velocity_unit.currentData() == "km"

    window.slope_auto_colors.setChecked(True)
    assert not window.slope_selection.isEnabled()
    window.close(); app.processEvents()


def test_filtered_figure_export_restores_live_artists(tmp_path: Path) -> None:
    _application()
    canvas = TimeDistanceCanvas()
    result = TDResult(
        matrix=np.arange(6, dtype=float).reshape(2, 3), times=None,
        frame_indices=np.arange(3), distance=np.array([0.0, 1.0]),
        distance_unit="pixel", path_id="test", metadata={"path": {"name": "S1"}},
    )
    canvas.show_result(result, title="Keep me", show_colorbar=True)
    colorbar_axes = canvas.figure.axes[1]
    output = tmp_path / "filtered.png"
    export_figure(
        canvas.figure, output, main_axes=canvas.axes,
        include_axes=False, include_title=False, include_colorbar=False,
    )
    assert output.stat().st_size > 100
    assert canvas.axes.axison
    assert canvas.axes.title.get_visible()
    assert colorbar_axes.get_visible() and colorbar_axes.get_in_layout()
    canvas.close()


def test_image_display_range_controls_redraw_immediately() -> None:
    app = _application()
    window = MainWindow()
    data = np.arange(100, dtype=float).reshape(10, 10)
    window.image_canvas.show_frame(data, None, "Image")
    window.image_panel.normalization.setCurrentIndex(
        window.image_panel.normalization.findData("manual")
    )
    window.image_panel.vmin.setValue(20.0)
    window.image_panel.vmax.setValue(40.0)
    app.processEvents()
    assert window.image_canvas._image_artist.get_clim() == (20.0, 40.0)
    window.image_panel.normalization.setCurrentIndex(
        window.image_panel.normalization.findData("percentile")
    )
    window.image_panel.percentile_low.setValue(10.0)
    window.image_panel.percentile_high.setValue(90.0)
    app.processEvents()
    assert np.allclose(window.image_canvas._image_artist.get_clim(), (9.9, 89.1))
    window.image_panel.normalization.setCurrentIndex(
        window.image_panel.normalization.findData("minmax")
    )
    app.processEvents()
    assert window.image_canvas._image_artist.get_clim() == (0.0, 99.0)

    layout = {"left": 0.16, "right": 0.84, "bottom": 0.14, "top": 0.88, "wspace": 0.3, "hspace": 0.25}
    window._apply_plot_layout(window.image_canvas, layout)
    window.image_canvas.show_frame(data + 1, None, "Image 2")
    assert window.image_canvas.figure.get_layout_engine() is None
    assert np.isclose(window.image_canvas.figure.subplotpars.left, 0.16)
    assert np.isclose(window.image_canvas.figure.subplotpars.right, 0.84)
    assert window.image_canvas.axes.get_anchor() == "C"
    window.close(); app.processEvents()


def test_region_plots_use_marker_colors_and_english_labels() -> None:
    _application()
    result = RegionTrendResult(
        times=Time(["2026-01-01T00:00:00", "2026-01-01T00:00:10"]),
        frame_indices=np.arange(2),
        region_ids=["one", "two"],
        region_names=["R1", "R2"],
        values=np.array([[1.0, 2.0], [2.0, 4.0]]),
        statistic="mean",
        region_colors=["#ff0000", "#00ff00"],
    )
    canvas = RegionAnalysisCanvas()
    canvas.show_trends(result, line_style="--", line_width=2.5, marker="o")
    assert [line.get_color() for line in canvas.axes.lines] == ["#ff0000", "#00ff00"]
    assert all(line.get_linestyle() == "--" for line in canvas.axes.lines)
    plotted_text = " ".join([
        canvas.axes.get_title(), canvas.axes.get_xlabel(), canvas.axes.get_ylabel(),
    ])
    assert not any("\u4e00" <= char <= "\u9fff" for char in plotted_text)
    canvas.show_trends(result, plot_type="bar", title_size=15, legend_fontsize=13)
    assert canvas.axes.patches
    assert canvas.axes.title.get_fontsize() == 15
    assert canvas.axes.get_legend().get_texts()[0].get_fontsize() == 13

    histogram = RegionHistogramResult(
        region_ids=["one", "two"], region_names=["R1", "R2"],
        edges=[np.array([0.0, 1.0, 2.0]), np.array([0.0, 1.0, 2.0])],
        counts=[np.array([100, 50]), np.array([2, 1])], frame_index=0,
        bin_width=1.0, region_colors=["#ff0000", "#00ff00"],
    )
    canvas.show_histograms(histogram, y_unit="frequency", plot_type="bar")
    assert canvas.axes.get_ylabel() == "Relative Frequency"
    # Tall distribution is drawn first; the small green distribution remains on top.
    assert canvas.axes.patches[-1].get_facecolor()[1] > canvas.axes.patches[-1].get_facecolor()[0]


def test_marker_visibility_style_and_label_roundtrip() -> None:
    slit = PathGeometry(
        "line", np.array([[1.0, 2.0], [3.0, 4.0]]), name="S4",
        visible=False, show_label=True, label_position_pixel=(2.5, 2.75),
        display_color="#123456", display_linewidth=3.5,
        label_color="#abcdef", label_background_color="#102030", label_fontsize=14.0,
    )
    restored_slit = PathGeometry.from_dict(slit.to_dict())
    assert not restored_slit.visible
    assert restored_slit.label_position_pixel == (2.5, 2.75)
    assert restored_slit.display_linewidth == 3.5
    assert restored_slit.label_color == "#abcdef"
    assert restored_slit.label_background_color == "#102030"
    assert restored_slit.label_fontsize == 14.0

    region = RegionGeometry.circle("R2", (8.0, 9.0), 3.0)
    region.label_position_pixel = (7.0, 12.0)
    region.visible = False
    region.label_color = "#fedcba"
    region.label_background_color = "#302010"
    region.label_fontsize = 13.0
    restored_region = RegionGeometry.from_dict(region.to_dict())
    assert not restored_region.visible
    assert restored_region.label_position_pixel == (7.0, 12.0)
    assert restored_region.label_color == "#fedcba"
    assert restored_region.label_background_color == "#302010"
    assert restored_region.label_fontsize == 13.0


class _TinyDataset(TimeSeriesDataset):
    source_type = "test"

    def __init__(self) -> None:
        self._frames = [np.arange(256, dtype=float).reshape(16, 16), np.eye(16) * 255.0]
        metadata = [FrameMetadata(source="test", time=None, header={}, exposure_seconds=None, shape=(16, 16)) for _ in self._frames]
        super().__init__("tiny", None, metadata, (16, 16))

    def get_frame(self, index: int) -> np.ndarray:
        return self._frames[index]

    def get_wcs(self, index: int):
        return None


def test_application_animation_export_gif_and_mp4(tmp_path: Path) -> None:
    dataset = _TinyDataset()
    gif = tmp_path / "movie.gif"
    mp4 = tmp_path / "movie.mp4"
    export_animation(dataset, gif, 0, 1, 1, 2.0, "gray", output_size=(32, 24))
    export_animation(dataset, mp4, 0, 1, 1, 2.0, "gray", output_size=(32, 24))
    assert gif.stat().st_size > 100
    assert mp4.stat().st_size > 100
    assert b"ftyp" in mp4.read_bytes()[:64]

    annotated = tmp_path / "current_view.mp4"
    export_animation(
        dataset, annotated, 0, 1, 1, 2.0, "viridis",
        output_size=(480, 320),
        viewport_limits=((3.5, 12.5), (2.5, 13.5)),
        include_axes=True, include_timestamp=True,
        include_title=True, include_colorbar=True,
    )
    assert annotated.stat().st_size > 1000
    assert b"ftyp" in annotated.read_bytes()[:64]
