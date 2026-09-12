"""Local 1.2.1 regressions: responsive reporting, fit bands and plot navigation."""
from types import SimpleNamespace
from time import perf_counter, sleep
import numpy as np
import pytest
import matplotlib.dates as mdates
from matplotlib.lines import Line2D
from matplotlib.collections import PolyCollection
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from app.data.quality import quality_report
from app.processing.velocity import fit_motion
from app.processing.td_generator import generate_time_distance, TDConfig
from app.processing.region_analysis import analyze_region_trends, region_histograms
from app.regions.base import RegionGeometry
from tests.test_research_upgrade import research_window
from tests.test_history_and_updates import click


def test_quality_450_headers_cached_and_cancellable(research_window, monkeypatch):
    import app.data.quality as module
    meta = research_window.dataset.get_frame_metadata(0)
    source = SimpleNamespace(n_frames=450, times=None, get_frame_metadata=lambda _: meta)
    calls = []
    original = module.spatial_wcs
    monkeypatch.setattr(module, "spatial_wcs", lambda h: (calls.append(h), original(h))[1])
    progress = []
    report = quality_report(source, lambda n, total: progress.append(n))
    assert report["frames"] == 450 and len(calls) == 1 and progress[-1] == 450
    with pytest.raises(InterruptedError):
        quality_report(source, cancelled=lambda: True)


def test_quality_gui_worker_keeps_event_loop_alive(research_window, monkeypatch):
    import app.ui.quality_worker as module
    def slow(dataset, progress, cancelled):
        for i in range(30):
            if cancelled(): raise InterruptedError()
            sleep(.005); progress(i+1, 30)
        return {"frames": 30}
    monkeypatch.setattr(module, "quality_report", slow)
    from app.ui.dialogs import HelpTextDialog
    monkeypatch.setattr(HelpTextDialog, "exec", lambda self: 0)
    ticks = []; timer = QTimer(); timer.timeout.connect(lambda: ticks.append(1)); timer.start(5)
    start = perf_counter(); research_window.show_quality_report()
    assert perf_counter()-start < .5
    deadline = perf_counter()+5
    while research_window._quality_worker is not None and perf_counter()<deadline:
        QTest.qWait(10)
    timer.stop()
    assert research_window._quality_worker is None and len(ticks)>5
    assert research_window._quality_cache == {"frames": 30}


def test_acceleration_and_mean_band():
    t = np.array([0, 2, 5, 9, 15.])
    fit = fit_motion(t, 4+3*t+.5*.4*t*t, True)
    assert fit["acceleration"] == pytest.approx(.4)
    assert fit["acceleration_stderr"] < 1e-10
    fit = fit_motion(t, 3*t+np.array([.2, -.3, .5, -.1, .2]))
    assert (fit["sigma"]>0).all()
    with pytest.raises(ValueError): fit_motion(t[:3], t[:3], True)
    with pytest.raises(ValueError): fit_motion(np.ones(4), np.arange(4), True)


def make_td(w):
    w.new_path("line"); click(w, 2, 3); click(w, 14, 3)
    result = generate_time_distance(w.dataset, w.active_path(), TDConfig())
    w._td_finished(result)
    return result


def test_plot_shape_fit_picks_band_restore_and_clear(research_window):
    w = research_window; result = make_td(w); c = w.td_canvas
    c.slope_velocity_unit = "auto"
    c.show_acceleration = True
    c.show_result(result, aspect="equal"); c.draw()
    assert c.axes.get_box_aspect() == 1
    assert c.axes.get_window_extent().width > 100
    xs = mdates.date2num(result.times.utc.to_datetime())
    for mode in ("ols", "acceleration"):
        c.fit_mode = mode; c.enable_slope_measurement(True)
        c._measure_points = list(zip(xs, [1, 2.2, 3, 8]))
        c._finish_measurement()
        group = c._measurement_groups[-1]
        assert any(isinstance(a, Line2D) and a.get_marker()=="o" for a in group["artists"])
        assert any(isinstance(a, PolyCollection) for a in group["artists"])
    saved = c.measurement_snapshot(); c.restore_measurements(saved)
    assert c.measurement_snapshot() == saved
    c.slope_auto_colors = False; c.set_measurement_style(2, font_size=16, line_color="red")
    assert "a_" in c._measurement_groups[1]["label"].get_text()
    c.clear_measurements()
    assert not any(a.get_gid()=="slope_measurement" for a in c.axes.get_children())


def test_td_and_region_frame_navigation(research_window):
    w = research_window; result = make_td(w)
    picker = w._td_frame_picker
    picker.pick.setChecked(True)
    picker._click(SimpleNamespace(inaxes=w.td_canvas.axes, button=1,
        xdata=mdates.date2num(result.times[2].utc.to_datetime())))
    assert picker.selected == 2 and picker.artists
    picker._jump(); assert w.current_frame == 2 and w.main_tabs.currentIndex()==0
    region = RegionGeometry.rectangle("R1", (9,9), 8,8)
    w.region_result = analyze_region_trends(w.dataset, [region], "mean")
    w._redraw_region()
    picker = w._region_frame_picker; picker.pick.setChecked(True)
    picker._click(SimpleNamespace(inaxes=w.region_canvas.axes, button=1,
        xdata=mdates.date2num(w.dataset.times[1].utc.to_datetime())))
    picker._jump(); assert w.current_frame==1
    w.region_result = None; picker._redraw(None)
    assert picker.selected is None and not picker.jump.isEnabled()


def test_histogram_frame_pick(research_window):
    w = research_window
    region = RegionGeometry.rectangle("R1", (9,9), 8,8)
    w.region_result = region_histograms(w.dataset.get_frame(3), [region], w.dataset.get_wcs(3), 3, 20, w.dataset.get_time(3))
    w._redraw_region()
    picker = w._region_frame_picker; picker.pick.setChecked(True)
    picker._click(SimpleNamespace(inaxes=w.region_canvas.axes, button=1, xdata=100))
    assert picker.selected == 3
    picker._jump(); assert w.current_frame == 3
