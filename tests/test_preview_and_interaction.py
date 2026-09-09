from __future__ import annotations

from types import SimpleNamespace

import numpy as np
from astropy.io import fits
from matplotlib.backend_bases import MouseButton
from PySide6.QtWidgets import QApplication

from app.data.fits_image import FitsImageDataset
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
