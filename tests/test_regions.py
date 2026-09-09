from __future__ import annotations

from types import SimpleNamespace

import numpy as np
from astropy.io import fits
from astropy.time import Time, TimeDelta
from matplotlib.backend_bases import MouseButton
from PySide6.QtWidgets import QApplication

from app.data.fits_folder import FitsFolderDataset
from app.processing.region_analysis import analyze_region_trends, region_histograms
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
