"""Qt process initialization and top-level error reporting."""

from __future__ import annotations

import sys
import os
from pathlib import Path

_pre_qt_marker = os.environ.get("STDE_SMOKE_MARKER")
if _pre_qt_marker:
    Path(_pre_qt_marker).write_text("bootstrap entered before Qt import", encoding="utf-8")

from PySide6.QtCore import QLibraryInfo, QTranslator
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from app.utils.logging import configure_logging


def _smoke_marker(stage: str) -> None:
    """Write a transient diagnostic marker only when packaging tests request it."""
    destination = os.environ.get("STDE_SMOKE_MARKER")
    if destination:
        Path(destination).write_text(stage, encoding="utf-8")


def _validate_export_backends() -> None:
    """Exercise frozen vector backends and the bundled playback-safe encoder."""
    from tempfile import TemporaryDirectory

    import numpy as np
    from matplotlib.figure import Figure
    import matplotlib.backends.backend_pdf  # noqa: F401
    import matplotlib.backends.backend_ps  # noqa: F401
    from PIL import Image

    from app.animation.exporter import _ffmpeg_executable, _run_ffmpeg, _verify_video

    with TemporaryDirectory(prefix="stde_export_smoke_") as directory:
        root = Path(directory)
        figure = Figure(figsize=(2, 2)); axes = figure.add_subplot(111); axes.plot([0, 1], [0, 1])
        figure.savefig(root / "figure.pdf")
        figure.savefig(root / "figure.eps")
        for index in range(2):
            frame = np.zeros((16, 16, 3), dtype=np.uint8)
            frame[4:12, 4:12, index] = 255
            Image.fromarray(frame).save(root / f"frame_{index:06d}.png", "PNG")
        ffmpeg = _ffmpeg_executable()
        _run_ffmpeg([
            str(ffmpeg), "-y", "-hide_banner", "-loglevel", "error", "-framerate", "2",
            "-i", str(root / "frame_%06d.png"), "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", str(root / "movie.mp4"),
        ])
        _verify_video(ffmpeg, root / "movie.mp4")
        _run_ffmpeg([
            str(ffmpeg), "-y", "-hide_banner", "-loglevel", "error", "-framerate", "2",
            "-i", str(root / "frame_%06d.png"), "-loop", "0", str(root / "movie.gif"),
        ])
        if not all((root / name).exists() for name in ("figure.pdf", "movie.gif", "movie.mp4")):
            raise RuntimeError("One or more export smoke artifacts were not created.")


def run() -> int:
    """Create and execute the Qt application with logging configured."""
    _smoke_marker("run entered")
    configure_logging()
    _smoke_marker("logging configured")
    app = QApplication(sys.argv)
    # The application has a single Chinese interface. Qt's translator also
    # localizes native standard buttons such as OK/Cancel where available.
    translator = QTranslator(app)
    translations = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    if translator.load("qtbase_zh_CN", translations) or translator.load("qt_zh_CN", translations):
        app.installTranslator(translator)
        app._stde_translator = translator  # type: ignore[attr-defined]
    _smoke_marker("QApplication created")
    app.setApplicationName("Solar Time–Distance Explorer")
    app.setOrganizationName("Solar Time-Distance Explorer")
    bundle_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    icon_path = bundle_root / "resources" / "stde_icon.png"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    import matplotlib

    matplotlib.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial Unicode MS", "DejaVu Sans"]
    matplotlib.rcParams["axes.unicode_minus"] = False
    try:
        from app.ui.main_window import MainWindow

        _smoke_marker("MainWindow imported")
        window = MainWindow()
        _smoke_marker("MainWindow constructed")
        if "--smoke-test" in sys.argv or os.environ.get("STDE_SMOKE_TEST") == "1":
            # PyInstaller's windowed bootloader can detach the process, which
            # makes timer-driven smoke tests unreliable. Constructing the main
            # window has already loaded the Qt/Matplotlib plugins we need to
            # validate; process pending events once, then exit deterministically.
            app.processEvents()
            if os.environ.get("STDE_SMOKE_EXPORTS") == "1":
                _validate_export_backends()
                _smoke_marker("export smoke succeeded")
            window.close()
            _smoke_marker("smoke succeeded")
            return 0
        window.show()
        _smoke_marker("window shown")
        return app.exec()
    except Exception as exc:  # pragma: no cover - only catastrophic startup faults
        QMessageBox.critical(None, "无法启动", f"程序无法启动。\n\n{exc}")
        raise
