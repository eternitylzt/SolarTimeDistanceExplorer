"""Optional real-data QA/benchmark; never changes input FITS files.

Run: python -m tests.manual_research_qa --folder E:/tempdata/maps_for_dem
Outputs live only in tests/generated/research-qa (ignored by Git).
"""
from __future__ import annotations
import argparse
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace
import warnings
import json
import numpy as np
from PySide6.QtWidgets import QApplication
from app.data.fits_folder import FitsFolderDataset
from app.data.quality import quality_report
from app.processing.td_generator import TDConfig, generate_time_distance
from app.processing.region_analysis import analyze_region_trends, region_histogram_sequence
from app.project.session import save_session, load_session
from app.ui.main_window import MainWindow
from app.plotting.region_export import export_region_result
from app.plotting.export import export_td_fits


def main() -> None:
    parser=argparse.ArgumentParser(); parser.add_argument("--folder",required=True)
    args=parser.parse_args()
    output=Path("tests/generated/research-qa"); output.mkdir(parents=True,exist_ok=True)
    app=QApplication([])
    warnings.filterwarnings("ignore",module="sunpy|astropy")
    dataset=FitsFolderDataset(args.folder,cache_size=64)
    window=MainWindow(); window._install_dataset(dataset); window.show(); app.processEvents()
    quality=quality_report(dataset)
    (output/"quality.json").write_text(json.dumps(quality,indent=2))
    def click(x,y):
        window.image_canvas.mouse_pressed.emit(SimpleNamespace(button=1,xdata=x,ydata=y,dblclick=False))
    products=[]
    for i in range(3):
        window.new_path("line"); click(280,300+20*i); click(420,350+20*i)
        result=generate_time_distance(dataset,window.active_path(),TDConfig(distance_unit="arcsec",tracking_mode="world_fixed",normalize_exposure=True))
        assert np.isfinite(result.matrix).any()
        window._td_finished(result); products.append(result)
    window.edit_history.flush(); window.delete_active_path(); window.edit_history.undo()
    assert window.paths[-1].name=="S3"
    window.edit_history.redo(); assert len(window.paths)==2
    window.new_region("circle"); click(330,350); click(350,350)
    window.new_region("circle"); click(380,390); click(395,390)
    trend=analyze_region_trends(dataset,window.regions,"mean")
    window._region_trends_finished(trend)
    # Choose a practical bin width from finite reference-region data.
    frame=dataset.get_frame(0)
    values=frame[window.regions[0].mask(frame.shape,dataset.get_wcs(0))]
    width=max(float(np.nanmax(values)-np.nanmin(values))/60,1e-6)
    sequence=region_histogram_sequence(dataset,window.regions,0,dataset.n_frames-1,1,width)
    window._install_region_histogram_sequence(sequence,0,record=True)
    window.region_grid.setChecked(False)
    window.region_canvas.draw()
    def benchmark(force_style):
        timings=[]
        for i in range(min(12,sequence.n_frames)):
            if force_style: window.region_canvas._histogram_style_signature=None
            start=perf_counter(); window.show_region_histogram_frame(i); window.region_canvas.draw()
            timings.append(1000*(perf_counter()-start))
        return float(np.median(timings))
    old_ms=benchmark(True); new_ms=benchmark(False)
    start=perf_counter()
    for i in range(dataset.n_frames): dataset.get_frame(i)
    warm_ms=1000*(perf_counter()-start)/dataset.n_frames
    state=window._analysis_session_state(); session=output/"analysis.stdsession"
    save_session(session,state); window._restore_analysis_session(load_session(session))
    assert window._region_hist_sequence.n_frames==dataset.n_frames
    assert len(window.paths)==2
    entry=next(e for e in window._history_entries if e.get("td_result") is not None)
    window._open_history_entry(entry["id"]); app.processEvents()
    assert window._history_viewer.result.path_id==products[-1].path_id
    window._history_viewer.close()
    window.new_path("polyline"); click(280,300); click(350,390); click(420,320); window.path_editor.finish()
    assert window.active_path().complete
    window.main_tabs.setCurrentIndex(1); app.processEvents()
    window.grab().save(str(output/"td-ui.png"))
    window.main_tabs.setCurrentIndex(2); app.processEvents()
    window.grab().save(str(output/"region-ui.png"))
    export_region_result(trend,output/"region.fits"); export_td_fits(products[0],output/"td.fits")
    report={"frames":dataset.n_frames,"shape":dataset.shape,"old_histogram_ms_median":old_ms,
            "optimized_histogram_ms_median":new_ms,"cached_frame_read_ms_mean":warm_ms,
            "session_bytes":session.stat().st_size,"cache":window.dataset.cache_stats()}
    (output/"benchmark.json").write_text(json.dumps(report,indent=2))
    print(json.dumps(report)); print("REAL DATA QA PASSED")
    window.close(); app.processEvents()


if __name__=="__main__": main()
