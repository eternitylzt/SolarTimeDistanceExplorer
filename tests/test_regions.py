from __future__ import annotations

from types import SimpleNamespace

import numpy as np
from astropy.io import fits
from astropy.time import Time, TimeDelta
from matplotlib.backend_bases import MouseButton
from matplotlib.patches import StepPatch
from PySide6.QtWidgets import QApplication

from app.data.fits_folder import FitsFolderDataset
from app.animation.exporter import export_region_histogram_animation
from app.processing.region_analysis import (
    analyze_region_trends,
    region_histogram_sequence,
    region_histograms,
)
from app.regions.base import RegionGeometry
from app.plotting.region_export import export_region_result
from app.ui.main_window import MainWindow
from app.ui.region_plot import RegionAnalysisCanvas
from tests.data_generator import _header


def _known_folder(tmp_path):
    for index, value in enumerate((2.0, 5.0, 9.0)):
        header = _header(Time("2026-01-01") + TimeDelta(index, format="sec"))
        fits.PrimaryHDU(np.full((20, 20), value), header=header).writeto(tmp_path / f"r{index}.fits")
    return FitsFolderDataset(tmp_path)


def test_circle_rectangle_polygon_masks_and_multi_region_trends(tmp_path) -> None:
    dataset = _known_folder(tmp_path)
    regions = [
        RegionGeometry.circle("C", (10, 10), 3),
        RegionGeometry.rectangle("R", (10, 10), 4, 6, 25),
        RegionGeometry("polygon", name="P", control_points_pixel=np.array([[2, 2], [8, 2], [5, 8]])),
    ]
    assert all(0 < region.mask((20, 20)).sum() < 400 for region in regions)
    mean_result = analyze_region_trends(dataset, regions, "mean")
    assert mean_result.values.shape == (3, 3)
    assert np.allclose(mean_result.values, [[2, 5, 9]] * 3)
    assert mean_result.region_colors == [item.display_color for item in regions]
    sum_result = analyze_region_trends(dataset, regions, "sum")
    assert np.all(sum_result.values[:, 2] > sum_result.values[:, 0])
    histogram = region_histograms(
        dataset.get_frame(0), regions, dataset.get_wcs(0), 0, 0.5,
        time=dataset.get_time(0),
    )
    assert len(histogram.counts) == 3
    assert histogram.region_colors == [item.display_color for item in regions]
    assert all(counts.sum() > 0 for counts in histogram.counts)
    canvas = RegionAnalysisCanvas()
    canvas.show_histograms(histogram, plot_type="bar")
    assert canvas.axes.patches
    assert all(isinstance(item, StepPatch) for item in canvas.axes.patches)
    assert len(canvas.axes.patches) == len(regions)
    assert "2026-01-01" in canvas.axes.get_title()
    canvas.show_histograms(histogram, plot_type="line")
    assert len(canvas.axes.lines) == 3
    export_region_result(mean_result, tmp_path / "trends.fits")
    export_region_result(mean_result, tmp_path / "trends.csv")
    export_region_result(histogram, tmp_path / "hist.txt")
    assert (tmp_path / "trends.fits").exists()
    assert "time_utc" in (tmp_path / "trends.csv").read_text(encoding="utf-8")

    regions[1].visible = False
    selected = analyze_region_trends(dataset, regions, "mean")
    selected_histogram = region_histograms(dataset.get_frame(0), regions, None, 0, 0.5)
    assert selected.region_names == ["C", "P"]
    assert selected_histogram.region_names == ["C", "P"]


