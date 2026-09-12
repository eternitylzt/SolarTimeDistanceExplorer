"""Research 1.2 regressions: science, undo/session state, caching and provenance."""
from __future__ import annotations
from types import SimpleNamespace
import json
import numpy as np
import pytest
from astropy.time import Time, TimeDelta
from astropy.io import fits
from PySide6.QtWidgets import QApplication

from app.data.cache import LRUFrameCache
from app.data.fits_folder import FitsFolderDataset
from app.data.quality import quality_report
from app.processing.velocity import fit_velocity
from app.processing.time_edges import gap_aware_edges
from app.processing.region_analysis import analyze_region_trends, region_histogram_sequence
from app.processing.td_generator import generate_time_distance, TDConfig
from app.regions.base import RegionGeometry
from app.project.session import save_session, load_session
from app.ui.main_window import MainWindow
from app.plotting.region_export import export_region_result
from tests.test_history_and_updates import click


@pytest.fixture
def research_window(tmp_path):
    app = QApplication.instance() or QApplication([])
    folder = tmp_path / "input"; folder.mkdir()
    for i, sec in enumerate([0,10,20,100]):
        data = np.arange(400,dtype=float).reshape(20,20)+i*100
        if i==2:
            data[5:10,5:10] = np.nan
        header = fits.Header({"DATE-OBS": (Time("2026-01-01")+TimeDelta(sec,format="sec")).isot, "EXPTIME": 2})
        fits.writeto(folder/f"frame{i}.fits",data,header)
    dataset = FitsFolderDataset(folder,prepare_aia=False)
    window = MainWindow(); window._install_dataset(dataset)
    yield window
    window.close(); app.processEvents()


def test_cache_obeys_byte_budget_and_promotes_recent():
    cache = LRUFrameCache(10,80)
    for i in range(2): cache.put(i,np.zeros(5))
    cache.get(0); cache.put(2,np.zeros(5))
    assert cache.get(1) is None and cache.get(0) is not None
    assert cache.used_bytes==80
    cache.set_byte_limit(16)
    assert len(cache)==0
    cache.put(5,np.zeros(100))
    assert len(cache)==0 and cache.used_bytes==0


def test_quality_flags_and_no_frame_reads(research_window, monkeypatch):
    dataset = research_window.dataset
    dataset.set_times(Time(["2026-01-01T00:00:00","2026-01-01T00:00:10","2026-01-01T00:00:10","2026-01-01T00:00:05"]))
    monkeypatch.setattr(dataset,"get_frame",lambda i: pytest.fail("Quality must not load images"))
    report = quality_report(dataset)
    assert report["duplicate_time_intervals"]==1 and report["reversed_time_intervals"]==1
    assert report["missing_angular_wcs"]==4 and report["missing_or_invalid_exposure"]==0
    assert report["time_axis"]=="user/project configured"


def test_gap_bins_do_not_modify_original_observations():
    data = np.arange(8).reshape(2,4)
    edges, rendered = gap_aware_edges(np.array([0,10,20,100]),data,5)
    np.testing.assert_allclose(edges,[-5,5,15,25,95,140])
    assert np.isnan(rendered[:,3]).all()
    np.testing.assert_array_equal(rendered[:,[0,1,2,4]],data)
    assert np.all(np.diff(edges)>0)


def test_ols_velocity_and_uncertainty():
    t = np.array([0,10,25,70,95.])
    noise = np.array([.3,-.2,.1,-.4,.2])
    fit = fit_velocity(t,3*t+10+noise)
    assert fit.slope==pytest.approx(3,abs=.01)
    assert 0<fit.stderr<.01
    assert np.abs(fit.residuals.mean())<1e-10
    assert fit_velocity(t[:2],3*t[:2]).stderr is None
    with pytest.raises(ValueError): fit_velocity(np.zeros(3),np.arange(3))


