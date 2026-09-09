from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import matplotlib.dates as mdates
from astropy.time import Time
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
    x1, x2 = mdates.date2num(result.times.to_datetime()[[0, 2]])
    canvas._on_press(SimpleNamespace(inaxes=canvas.axes, xdata=x1, ydata=0.25))
    canvas._on_press(SimpleNamespace(inaxes=canvas.axes, xdata=x2, ydata=1.75))
    assert any(item.get_gid() == "slope_measurement" for item in canvas.axes.texts)
    assert any("v =" in item.get_text() for item in canvas.axes.texts)
    canvas.clear_measurements()
    assert not any(item.get_gid() == "slope_measurement" for item in canvas.axes.lines)
    assert not any(item.get_gid() == "slope_measurement" for item in canvas.axes.texts)
    output = tmp_path / "td.pdf"
    export_figure(canvas.figure, output)
    assert output.read_bytes().startswith(b"%PDF")
    eps = tmp_path / "td.eps"
    export_figure(canvas.figure, eps)
    assert eps.read_bytes().startswith(b"%!PS-Adobe")


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