def test_interactive_circle_uses_two_clicks(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow(); window._install_dataset(_known_folder(tmp_path))
    window.region_panel.region_type.setCurrentText("circle"); window.new_region()
    assert window.region_editor.drawing
    window.region_editor._press(SimpleNamespace(button=MouseButton.LEFT, xdata=8.0, ydata=9.0, dblclick=False))
    window.region_editor._move(SimpleNamespace(xdata=12.0, ydata=9.0))
    window.region_editor._press(SimpleNamespace(button=MouseButton.LEFT, xdata=12.0, ydata=9.0, dblclick=False))
    assert window.active_region() is not None and window.active_region().complete
    assert not window.region_editor.drawing
    assert np.isclose(np.hypot(*(window.active_region().control_points_pixel[1] - window.active_region().control_points_pixel[0])), 4.0)
    window.close(); app.processEvents()


def test_histogram_sequence_uses_requested_range_and_real_times(tmp_path) -> None:
    dataset = _known_folder(tmp_path)
    regions = [RegionGeometry.circle("R1", (10, 10), 3)]
    result = region_histogram_sequence(dataset, regions, 0, 2, 2, 0.5)
    assert result.frame_indices.tolist() == [0, 2]
    assert result.n_frames == 2
    assert [item.frame_index for item in result.results] == [0, 2]
    assert result.results[1].time is not None
    assert result.results[1].time.isot.startswith("2026-01-01T00:00:02")


def test_region_history_restores_overwritten_result_and_sequence(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow(); dataset = _known_folder(tmp_path); window._install_dataset(dataset)
    region = RegionGeometry.circle("R1", (10, 10), 3)
    window.regions.append(region)
    window.region_panel.regions.addItem(window._marker_item(region.name, True, region.id))
    trend = analyze_region_trends(dataset, [region], "mean")
    histogram = region_histograms(dataset.get_frame(0), [region], dataset.get_wcs(0), 0, 0.5)
    window._record_history("trend", main_tab=2, left_tab=3, region_result=trend)
    trend_entry = window._history_entries[0]["id"]
    window._record_history("hist", main_tab=2, left_tab=3, region_result=histogram)
    window._open_history_entry(trend_entry)
    assert window.region_result is None
    assert window._history_viewer.result is trend
    sequence = region_histogram_sequence(dataset, [region], 0, 2, 1, 0.5)
    window._record_history("sequence", main_tab=2, left_tab=3, histogram_sequence=sequence)
    sequence_entry = window._history_entries[0]["id"]
    window._open_history_entry(sequence_entry)
    assert window._region_hist_sequence is None
    assert window._history_viewer.sequence is sequence
    window.regions.clear()
    window._open_history_entry(trend_entry)
    assert window._history_viewer.result is trend
    assert not window._history_marker_match(window._history_viewer.entry)[0]
    assert len(window._history_viewer.canvas.axes.lines) == 1
    window._open_history_entry(sequence_entry)
    window._history_viewer.show_frame(2)
    assert window._history_viewer.result is sequence.results[2]
    assert window.region_result is None
    window._history_viewer.close()
    window.close(); app.processEvents()


def test_region_histogram_sequence_exports_playable_mp4(tmp_path) -> None:
    dataset = _known_folder(tmp_path)
    region = RegionGeometry.circle("R1", (10, 10), 3)
    sequence = region_histogram_sequence(dataset, [region], 0, 2, 2, 0.5)
    movie = tmp_path / "region_histograms.mp4"
    export_region_histogram_animation(
        sequence, movie, 2.0, (320, 240), start=1, end=1,
        viewport_limits=((1.5, 2.5), (0.0, 40.0)), include_axes=False,
        include_title=False, include_timestamp=False, include_legend=False,
    )
    assert movie.is_file() and movie.stat().st_size > 1000


def test_histogram_sequence_cache_and_zoom_are_shared_across_frames(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    dataset = _known_folder(tmp_path)
    region = RegionGeometry.circle("R1", (10, 10), 3)
    sequence = region_histogram_sequence(dataset, [region], 0, 2, 1, 0.5)
    window = MainWindow(); window._install_dataset(dataset)
    window.regions.append(region)
    window.region_panel.regions.addItem(window._marker_item(region.name, True, region.id))
    window._install_region_histogram_sequence(sequence, 0, record=False)

    # Sequence results are retained, rather than recalculated when scrubbing.
    assert window._region_hist_sequence is sequence
    first_result = sequence.results[0]
    window.region_canvas.axes.set_xlim(1.7, 2.3)
    window.region_canvas.axes.set_ylim(0.2, 25.0)
    window.show_region_histogram_frame(1)
    assert window._region_hist_sequence.results[0] is first_result
    assert np.allclose(window.region_canvas.axes.get_xlim(), (1.7, 2.3))
    assert np.allclose(window.region_canvas.axes.get_ylim(), (0.2, 25.0))
    window.show_region_histogram_frame(2)
    assert np.allclose(window.region_canvas.axes.get_xlim(), (1.7, 2.3))
    assert np.allclose(window.region_canvas.axes.get_ylim(), (0.2, 25.0))
    window.close(); app.processEvents()


def test_histogram_sequence_grid_can_be_disabled_across_cached_frames(tmp_path) -> None:
    """Turning Grid off must also hide minor grid artists on reused axes."""
    app = QApplication.instance() or QApplication([])
    dataset = _known_folder(tmp_path)
    region = RegionGeometry.circle("R1", (10, 10), 3)
    sequence = region_histogram_sequence(dataset, [region], 0, 2, 1, 0.5)
    window = MainWindow(); window._install_dataset(dataset)
    window.regions.append(region)
    window.region_panel.regions.addItem(window._marker_item(region.name, True, region.id))
    window._install_region_histogram_sequence(sequence, 0, record=False)

    window.region_grid.setChecked(False)
    window.show_region_histogram_frame(1)
    app.processEvents()
    ticks = (
        *window.region_canvas.axes.xaxis.get_major_ticks(),
        *window.region_canvas.axes.xaxis.get_minor_ticks(),
        *window.region_canvas.axes.yaxis.get_major_ticks(),
        *window.region_canvas.axes.yaxis.get_minor_ticks(),
    )
    assert ticks
    assert not any(tick.gridline.get_visible() for tick in ticks)
    window.show_region_histogram_frame(2)
    assert not any(
        tick.gridline.get_visible()
        for axis in (window.region_canvas.axes.xaxis, window.region_canvas.axes.yaxis)
        for tick in (*axis.get_major_ticks(), *axis.get_minor_ticks())
    )
    window.close(); app.processEvents()


def test_large_histogram_uses_one_artist_per_region() -> None:
    app = QApplication.instance() or QApplication([])
    result = region_histograms(
        np.linspace(0.0, 100.0, 40_000).reshape(200, 200),
        [RegionGeometry.rectangle("R1", (100, 100), 198, 198)],
        None, 0, 0.005,
    )
    canvas = RegionAnalysisCanvas(); canvas.show_histograms(result, plot_type="bar")
    app.processEvents()
    assert len(canvas.axes.patches) == 1
    assert isinstance(canvas.axes.patches[0], StepPatch)
    canvas.close()