def test_shared_histograms_coverage_and_exports(research_window,tmp_path):
    dataset=research_window.dataset
    region=RegionGeometry.rectangle("R1",(9,9),12,12)
    trend=analyze_region_trends(dataset,[region],"mean")
    assert trend.valid_counts[0,2]<trend.mask_counts[0,2]
    assert trend.valid_counts[0,0]==trend.mask_counts[0,0]
    sequence=region_histogram_sequence(dataset,[region],0,3,1,20)
    for result in sequence.results:
        np.testing.assert_array_equal(result.edges[0],sequence.results[0].edges[0])
        assert result.counts[0].sum()==result.valid_counts[0]
    export_region_result(trend,tmp_path/"trend.fits")
    with fits.open(tmp_path/"trend.fits") as hdul:
        np.testing.assert_array_equal(hdul["VALID_COUNT"].data,trend.valid_counts)
        assert "PARAMETERS" in hdul
    metadata=json.loads((tmp_path/"trend.fits.json").read_text())
    assert metadata["schema"]=="STDE-provenance-1"
    assert len(metadata["source_files"])==4
    assert metadata["parameters"]["statistic"]=="mean"


def test_undo_redo_delete_rename_width_and_new_drawing(research_window):
    w=research_window
    w.new_path("line"); click(w,2,2); click(w,12,10)
    w.edit_history.flush()
    original_id=w.active_path_id
    w.path_panel.name.setText("Research Slit"); w._path_settings_changed(); w.edit_history.flush()
    w.delete_active_path(); assert not w.paths
    w.edit_history.undo()
    assert w.active_path_id==original_id and w.paths[0].name=="Research Slit"
    assert w.path_panel.paths.item(0).text()=="Research Slit"
    w.edit_history.undo(); assert w.paths[0].name=="S1"
    w.edit_history.redo(); assert w.paths[0].name=="Research Slit"
    w.edit_history.redo(); assert not w.paths
    w.new_path("smooth"); click(w,3,3); click(w,8,12); click(w,14,3); w.path_editor.finish()
    assert w.active_path().complete
    w.edit_history.flush()
    w.active_path().width=5; w._refresh_overlays(); w.edit_history.flush()
    w.edit_history.undo(); assert w.active_path().width!=5
    w.edit_history.redo(); assert w.active_path().width==5
    w.new_region("circle"); click(w,8,8); click(w,12,8); w.edit_history.flush()
    w.delete_active_region(); w.edit_history.undo()
    assert w.regions[0].complete and w.region_panel.regions.count()==1
    w.edit_history.redo(); assert not w.regions


def test_session_roundtrip_with_deleted_marker_history_and_fit(research_window,tmp_path):
    w=research_window
    w.new_path("line"); click(w,2,3); click(w,14,3)
    path=w.active_path()
    result=generate_time_distance(w.dataset,path,TDConfig())
    w._td_finished(result)
    c=w.td_canvas; c.fit_mode="ols"; c.enable_slope_measurement(True)
    import matplotlib.dates as mdates
    xs=mdates.date2num(w.dataset.times.to_datetime())
    for x,y in zip(xs[:3],[1,3.2,5]): c._on_press(SimpleNamespace(inaxes=c.axes,xdata=x,ydata=y,button=1,dblclick=False))
    c._on_press(SimpleNamespace(inaxes=c.axes,xdata=xs[2],ydata=5,button=3,dblclick=False))
    assert c.measurement_count==1 and c._measurement_groups[0]["stderr"]>0
    c.slope_auto_colors=False; c.set_measurement_style(1,text_color="#123456",font_size=17)
    # Preserve configured auto-color policy for reopening.
    w.slope_auto_colors.setChecked(False)
    w.delete_active_path()
    w.new_region("circle"); click(w,9,9); click(w,13,9)
    trend=analyze_region_trends(w.dataset,w.regions,"sum")
    w._region_trends_finished(trend)
    sequence=region_histogram_sequence(w.dataset,w.regions,0,3,1,40)
    w._install_region_histogram_sequence(sequence,2,record=True)
    w.region_canvas.axes.set_xlim(100,300)
    filename=tmp_path/"analysis.stdsession"
    save_session(filename,w._analysis_session_state())
    restored=load_session(filename)
    assert isinstance(restored["td"].times,Time)
    np.testing.assert_allclose((restored["td"].times-result.times).to_value("s"),0,atol=1e-10)
    np.testing.assert_allclose(restored["td"].matrix,result.matrix)
    w._restore_analysis_session(restored)
    assert w.td_canvas.measurement_count==1
    assert w.td_canvas.measurement_style(1)[1]=="#123456"
    assert not w.paths and w.regions[0].name=="R1"
    assert w._region_hist_position==2
    np.testing.assert_allclose(w.region_canvas.axes.get_xlim(),[100,300])
    entry=next(e for e in w._history_entries if e.get("td_result") is not None)
    assert not w._history_marker_match(entry)[0]
    w._open_history_entry(entry["id"])
    np.testing.assert_allclose(w._history_viewer.result.matrix,result.matrix)
    w._history_viewer.close()
    w.new_path("line"); click(w,3,3); click(w,14,8)
    assert w.active_path().complete


