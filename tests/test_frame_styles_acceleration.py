"""Frame marker interaction and independent OLS/acceleration presentation."""
from types import SimpleNamespace
import numpy as np
import matplotlib.dates as mdates
from matplotlib.backend_bases import MouseEvent
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QPlainTextEdit, QPushButton
from app.processing.region_analysis import analyze_region_trends
from app.regions.base import RegionGeometry
from tests.test_research_upgrade import research_window
from tests.test_research_refinements import make_td


def test_auto_acceleration_hidden_details_and_toggle(research_window, monkeypatch):
    w = research_window; result = make_td(w); c = w.td_canvas
    w.velocity_fit_mode.setCurrentIndex(w.velocity_fit_mode.findData("ols"))
    assert not w.show_acceleration.isHidden()
    assert w.velocity_fit_mode.findData("acceleration") == -1
    c.slope_velocity_unit = "auto"
    xs = mdates.date2num(result.times.utc.to_datetime())
    seconds = (xs-xs[0])*86400
    c.enable_slope_measurement(True)
    c._measure_points = list(zip(xs, 2+3*seconds+.2*seconds**2))
    c._finish_measurement()
    group = c._measurement_groups[0]
    assert abs(group["acceleration"]-.4) < 1e-8
    assert "a_" not in group["label"].get_text()
    original = c.measurement_snapshot()[0]
    w.show_acceleration.setChecked(True)
    assert "a_" in group["label"].get_text()
    np.testing.assert_array_equal(original["line_y"], group["line"].get_ydata())
    w.show_acceleration.setChecked(False)
    assert "a_" not in group["label"].get_text()
    captured=[]
    monkeypatch.setattr("app.ui.research_tools.HelpTextDialog", lambda title,text,parent: SimpleNamespace(exec=lambda: captured.append(text)))
    w.show_fit_details()
    assert "Acceleration (native):" in captured[0] and "0.4" in captured[0]
    w.velocity_fit_mode.setCurrentIndex(w.velocity_fit_mode.findData("two"))
    assert w.show_acceleration.isHidden()
    w._apply_td_settings({"velocity_fit_mode":"acceleration"})
    assert w.velocity_fit_mode.currentData()=="ols" and w.show_acceleration.isChecked()


def test_three_point_acceleration_has_no_invented_error(research_window):
    w=research_window; result=make_td(w); c=w.td_canvas
    c.fit_mode="ols"; c.slope_velocity_unit="auto"
    xs=mdates.date2num(result.times[:3].utc.to_datetime())
    t=(xs-xs[0])*86400
    c.enable_slope_measurement(True); c._measure_points=list(zip(xs, 1+t+.1*t*t)); c._finish_measurement()
    group=c._measurement_groups[0]
    assert abs(group["acceleration"]-.2)<1e-8 and group["acceleration_stderr"] is None
    c.set_show_acceleration(True)
    assert "uncertainty unavailable" in group["label"].get_text()


def test_frame_label_text_dialog_and_layout(research_window):
    w=research_window; result=make_td(w)
    layout=w.slope_auto_colors.parentWidget().layout().itemAt(0).layout()
    assert layout.indexOf(w.velocity_fit_mode) < layout.indexOf(w.slope_auto_colors)
    assert layout.indexOf(w.slope_auto_colors)+2 == layout.indexOf(w.slope_selection)
    region=RegionGeometry.rectangle("R1", (9,9), 8,8)
    w.region_result=analyze_region_trends(w.dataset,[region],"mean"); w._redraw_region()
    for picker, canvas in ((w._td_frame_picker,w.td_canvas),(w._region_frame_picker,w.region_canvas)):
        picker.pick.setChecked(True)
        event=SimpleNamespace(inaxes=canvas.axes,button=1,xdata=mdates.date2num(result.times[1].utc.to_datetime()))
        picker._click(event)
        custom="\n".join(picker.default_text().splitlines()[1:])
        def accept_text():
            dialog=QApplication.activeModalWidget()
            dialog.findChild(QPlainTextEdit).setPlainText(custom)
            dialog.accept()
        QTimer.singleShot(0,accept_text); picker.edit_style()
        assert picker.artists[-1].get_text()==custom and "Frame" not in custom
        picker.apply_style(dict(fontsize=13)); canvas.draw()
        assert picker.artists[-1].get_text()==custom
        def cancel_text():
            dialog=QApplication.activeModalWidget()
            dialog.findChild(QPlainTextEdit).setPlainText("Discarded")
            dialog.reject()
        QTimer.singleShot(0,cancel_text); picker.edit_style()
        assert picker.custom_text==custom
        def restore_text():
            dialog=QApplication.activeModalWidget()
            next(b for b in dialog.findChildren(QPushButton) if b.text() in {"恢复默认文字", "Restore default text"}).click()
            dialog.accept()
        QTimer.singleShot(0,restore_text); picker.edit_style()
        assert picker.custom_text is None and "Frame" in picker.artists[-1].get_text()
        picker.custom_text="old time"; picker.pick.setChecked(True); picker._click(event)
        assert picker.custom_text is None
        picker.clear()


def test_frame_style_drag_clear_and_no_resurrection(research_window, monkeypatch):
    w=research_window; result=make_td(w)
    region=RegionGeometry.rectangle("R1", (9,9), 8,8)
    w.region_result=analyze_region_trends(w.dataset,[region],"mean"); w._redraw_region()
    for picker, canvas in ((w._td_frame_picker,w.td_canvas),(w._region_frame_picker,w.region_canvas)):
        canvas.draw()
        picker.pick.setChecked(True)
        picker._click(SimpleNamespace(inaxes=canvas.axes,button=1,xdata=mdates.date2num(result.times[1].utc.to_datetime())))
        canvas.draw()
        line,label=picker.artists
        px=canvas.axes.get_xaxis_transform().transform((line.get_xdata()[0], .95))[0]
        assert abs(canvas.axes.transAxes.transform(label.get_position())[0]-px-6)<1
        picker.apply_style(dict(line_color="red",text_color="blue",linewidth=3,fontsize=15))
        canvas.draw(); line,label=picker.artists
        assert line.get_color()=="red" and label.get_color()=="blue" and label.get_fontsize()==15
        box=label.get_window_extent(); x,y=box.x0+4,box.y0+box.height/2
        picker._click(MouseEvent("button_press_event",canvas,x,y,button=1))
        assert picker._drag_offset is not None
        picker._motion(MouseEvent("motion_notify_event",canvas,x+20,y-20,button=1))
        picker._release(None); position=picker.label_position
        assert position is not None
        picker.apply_style(dict(fontsize=17)); assert picker.artists[-1].get_position()==position
        called=[]; monkeypatch.setattr(picker,"edit_style",lambda:called.append(1))
        canvas.draw(); box=picker.artists[-1].get_window_extent()
        picker._click(MouseEvent("button_press_event",canvas,box.x0+4,box.y0+box.height/2,button=1,dblclick=True))
        assert called
        picker.clear(); canvas.draw(); picker._redraw(None)
        assert not picker.artists and picker.selected is None and not picker.jump.isEnabled()
