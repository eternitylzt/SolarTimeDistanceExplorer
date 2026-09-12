"""Regressions for abandoned marker names, isolated history and manual updates."""

from types import SimpleNamespace
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from time import monotonic

import numpy as np
import pytest
from astropy.io import fits
from matplotlib.backend_bases import MouseButton
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest

from app.data.fits_image import FitsImageDataset
from app.processing.td_generator import TDResult
from app.ui.main_window import MainWindow
from app.utils.updates import RELEASES_URL, parse_release, version_tuple


def make_window(tmp_path):
    app = QApplication.instance() or QApplication([])
    target = tmp_path / "image.fits"
    fits.writeto(target, np.arange(400, dtype=float).reshape(20, 20))
    window = MainWindow()
    window._install_dataset(FitsImageDataset(target))
    return app, window


def click(window, x, y):
    window.image_canvas.mouse_pressed.emit(SimpleNamespace(
        button=MouseButton.LEFT, xdata=x, ydata=y, dblclick=False,
    ))


def test_unused_names_survive_shape_changes_and_tab_switches(tmp_path):
    app, window = make_window(tmp_path)
    window.new_path("line")
    original_id = window.active_path_id
    for shape in ("smooth", "polyline", "line"):
        window.new_path(shape)
        app.processEvents()
        assert window.active_path_id == original_id
        assert [p.name for p in window.paths] == ["S1"]
        assert window.path_editor.drawing
    click(window, 2, 2); click(window, 12, 10)
    window.new_path("line")
    assert window.active_path().name == "S2"
    window.new_region("circle")
    original_region_id = window.active_region_id
    for shape in ("rectangle", "polygon", "circle"):
        window.new_region(shape)
        app.processEvents()
        assert window.active_region_id == original_region_id
        assert [r.name for r in window.regions] == ["R1"]
        assert window.region_editor.drawing
    click(window, 8, 8); click(window, 10, 8)
    window.new_region("polygon")
    assert window.active_region().name == "R2"
    window.new_path("polyline")
    assert window.active_path().name == "S2"
    assert window.path_editor.drawing
    window.close(); app.processEvents()


def test_deleted_slit_history_retains_td_and_does_not_touch_latest_drawing(tmp_path):
    app, window = make_window(tmp_path)
    products = []
    for number in range(1, 4):
        window.new_path("line")
        click(window, 2, number); click(window, 12, number)
        path = window.active_path()
        result = TDResult(np.full((4, 3), number, dtype=float), None, np.arange(3),
                          np.arange(4), "pixel", path.id, {"path": path.to_dict()})
        window._td_finished(result)
        products.append((result, window._history_entries[0]))
    window.delete_active_path()
    window.new_path("polyline")
    click(window, 3, 4)
    draft = window.active_path()
    state = (window.current_frame, window.main_tabs.currentIndex(), window.left_tabs.currentIndex())
    latest = window.td_result
    for result, entry in products:
        window._open_history_entry(entry["id"])
        app.processEvents()
        assert window._history_viewer.result is result
        assert window._history_viewer.canvas.result is result
        assert window.td_result is latest
        assert window.active_path() is draft
        assert window.path_editor.drawing and window.path_editor.geometry is draft
        assert state == (window.current_frame, window.main_tabs.currentIndex(), window.left_tabs.currentIndex())
        assert window._history_marker_match(entry)[0] == (result is not products[2][0])
        window._history_viewer.close()
    # Reusing the deleted label cannot make a different UUID match the old result.
    draft.name = "S3"
    assert not window._history_marker_match(products[2][1])[0]
    click(window, 8, 9)
    assert draft.control_count == 2
    window.paths[0].width += 1
    assert not window._history_marker_match(products[0][1])[0]
    window.close(); app.processEvents()


def test_update_versions_and_release_validation():
    info = parse_release(json.dumps({"tag_name": "v1.10.0", "html_url": f"{RELEASES_URL}/tag/v1.10.0"}).encode())
    assert info.is_newer_than("1.9.0")
    assert not info.is_newer_than("1.10.0")
    assert version_tuple("v1.0") == version_tuple("1.0.0")
    for payload in (b"offline", b"[]", b"{}", json.dumps({"tag_name":"v2.0.0", "html_url":"https://example.com"}).encode()):
        with pytest.raises(ValueError):
            parse_release(payload)


@pytest.mark.parametrize("tag,status,newer,error", [
    ("v99.0.0", 200, True, False),
    ("v1.0.0", 200, False, False),
    ("v1.0.0", 503, False, True),
])
def test_manual_update_dialog_new_current_and_network_error(monkeypatch, tag, status, newer, error):
    """Use a local HTTP endpoint to exercise actual async Qt network completion."""
    from app.ui import update_dialog
    from app.i18n import set_language

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            payload = json.dumps({"tag_name": tag, "html_url": f"{RELEASES_URL}/tag/{tag}"}).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    app = QApplication.instance() or QApplication([])
    set_language("en")
    monkeypatch.setattr(update_dialog, "LATEST_RELEASE_API", f"http://127.0.0.1:{server.server_port}/latest")
    dialog = update_dialog.UpdateDialog()
    try:
        deadline = monotonic() + 4
        while dialog._timeout.isActive() and monotonic() < deadline:
            QTest.qWait(20)
        assert not dialog._timeout.isActive()
        assert dialog.download.isHidden() is not newer
        if error:
            assert "Network error" in dialog.message.text()
        elif newer:
            assert tag in dialog.message.text()
        else:
            assert "up to date" in dialog.message.text()
    finally:
        dialog.reject(); dialog.deleteLater(); app.processEvents()
        server.shutdown(); server.server_close(); thread.join(2)
        set_language("zh")
