from __future__ import annotations

from types import SimpleNamespace

import numpy as np
from astropy.io import fits
from matplotlib.backend_bases import MouseButton
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from app.data.fits_image import FitsImageDataset
from app.paths.base import PathGeometry
from app.data.sav_cube import is_ssw_map_structure
from app.ui.main_window import MainWindow
from app.ui.image_plot import ImageCanvas
from app.utils.units import distance_along_path
from tests.data_generator import _header
from astropy.time import Time


def _single_image(tmp_path):
    target = tmp_path / "single.fits"
    fits.PrimaryHDU(np.arange(64, dtype=np.float32).reshape(8, 8), header=_header(Time("2026-01-01"))).writeto(target)
    return target


def test_single_fits_preview_has_hpc_map_and_arcsec_distance(tmp_path) -> None:
    dataset = FitsImageDataset(_single_image(tmp_path))
    smap = dataset.get_map(0)
    assert smap is not None
    assert smap.coordinate_frame.name == "helioprojective"
    samples = np.array([[2.0, 4.0], [12.0, 4.0]])
    distance = distance_along_path(samples, "arcsec", dataset.get_wcs(0))
    assert np.isclose(distance[-1], 6.0, atol=1e-3)

    app = QApplication.instance() or QApplication([])
    canvas = ImageCanvas()
    canvas.show_frame(dataset.get_frame(0), dataset.get_wcs(0), "WCS 1", solar_map=smap)
    axes_id = id(canvas.axes)
    canvas.show_frame(dataset.get_frame(0) + 1, dataset.get_wcs(0), "WCS 2", solar_map=smap)
    assert id(canvas.axes) == axes_id
    canvas.close()
    app.processEvents()


