"""Explicit plot-to-image frame navigation; never changes scientific results."""
import numpy as np
import matplotlib.dates as mdates
from PySide6.QtWidgets import (QPushButton, QDialog, QDialogButtonBox, QFormLayout,
    QDoubleSpinBox, QComboBox, QColorDialog, QFontComboBox, QCheckBox, QPlainTextEdit)
from PySide6.QtGui import QColor, QFont
from app.i18n import tr


class PlotFramePicker:
    def __init__(self, window, canvas, toolbar, result_getter):
        self.window, self.canvas, self.get_result = window, canvas, result_getter
        self.selected = None
        self.result = None
        self.artists = []
        self.label_position = None
        self.custom_text = None
        self._drag_offset = None
        self.style = dict(line_color="#e06c24", text_color="#e06c24", linewidth=1.0,
                          linestyle="--", fontsize=9.0, fontfamily="DejaVu Sans",
                          background="white", transparent=True)
        self.pick = QPushButton(tr("在图上选帧", "Pick frame")); self.pick.setCheckable(True)
        self.jump = QPushButton(tr("查看对应图像", "Show frame image")); self.jump.setEnabled(False)
        self.pick.setToolTip(tr("时间曲线/TD：点击时间位置；直方图：点击确认当前显示帧。", "Trend/TD: click a time; histogram: click to select its displayed frame."))
        toolbar.addWidget(self.pick); toolbar.addWidget(self.jump)
        self.style_button = QPushButton(tr("帧标记样式", "Frame style"))
        self.clear_button = QPushButton(tr("清除帧标记", "Clear frame"))
        self.style_button.setEnabled(False); self.clear_button.setEnabled(False)
        toolbar.addWidget(self.style_button); toolbar.addWidget(self.clear_button)
        self.style_button.clicked.connect(self.edit_style)
        self.clear_button.clicked.connect(self.clear)
        self.pick.clicked.connect(self._activate)
        self.jump.clicked.connect(self._jump)
        canvas.mpl_connect("button_press_event", self._click)
        canvas.mpl_connect("draw_event", self._redraw)
        canvas.mpl_connect("motion_notify_event", self._motion)
        canvas.mpl_connect("button_release_event", self._release)

    def _activate(self, checked):
        if checked:
            toolbar = self.canvas.toolbar
            if toolbar and toolbar.mode:
                if "zoom" in str(toolbar.mode).lower():
                    toolbar.zoom()
                else:
                    toolbar.pan()
            if hasattr(self.canvas, "enable_slope_measurement"):
                self.canvas.enable_slope_measurement(False)

    def _remove(self):
        for artist in self.artists:
            try:
                artist.remove()
            except (ValueError, NotImplementedError):
                pass
        self.artists = []

    def _click(self, event):
        if getattr(self.canvas, "_measure_mode", False) or (self.canvas.toolbar and self.canvas.toolbar.mode):
            self.pick.setChecked(False)
            return
        result = self.get_result()
        if not self.pick.isChecked() and self.artists and event.button == 1:
            label = self.artists[-1]
            if label.contains(event)[0]:
                if getattr(event, "dblclick", False):
                    self._drag_offset = None
                    self.edit_style()
                else:
                    position = self.canvas.axes.transAxes.inverted().transform((event.x, event.y))
                    self._drag_offset = np.asarray(label.get_position()) - position
                return
        if not self.pick.isChecked() or result is None or event.inaxes is not self.canvas.axes or event.button != 1 or event.xdata is None:
            return
        if hasattr(result, "frame_index"):
            frame = int(result.frame_index)
        else:
            x = self._time_coordinates(result)
            frame = int(result.frame_indices[np.argmin(abs(x-event.xdata))])
        self._remove()
        self.label_position = None; self._drag_offset = None
        self.custom_text = None
        self.result = result; self.selected = frame
        self.pick.setChecked(False); self.jump.setEnabled(True)
        self.style_button.setEnabled(True); self.clear_button.setEnabled(True)
        self._redraw(None)

    def _time_coordinates(self, result):
        true_time = result.times is not None and getattr(self.canvas, "_true_time", True)
        return mdates.date2num(result.times.utc.to_datetime()) if true_time else np.asarray(result.frame_indices)

    def _redraw(self, _event):
        if self.result is not self.get_result():
            had_artists = bool(self.artists)
            self._remove(); self.selected = None; self.result = self.get_result()
            self.label_position = None; self._drag_offset = None
            self.custom_text = None
            self.style_button.setEnabled(False); self.clear_button.setEnabled(False)
            self.jump.setEnabled(False)
            if had_artists:
                self.canvas.draw_idle()
            return
        if self.selected is None:
            return
        if self.artists and self.artists[0].axes is self.canvas.axes:
            if self.label_position is None:
                position = self._default_position()
                if not np.allclose(position, self.artists[-1].get_position(), atol=1e-6):
                    self.artists[-1].set_position(position)
                    self.artists[-1].set_ha(self._label_align)
                    self.canvas.draw_idle()
            return
        self._remove()
        result = self.result
        self._label_align = getattr(self, "_label_align", "left")
        if not hasattr(result, "frame_index"):
            index = int(np.argmin(abs(result.frame_indices-self.selected)))
            self.artists.append(self.canvas.axes.axvline(self._time_coordinates(result)[index],
                color=self.style["line_color"], ls=self.style["linestyle"], lw=self.style["linewidth"]))
        text = self.default_text() if self.custom_text is None else self.custom_text
        self.artists.append(self.canvas.axes.text(*(self.label_position or self._default_position()), text,
            transform=self.canvas.axes.transAxes, va="top", fontsize=self.style["fontsize"],
            ha=self._label_align,
            clip_on=True, in_layout=False,
            fontfamily=self.style["fontfamily"], color=self.style["text_color"],
            bbox=dict(facecolor="none" if self.style["transparent"] else self.style["background"],
                      alpha=0 if self.style["transparent"] else .8, edgecolor="none")))
        self.canvas.draw_idle()

    def default_text(self) -> str:
        """Generate the selected frame's label without changing selection data."""
        if self.selected is None:
            return ""
        dataset = self.window.dataset
        timestamp = dataset.get_time(self.selected) if dataset is not None else None
        return f"Frame {self.selected+1}" + ("\n" + timestamp.utc.isot.replace("T", "\n") + " UTC" if timestamp is not None else "")

    def _default_position(self):
        """Anchor next to the selected time line; histogram has no time axis."""
        if self.result is None or hasattr(self.result, "frame_index"):
            return (.02, .95)
        index = int(np.argmin(abs(self.result.frame_indices-self.selected)))
        x = self._time_coordinates(self.result)[index]
        pixel = self.canvas.axes.get_xaxis_transform().transform((x, .95))
        fraction = self.canvas.axes.transAxes.inverted().transform(pixel)[0]
        self._label_align = "right" if fraction > .5 else "left"
        position = self.canvas.axes.transAxes.inverted().transform(pixel + ([-6, 0] if fraction > .5 else [6, 0]))
        return tuple(position)

    def _motion(self, event):
        if self._drag_offset is None or not self.artists or event.inaxes is not self.canvas.axes:
            return
        position = self.canvas.axes.transAxes.inverted().transform((event.x, event.y)) + self._drag_offset
        self.label_position = tuple(position)
        self.artists[-1].set_position(self.label_position)
        self.canvas.draw_idle()

    def _release(self, _event):
        self._drag_offset = None

    def clear(self):
        """Clear selection as well as its artists so redraw cannot revive it."""
        self._remove(); self.selected = None; self.label_position = None; self._drag_offset = None
        self.custom_text = None
        self.pick.setChecked(False); self.jump.setEnabled(False)
        self.style_button.setEnabled(False); self.clear_button.setEnabled(False)
        self.canvas.draw_idle()

    def apply_style(self, style):
        self.style.update(style)
        self._remove(); self._redraw(None)

    def edit_style(self):
        if self.selected is None:
            return
        dialog = QDialog(self.window); dialog.setWindowTitle(tr("帧标记样式", "Frame marker style"))
        form = QFormLayout(dialog); colors = {}
        text_editor = QPlainTextEdit(self.default_text() if self.custom_text is None else self.custom_text)
        text_editor.setMaximumHeight(100)
        form.addRow(tr("标记文字（可换行）", "Label text (multiline)"), text_editor)
        restore = QPushButton(tr("恢复默认文字", "Restore default text"))
        restore.clicked.connect(lambda: text_editor.setPlainText(self.default_text()))
        form.addRow(restore)
        for key, title in (("line_color", tr("线条颜色", "Line color")),
                           ("text_color", tr("文字颜色", "Text color")),
                           ("background", tr("文字背景", "Text background"))):
            button = QPushButton(self.style[key]); colors[key] = button
            def choose(_checked=False, button=button):
                color = QColorDialog.getColor(QColor(button.text()), dialog)
                if color.isValid(): button.setText(color.name())
            button.clicked.connect(choose); form.addRow(title, button)
        width = QDoubleSpinBox(); width.setRange(.1, 20); width.setValue(self.style["linewidth"])
        size = QDoubleSpinBox(); size.setRange(4, 72); size.setValue(self.style["fontsize"])
        line = QComboBox(); line.addItems(["--", "-", ":", "-."]); line.setCurrentText(self.style["linestyle"])
        font = QFontComboBox(); font.setCurrentFont(QFont(self.style["fontfamily"]))
        transparent = QCheckBox(tr("透明背景", "Transparent background")); transparent.setChecked(self.style["transparent"])
        form.addRow(tr("线宽", "Line width"), width); form.addRow(tr("线型", "Line style"), line)
        form.addRow(tr("字号", "Font size"), size); form.addRow(tr("字体", "Font family"), font)
        form.addRow(transparent)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject); form.addRow(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            text = text_editor.toPlainText()
            self.custom_text = None if text == self.default_text() else text
            self.apply_style({**{k: b.text() for k, b in colors.items()}, "linewidth": width.value(),
                "fontsize": size.value(), "linestyle": line.currentText(),
                "fontfamily": font.currentFont().family(), "transparent": transparent.isChecked()})

    def _jump(self):
        if self.selected is None or self.result is not self.get_result() or self.window.dataset is None:
            return
        self.window.set_current_frame(self.selected)
        self.window.main_tabs.setCurrentIndex(0)
