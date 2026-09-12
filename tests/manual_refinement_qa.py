"""Read-only real metadata timing and local window captures for 1.2.1."""
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace
import json
import numpy as np
import matplotlib.dates as mdates
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from app.data.fits_folder import FitsFolderDataset
from app.data.quality import quality_report
from app.ui.main_window import MainWindow
from app.processing.td_generator import generate_time_distance, TDConfig
from app.processing.region_analysis import analyze_region_trends
from tests.test_history_and_updates import click


def main():
    app = QApplication([])
    folder = Path("E:/tempdata/maps_for_dem")
    dataset = FitsFolderDataset(folder)
    # 450 cached records derived from actual headers: workload benchmark, NOT
    # a claim that the available real folder contains 450 distinct FITS files.
    proxy = SimpleNamespace(n_frames=450, times=None,
        get_frame_metadata=lambda i: dataset.get_frame_metadata(i % dataset.n_frames))
    start = perf_counter(); report = quality_report(proxy); elapsed = perf_counter()-start
    print(json.dumps(dict(real_frames=dataset.n_frames, metadata_records=450, quality_seconds=elapsed,
        missing_angular_wcs=report["missing_angular_wcs"])), flush=True)
    output = Path("tests/generated/refinement-qa-1.2.2"); output.mkdir(parents=True, exist_ok=True)
    window = MainWindow(); window._install_dataset(dataset); window.show(); QTest.qWait(100)
    window.new_path("line"); click(window,280,300); click(window,420,350)
    result = generate_time_distance(dataset, window.active_path(), TDConfig(distance_unit="arcsec", tracking_mode="world_fixed"))
    window._td_finished(result)
    canvas = window.td_canvas
    xs = mdates.date2num(result.times.utc.to_datetime())
    window.velocity_fit_mode.setCurrentIndex(window.velocity_fit_mode.findData("ols"))
    window.show_acceleration.setChecked(True)
    canvas.enable_slope_measurement(True)
    indices = [0,5,10,15,23]
    dt = (xs[indices]-xs[0])*86400
    canvas._measure_points = list(zip(xs[indices], 5+.002*dt+1e-6*dt**2))
    canvas._finish_measurement(); assert canvas.measurement_count == 1
    picker = window._td_frame_picker; picker.pick.setChecked(True)
    picker._click(SimpleNamespace(inaxes=canvas.axes, button=1, xdata=xs[10]))
    picker.apply_style(dict(line_color="#dd4422", text_color="#dd4422", fontsize=11, linewidth=2))
    window.td_aspect.setCurrentIndex(window.td_aspect.findData("equal"))
    QTest.qWait(100); window.grab().save(str(output/"td.png"))
    canvas.figure.savefig(output/"acceleration.pdf")
    window.new_region("circle"); click(window,340,340); click(window,380,340)
    window.region_result = analyze_region_trends(dataset,window.regions,"mean")
    window._redraw_region(); window.main_tabs.setCurrentIndex(2)
    picker = window._region_frame_picker; picker.pick.setChecked(True)
    picker._click(SimpleNamespace(inaxes=window.region_canvas.axes, button=1, xdata=xs[10]))
    QTest.qWait(100); window.grab().save(str(output/"regions.png"))
    window.close(); app.processEvents()


if __name__ == "__main__":
    main()