def test_session_refuses_object_arrays(tmp_path):
    with pytest.raises(ValueError):
        save_session(tmp_path/"bad.stdsession",{"array":np.array([{}],dtype=object)})
    assert not (tmp_path/"bad.stdsession").exists()


def test_time_precision_and_shared_arrays_roundtrip(tmp_path):
    time=Time([2451545.0,2451545.0],[.123456789123,.123456789124],format="jd",scale="tai")
    data=np.arange(12)
    save_session(tmp_path/"precision.stdsession",{"time":time,"shared":[data,data],"scalar":time[0]})
    state=load_session(tmp_path/"precision.stdsession")
    assert state["shared"][0] is state["shared"][1]
    assert state["time"].scale=="tai"
    np.testing.assert_array_equal(state["time"].jd1,time.jd1)
    np.testing.assert_array_equal(state["time"].jd2,time.jd2)
    assert abs((state["scalar"]-time[0]).to_value("s"))<1e-10


def test_session_rejects_modified_source_without_clearing_current(research_window,tmp_path):
    w=research_window
    state=w._analysis_session_state()
    original=w.dataset
    source=next(original.source.glob("*.fits"))
    with fits.open(source,mode="update",memmap=False) as hdul:
        hdul[0].data[0,0]=12345
    with pytest.raises(ValueError,match="changed"):
        w._restore_analysis_session(state)
    assert w.dataset is original


def test_segmented_velocity_and_uniform_frame_axis_use_real_times(research_window):
    w=research_window
    w.new_path("line"); click(w,2,3); click(w,14,3)
    w._td_finished(generate_time_distance(w.dataset,w.active_path(),TDConfig()))
    w.true_time.setChecked(False)
    c=w.td_canvas; c.fit_mode="segmented"; c.enable_slope_measurement(True)
    for x,y in [(0,1),(1,3),(3,8)]:
        c._on_press(SimpleNamespace(inaxes=c.axes,xdata=x,ydata=y,button=1))
    c._on_key(SimpleNamespace(key="enter"))
    assert c.measurement_count==2
    assert c._measurement_groups[0]["delta_t"]==pytest.approx(10)
    assert c._measurement_groups[1]["delta_t"]==pytest.approx(90)
    assert c._measurement_groups[1]["slope_time_unit"]=="s"


def test_histogram_cached_frame_updates_keep_axes_and_grid_off(research_window):
    w=research_window
    w.new_region("circle"); click(w,9,9); click(w,13,9)
    sequence=region_histogram_sequence(w.dataset,w.regions,0,3,1,20)
    w._install_region_histogram_sequence(sequence,0,record=False)
    w.region_grid.setChecked(False)
    axes=w.region_canvas.axes; artist=dict(w.region_canvas._histogram_artists)
    for i in [1,2,3,0]:
        w.show_region_histogram_frame(i)
        assert w.region_canvas.axes is axes
        assert w.region_canvas._histogram_artists==artist
        assert not any(t.gridline.get_visible() for axis in (axes.xaxis,axes.yaxis)
                       for t in (*axis.get_major_ticks(),*axis.get_minor_ticks()))


def test_figure_sidecar_and_measurements_survive_style_changes(research_window,tmp_path):
    w=research_window
    w.new_path("line"); click(w,2,3); click(w,14,3)
    result=generate_time_distance(w.dataset,w.active_path(),TDConfig())
    w._td_finished(result)
    c=w.td_canvas
    c.enable_slope_measurement(True)
    x=min(c.axes.get_xlim())
    for px,py in [(x+.00001,2),(x+.0002,4)]:
        c._on_press(SimpleNamespace(inaxes=c.axes,xdata=px,ydata=py,button=1))
    assert c.measurement_count==1
    w.td_cmap.setCurrentText("plasma")
    assert c.measurement_count==1
    options={"dpi":72,"transparent":False,"include_axes":True,"include_title":True,"include_colorbar":True}
    w._export_canvas_figure(c,str(tmp_path/"td.pdf"),options)
    meta=json.loads((tmp_path/"td.pdf.json").read_text())
    assert meta["provenance"]["schema"]=="STDE-provenance-1"
    assert len(meta["velocity_measurements"])==1