def test_new_line_remains_in_drawing_mode_and_accepts_two_clicks(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window._install_dataset(FitsImageDataset(_single_image(tmp_path)))
    assert window.path_panel.coordinate_mode.currentData() == "world"
    assert window.path_panel.tracking.currentData() == "world_fixed"
    assert window.path_panel.width_unit.currentText() == "arcsec"
    assert window.path_panel.distance_unit.currentText() == "arcsec"
    assert window.path_panel.normalize_exposure.isChecked()
    window.path_panel.path_type.setCurrentText("line")
    window.new_path()
    assert window.path_editor.drawing
    window.path_editor._press(SimpleNamespace(button=MouseButton.LEFT, xdata=1.0, ydata=2.0, dblclick=False))
    window.path_editor._press(SimpleNamespace(button=MouseButton.LEFT, xdata=6.0, ydata=5.0, dblclick=False))
    assert window.active_path() is not None
    assert window.active_path().complete
    assert not window.path_editor.drawing
    window.close()
    app.processEvents()


def test_standard_ssw_map_tags_are_recognized() -> None:
    value = np.zeros(
        1,
        dtype=[("DATA", object), ("XC", "f8"), ("YC", "f8"), ("DX", "f8"), ("DY", "f8")],
    )
    value["DATA"][0] = np.ones((4, 4))
    assert is_ssw_map_structure(value)


def test_large_preview_is_decimated_and_axes_are_reused() -> None:
    app = QApplication.instance() or QApplication([])
    canvas = ImageCanvas()
    first = np.zeros((1800, 2000), dtype=np.float32)
    canvas.show_frame(first, None, "Frame 1")
    axes_id = id(canvas.axes)
    assert canvas.frame is first
    assert canvas.frame.dtype == np.float32
    assert max(canvas._preview_data.shape) <= 1600
    assert tuple(canvas._image_artist.get_extent()) == (-0.5, 1999.5, -0.5, 1799.5)

    canvas.axes.set_xlim(200.0, 800.0)
    canvas.axes.set_ylim(300.0, 900.0)
    canvas.show_frame(np.ones_like(first), None, "Frame 2")
    assert id(canvas.axes) == axes_id
    assert float(np.asarray(canvas._image_artist.get_array())[0, 0]) == 1.0
    assert np.allclose(canvas.axes.get_xlim(), (200.0, 800.0))
    assert np.allclose(canvas.axes.get_ylim(), (300.0, 900.0))
    canvas.close()
    app.processEvents()


def test_shape_is_chosen_from_new_menu_and_right_click_finishes(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window._install_dataset(FitsImageDataset(_single_image(tmp_path)))
    assert not hasattr(window.image_panel, "play")
    assert not hasattr(window.path_panel, "finish")
    assert not hasattr(window.region_panel, "finish")

    # The menu choice belongs to this new slit, rather than silently changing
    # the type used by a later command.
    window.path_panel.new.menu().actions()[1].trigger()  # Polyline
    assert window.active_path() is not None
    assert window.active_path().path_type == "polyline"
    for x, y in ((1.0, 1.0), (3.0, 5.0), (6.0, 4.0)):
        window.path_editor._press(SimpleNamespace(button=MouseButton.LEFT, xdata=x, ydata=y, dblclick=False))
    window.path_editor._press(SimpleNamespace(button=MouseButton.RIGHT, xdata=6.0, ydata=4.0, dblclick=False))
    assert not window.path_editor.drawing

    window.region_panel.new.menu().actions()[2].trigger()  # Polygon
    assert window.active_region() is not None
    assert window.active_region().region_type == "polygon"
    for x, y in ((1.0, 1.0), (6.0, 1.0), (3.0, 6.0)):
        window.region_editor._press(SimpleNamespace(button=MouseButton.LEFT, xdata=x, ydata=y, dblclick=False))
    window.region_editor._press(SimpleNamespace(button=MouseButton.RIGHT, xdata=3.0, ydata=6.0, dblclick=False))
    assert not window.region_editor.drawing
    window.close(); app.processEvents()


def test_slit_editor_recovers_after_region_workflow_and_blank_click_deselects(tmp_path) -> None:
    """Regression: Region editing must not leave the shared canvas owned by RegionEditor."""
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window._install_dataset(FitsImageDataset(_single_image(tmp_path)))

    window.new_path("line")
    for x, y in ((1.0, 1.0), (6.0, 2.0)):
        window.path_editor._press(
            SimpleNamespace(button=MouseButton.LEFT, xdata=x, ydata=y, dblclick=False)
        )
    window.new_region("circle")
    for x, y in ((3.0, 3.0), (5.0, 3.0)):
        window.region_editor._press(
            SimpleNamespace(button=MouseButton.LEFT, xdata=x, ydata=y, dblclick=False)
        )

    window.new_path("polyline")
    assert window.left_tabs.currentIndex() == 2
    assert window.main_tabs.currentIndex() == 0
    assert window.path_editor.enabled and not window.region_editor.enabled
    assert window.path_editor.drawing
    for x, y in ((1.0, 6.0), (4.0, 5.0), (7.0, 7.0)):
        window.path_editor._press(
            SimpleNamespace(button=MouseButton.LEFT, xdata=x, ydata=y, dblclick=False)
        )
    window.path_editor._press(
        SimpleNamespace(button=MouseButton.RIGHT, xdata=7.0, ydata=7.0, dblclick=False)
    )
    assert window.active_path() is not None and window.active_path().complete
    window.path_editor._press(
        SimpleNamespace(button=MouseButton.LEFT, xdata=0.0, ydata=0.0, dblclick=False)
    )
    assert window.active_path_id is None
    assert window.image_canvas.current_path is None
    window.close(); app.processEvents()


def test_slit_delete_state_stays_atomic_then_new_slit_draws(tmp_path) -> None:
    """Regression: list, model, editor and canvas must share one selected Slit ID."""
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window._install_dataset(FitsImageDataset(_single_image(tmp_path)))

    for y in (2.0, 5.0):
        window.new_path("line")
        for x in (1.0, 6.0):
            window.path_editor._press(
                SimpleNamespace(button=MouseButton.LEFT, xdata=x, ydata=y, dblclick=False)
            )
    window.new_region("circle")
    for x, y in ((3.0, 3.0), (4.0, 3.0)):
        window.region_editor._press(
            SimpleNamespace(button=MouseButton.LEFT, xdata=x, ydata=y, dblclick=False)
        )
    window.main_tabs.setCurrentIndex(2)
    window.main_tabs.setCurrentIndex(0)
    window.left_tabs.setCurrentIndex(2)

    window.path_panel.paths.setCurrentRow(0)
    window.active_path_id = "stale-id"  # emulate the former post-delete Qt row state
    window.delete_active_path()
    assert len(window.paths) == window.path_panel.paths.count() == 1
    remaining_id = window.path_panel.paths.item(0).data(Qt.ItemDataRole.UserRole)
    assert remaining_id == window.paths[0].id == window.active_path_id
    assert window.path_editor.geometry is window.paths[0]

    window.delete_active_path()
    assert len(window.paths) == window.path_panel.paths.count() == 0
    assert window.active_path_id is None and window.path_editor.geometry is None

    window.new_path("polyline")
    assert window.path_editor.drawing
    assert window.path_panel.paths.item(0).data(Qt.ItemDataRole.UserRole) == window.active_path_id
    for x, y in ((1.0, 1.0), (3.0, 6.0), (7.0, 4.0)):
        window.path_editor._press(
            SimpleNamespace(button=MouseButton.LEFT, xdata=x, ydata=y, dblclick=False)
        )
    window.path_editor._press(
        SimpleNamespace(button=MouseButton.RIGHT, xdata=7.0, ydata=4.0, dblclick=False)
    )
    assert window.active_path() is not None and window.active_path().complete
    assert window.image_panel.speed.value() == 5.0
    window.image_panel.speed.setValue(12.5)
    assert window._timer.interval() == 80
    window.path_panel.label_background_transparent.setChecked(True)
    assert window.active_path().label_background_color == "transparent"
    window.close(); app.processEvents()


def test_slit_native_actions_delete_then_draw_unique_mixed_shapes(tmp_path) -> None:
    """Exercise the QAction/QList signal route that previously cancelled New Slit."""
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window._install_dataset(FitsImageDataset(_single_image(tmp_path)))
    actions = {action.text(): action for action in window.path_panel.new.menu().actions()}

    def canvas_press(x: float, y: float, button: MouseButton = MouseButton.LEFT) -> None:
        window.image_canvas.mouse_pressed.emit(
            SimpleNamespace(button=button, xdata=x, ydata=y, dblclick=False)
        )
        app.processEvents()

    actions["Line"].trigger(); app.processEvents()
    canvas_press(1.0, 1.0); canvas_press(7.0, 2.0)
    actions["Polyline"].trigger(); app.processEvents()
    canvas_press(1.0, 5.0); canvas_press(4.0, 6.0); canvas_press(7.0, 5.0)
    canvas_press(7.0, 5.0, MouseButton.RIGHT)
    assert [item.name for item in window.paths] == ["S1", "S2"]

    window.path_panel.paths.setCurrentRow(0)
    window.path_panel.delete.click(); app.processEvents()
    actions["Smooth Curve"].trigger(); app.processEvents()
    assert window.path_editor.drawing and window.path_editor.enabled
    assert window.active_path() is window.path_editor.geometry
    canvas_press(1.0, 3.0); canvas_press(4.0, 4.0); canvas_press(7.0, 3.0)
    canvas_press(7.0, 3.0, MouseButton.RIGHT)

    assert [item.name for item in window.paths] == ["S2", "S3"]
    assert len({item.name for item in window.paths}) == len(window.paths)
    assert window.paths[-1].path_type == "smooth" and window.paths[-1].complete
    assert window.path_panel.paths.count() == len(window.paths)
    window.close(); app.processEvents()


def test_renamed_replacement_slit_keeps_list_id_and_remains_deletable(tmp_path) -> None:
    """Regression: renaming S3 to a freed S2 must update one atomic list/model row."""
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window._install_dataset(FitsImageDataset(_single_image(tmp_path)))

    def finish_line(y: float) -> None:
        window.new_path("line")
        for x in (1.0, 7.0):
            window.image_canvas.mouse_pressed.emit(
                SimpleNamespace(button=MouseButton.LEFT, xdata=x, ydata=y, dblclick=False)
            )
            app.processEvents()

    finish_line(2.0)  # S1
    finish_line(4.0)  # S2
    window.path_panel.paths.setCurrentRow(1)
    window.path_panel.delete.click(); app.processEvents()
    finish_line(6.0)  # monotonic S3
    replacement = window.active_path()
    assert replacement is not None and replacement.name == "S3"

    window.path_panel.name.setText("S2")
    window.path_panel.name.editingFinished.emit(); app.processEvents()
    row = window._path_row(replacement.id)
    assert row == 1
    assert replacement.name == "S2"
    assert window.path_panel.paths.item(row).text() == "S2"
    assert window.path_panel.paths.item(row).data(Qt.ItemDataRole.UserRole) == replacement.id

    window.path_panel.delete.click(); app.processEvents()
    assert [item.name for item in window.paths] == ["S1"]
    assert window.path_panel.paths.count() == 1
    finish_line(7.0)
    assert [item.name for item in window.paths] == ["S1", "S4"]
    window.close(); app.processEvents()


def test_drawing_history_is_bounded_and_navigates_to_slit(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.history_limit = 3
    window._install_dataset(FitsImageDataset(_single_image(tmp_path)))
    window.new_path("line")
    for x, y in ((1.0, 1.0), (7.0, 2.0)):
        window.image_canvas.mouse_pressed.emit(
            SimpleNamespace(button=MouseButton.LEFT, xdata=x, ydata=y, dblclick=False)
        )
    slit_entry = next(item for item in window._history_entries if item["marker_kind"] == "slit")
    window._record_history("Extra 1", main_tab=2, left_tab=3)
    window._record_history("Extra 2", main_tab=1, left_tab=2)
    assert len(window._history_entries) == 3
    window._open_history_entry(slit_entry["id"])
    assert window.main_tabs.currentIndex() == 0
    assert window.left_tabs.currentIndex() == 2
    assert window.active_path_id == window.paths[0].id
    window.close(); app.processEvents()


def test_scientific_width_shadow_can_be_toggled() -> None:
    app = QApplication.instance() or QApplication([])
    canvas = ImageCanvas()
    canvas.show_frame(np.ones((20, 20)), None, "Image")
    slit = PathGeometry(
        "line", np.array([[2.0, 10.0], [17.0, 10.0]]), width=5.0,
        show_width_boundaries=True,
    )
    canvas.set_paths([slit], None)
    assert canvas.axes.patches
    slit.show_width_boundaries = False
    canvas.set_paths([slit], None)
    assert not canvas.axes.patches
    canvas.close(); app.processEvents()
