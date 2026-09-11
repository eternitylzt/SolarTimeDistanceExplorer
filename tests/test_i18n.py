from __future__ import annotations

import re

from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QComboBox,
    QGroupBox,
    QLabel,
    QMenu,
    QMessageBox,
)

from app.i18n import LanguageEventFilter, set_language, translate_text
from app.ui.dialogs import HistogramAnimationExportDialog
from app.ui.main_window import MainWindow


def _has_chinese(value: str) -> bool:
    return bool(re.search(r"[\u3400-\u9fff]", value))


def test_english_mode_translates_all_static_main_window_controls() -> None:
    app = QApplication.instance() or QApplication([])
    set_language("en")
    window = MainWindow()
    language_filter = LanguageEventFilter()
    language_filter.localize(window)
    remaining: list[str] = []
    for obj in [window, *window.findChildren(object)]:
        if isinstance(obj, (QLabel, QAbstractButton, QAction)) and _has_chinese(obj.text()):
            remaining.append(obj.text())
        if isinstance(obj, (QGroupBox, QMenu)) and _has_chinese(obj.title()):
            remaining.append(obj.title())
        if isinstance(obj, QComboBox):
            remaining.extend(obj.itemText(i) for i in range(obj.count()) if _has_chinese(obj.itemText(i)))
    assert remaining == []
    assert window.language_en_action.isChecked()
    assert window.menuBar().actions()[0].text().startswith("File")
    window.close(); app.processEvents(); set_language("zh")


def test_dynamic_english_status_translation() -> None:
    set_language("en")
    translated = translate_text("已生成并缓存 25 帧区域直方图序列。")
    assert translated == "Generated and cached 25 histogram frames."
    assert translate_text("请先生成帧范围直方图序列。") == "Build a frame-range histogram sequence first."
    set_language("zh")


def test_language_choice_is_saved_and_deferred_when_restart_is_declined(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    set_language("zh")
    window = MainWindow()
    values: dict[str, object] = {}

    class Settings:
        def setValue(self, key: str, value: object) -> None:  # noqa: N802
            values[key] = value

        def sync(self) -> None:
            values["synced"] = True

    window.settings = Settings()  # type: ignore[assignment]
    monkeypatch.setattr(QMessageBox, "question", lambda *_args, **_kwargs: QMessageBox.StandardButton.No)
    window._change_language("en")
    assert values == {"language": "en", "synced": True}
    assert window.language_zh_action.isChecked()
    window.close(); app.processEvents()


def test_histogram_movie_dialog_exposes_full_export_controls() -> None:
    app = QApplication.instance() or QApplication([])
    dialog = HistogramAnimationExportDialog(8.0, 20, (900, 600))
    dialog.start_frame.setValue(3); dialog.end_frame.setValue(17); dialog.frame_step.setValue(2)
    dialog.include_axes.setChecked(False); dialog.include_legend.setChecked(False)
    settings = dialog.settings()
    assert settings["output_size"] == (900, 600)
    assert settings["start"] == 2 and settings["end"] == 16 and settings["step"] == 2
    assert settings["fps"] == 8.0
    assert settings["view_range"] == "current"
    assert settings["include_axes"] is False and settings["include_legend"] is False
    dialog.close(); app.processEvents()
