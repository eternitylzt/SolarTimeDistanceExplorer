"""True-time Matplotlib time-distance canvas and slope measurement."""

from __future__ import annotations

from typing import Any

import matplotlib.dates as mdates
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.text import Text
from PySide6.QtCore import Signal, Qt

from app.plotting.normalization import make_norm
from app.processing.td_generator import TDResult
from app.processing.time_edges import centers_to_edges
from app.utils.units import convert_distance_value


SLOPE_COLORS = ("#ffcc33", "#00d4ff", "#ff5c8a", "#66e36f", "#b388ff", "#ff8c42")


class TimeDistanceCanvas(FigureCanvasQTAgg):
    """Publication-quality TD renderer using real timestamp bin widths."""

    slope_measured = Signal(str)
    measurements_changed = Signal()
    measurement_selected = Signal(int)

    def __init__(self) -> None:
        self.figure = Figure(figsize=(8, 7), layout="constrained")
        super().__init__(self.figure)
        self.axes = self.figure.add_subplot(111)
        self.result: TDResult | None = None
        self._measure_mode = False
        self._measure_points: list[tuple[float, float]] = []
        self._measurement_artists: list[Any] = []
        self._measurement_groups: list[dict[str, Any]] = []
        self._pending_artists: list[Any] = []
        self._pending_color: str | None = None
        self._selected_measurement_index = 0
        self._drag_label_group: dict[str, Any] | None = None
        self.slope_color = "#ffffff"
        self.slope_linewidth = 1.5
        self.slope_linestyle = "-"
        self.slope_fontsize = 10.0
        self.slope_text_color = "#ffffff"
        self.slope_background_color = "#000000"
        self.slope_velocity_unit = "km"
        self.slope_auto_colors = True
        self.slope_precision = 1
        self._true_time = True
        self._include_start_time = False
        self._base_x_label = "Observation Time [UTC]"
        self.mpl_connect("button_press_event", self._on_press)
        self.mpl_connect("motion_notify_event", self._on_motion)
        self.mpl_connect("button_release_event", self._on_release)

    def show_result(
        self,
        result: TDResult,
        cmap: str = "viridis",
        normalization_mode: str = "percentile",
        stretch: str = "linear",
        true_time: bool = True,
        show_colorbar: bool = True,
        title: str = "Time–Distance Diagram",
        time_format: str = "%H:%M:%S",
        axis_label_size: float = 11.0,
        tick_label_size: float = 9.0,
        include_start_time: bool = False,
        x_label: str = "",
        y_label: str = "",
        grid: bool = False,
        aspect: str = "auto",
        vmin: float | None = None,
        vmax: float | None = None,
        low_percent: float = 1.0,
        high_percent: float = 99.0,
    ) -> None:
        """Render distance by time without making irregular cadence uniform."""
        self.result = result
        self._true_time = bool(true_time and result.times is not None)
        self._include_start_time = bool(include_start_time)
        self.figure.clear()
        self.axes = self.figure.add_subplot(111)
        distance_edges = centers_to_edges(result.distance)
        if true_time and result.times is not None:
            time_centers = mdates.date2num(result.times.to_datetime())
            time_edges = centers_to_edges(time_centers)
            default_x_label = "Observation Time [UTC]"
        else:
            time_edges = centers_to_edges(result.frame_indices.astype(float))
            default_x_label = "Frame Index"
        norm = make_norm(
            result.matrix,
            mode=normalization_mode,
            stretch=stretch,
            vmin=vmin,
            vmax=vmax,
            low_percent=low_percent,
            high_percent=high_percent,
        )
        mesh = self.axes.pcolormesh(
            time_edges,
            distance_edges,
            result.matrix,
            cmap=cmap,
            norm=norm,
            shading="flat",
            rasterized=True,
        )
        self.axes.set_title(title)
        self._base_x_label = x_label.strip() or default_x_label
        self.axes.set_xlabel(self._base_x_label, fontsize=axis_label_size)
        self.axes.set_ylabel(
            y_label.strip() or f"Distance Along Slit [{result.distance_unit}]",
            fontsize=axis_label_size,
        )
        if true_time and result.times is not None:
            self.axes.xaxis_date()
            locator = mdates.AutoDateLocator(minticks=3, maxticks=9, interval_multiples=True)
            self.axes.xaxis.set_major_locator(locator)
            self.axes.xaxis.set_major_formatter(mdates.DateFormatter(time_format, tz="UTC"))
        if show_colorbar:
            colorbar = self.figure.colorbar(mesh, ax=self.axes, pad=0.02)
            colorbar.set_label("Intensity")
            colorbar.ax.tick_params(labelsize=tick_label_size)
        if grid:
            self.axes.grid(True, alpha=0.25)
        else:
            self.axes.grid(False)
        self.axes.set_aspect(aspect)
        self.axes.tick_params(axis="both", which="both", labelsize=tick_label_size)
        self.axes.minorticks_on()
        self._measurement_artists.clear()
        self._measurement_groups.clear()
        self._pending_artists.clear()
        self._pending_color = None
        self._measure_points.clear()
        self._selected_measurement_index = 0
        self._drag_label_group = None
        self.measurements_changed.emit()
        if self._true_time:
            self.axes.callbacks.connect("xlim_changed", self._time_xlim_changed)
            self._update_time_xlabel()
        self.draw_idle()

    def _time_xlim_changed(self, _axes: Any) -> None:
        """Keep the optional Start timestamp synchronized with interactive zoom/pan."""
        self._update_time_xlabel()
        self.draw_idle()

    def _update_time_xlabel(self) -> None:
        label = self._base_x_label
        if self._include_start_time and self._true_time:
            left = min(self.axes.get_xlim())
            timestamp = mdates.num2date(left, tz=mdates.UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")
            label += f" (Start: {timestamp[:-3]})"
        self.axes.set_xlabel(label)

    def enable_slope_measurement(self, enabled: bool) -> None:
        """Enter two-click slope mode while leaving the TD image unchanged."""
        if self._measure_points:
            for artist in self._pending_artists:
                try:
                    artist.remove()
                except (ValueError, AttributeError):
                    pass
                if artist in self._measurement_artists:
                    self._measurement_artists.remove(artist)
            self._pending_artists.clear()
            self._pending_color = None
        self._measure_mode = enabled
        self._measure_points.clear()
        if enabled:
            self.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.unsetCursor()

    def set_slope_style(
        self,
        color: str,
        linewidth: float,
        fontsize: float,
        linestyle: str = "-",
        text_color: str | None = None,
        precision: int = 1,
        background_color: str = "#000000",
        velocity_unit: str = "auto",
        auto_colors: bool = True,
    ) -> None:
        self.slope_color = color
        self.slope_linewidth = linewidth
        self.slope_fontsize = fontsize
        self.slope_linestyle = linestyle
        self.slope_text_color = text_color or color
        self.slope_background_color = background_color
        self.slope_velocity_unit = velocity_unit
        self.slope_auto_colors = auto_colors
        self.slope_precision = max(0, int(precision))
        for group in self._measurement_groups:
            self._style_measurement_group(group)
        pending_color = self._measurement_color(len(self._measurement_groups) + 1)
        for artist in self._pending_artists:
            if isinstance(artist, Line2D):
                artist.set_color(pending_color)
        self.draw_idle()

    def _measurement_color(self, index: int) -> str:
        return SLOPE_COLORS[(index - 1) % len(SLOPE_COLORS)] if self.slope_auto_colors else self.slope_color

    def _style_measurement_group(self, group: dict[str, Any]) -> None:
        if self.slope_auto_colors:
            color = self._measurement_color(int(group["index"]))
            group["line_color"] = color
            group["text_color"] = color
        color = str(group.get("line_color", self.slope_color))
        text_color = str(group.get("text_color", color))
        background_color = str(group.get("background_color", self.slope_background_color))
        for artist in group["artists"]:
            if isinstance(artist, Text):
                artist.set_color(text_color)
                artist.set_fontsize(self.slope_fontsize)
                artist.set_text(self._velocity_text(group["delta_s"], group["delta_t"], group["index"]))
                patch = artist.get_bbox_patch()
                if patch is not None:
                    transparent = background_color.lower() == "transparent"
                    patch.set_facecolor("none" if transparent else background_color)
                    patch.set_alpha(0.0 if transparent else 0.55)
                    patch.set_edgecolor(color)
            elif isinstance(artist, Line2D):
                artist.set_color(color)
                artist.set_linewidth(self.slope_linewidth)
                artist.set_linestyle(self.slope_linestyle)

    @property
    def measurement_count(self) -> int:
        return len(self._measurement_groups)

    def measurement_style(self, index: int) -> tuple[str, str, str] | None:
        """Return line, text and background colours for one marker or defaults."""
        if index == 0:
            return self.slope_color, self.slope_text_color, self.slope_background_color
        if index == -1:
            group = self._measurement_groups[0] if self._measurement_groups else None
        else:
            group = next(
                (item for item in self._measurement_groups if item["index"] == index), None
            )
        if group is None:
            return None
        return (
            str(group["line_color"]),
            str(group["text_color"]),
            str(group.get("background_color", self.slope_background_color)),
        )

    def measurement_colors(self, index: int) -> tuple[str, str] | None:
        """Compatibility accessor for the line/text colour pair."""
        style = self.measurement_style(index)
        return None if style is None else style[:2]

    def select_measurement(self, index: int) -> None:
        """Select a completed velocity marker for per-marker styling."""
        valid = (index == -1 and bool(self._measurement_groups)) or any(
            item["index"] == index for item in self._measurement_groups
        )
        self._selected_measurement_index = index if valid else 0
        self.measurement_selected.emit(self._selected_measurement_index)

    def set_measurement_style(
        self,
        index: int,
        *,
        line_color: str | None = None,
        text_color: str | None = None,
        background_color: str | None = None,
    ) -> None:
        """Change one velocity marker, or all markers when ``index == -1``."""
        groups = (
            list(self._measurement_groups)
            if index == -1
            else [item for item in self._measurement_groups if item["index"] == index]
        )
        if not groups:
            return
        for group in groups:
            if line_color is not None:
                group["line_color"] = line_color
            if text_color is not None:
                group["text_color"] = text_color
            if background_color is not None:
                group["background_color"] = background_color
            self._style_measurement_group(group)
        self.draw_idle()

    def set_measurement_colors(
        self, index: int, *, line_color: str | None = None, text_color: str | None = None
    ) -> None:
        """Compatibility wrapper for callers that only change line/text colours."""
        self.set_measurement_style(index, line_color=line_color, text_color=text_color)

    def clear_measurements(self) -> None:
        """Reliably remove all tagged slope artists from every current axes."""
        candidates: list[Any] = list(self._measurement_artists)
        for axes in self.figure.axes:
            candidates.extend(
                artist for artist in axes.get_children()
                if getattr(artist, "get_gid", lambda: None)() == "slope_measurement"
            )
        seen: set[int] = set()
        for artist in candidates:
            if id(artist) in seen:
                continue
            seen.add(id(artist))
            try:
                artist.remove()
            except (ValueError, AttributeError, NotImplementedError):
                pass
        self._measurement_artists.clear()
        self._measurement_groups.clear()
        self._pending_artists.clear()
        self._pending_color = None
        self._measure_points.clear()
        self._measure_mode = False
        self._selected_measurement_index = 0
        self._drag_label_group = None
        self.unsetCursor()
        self.draw_idle()
        self.measurements_changed.emit()

    def _on_press(self, event: Any) -> None:
        if self.result is None or event.inaxes is not self.axes:
            return
        if event.xdata is None or event.ydata is None:
            return
        if not self._measure_mode:
            for group in reversed(self._measurement_groups):
                label = group.get("label")
                line = group.get("line")
                if isinstance(label, Text) and label.contains(event)[0]:
                    self._drag_label_group = group
                    self.select_measurement(int(group["index"]))
                    return
                if isinstance(line, Line2D) and line.contains(event)[0]:
                    self.select_measurement(int(group["index"]))
                    return
            return
        self._measure_points.append((float(event.xdata), float(event.ydata)))
        measurement_index = len(self._measurement_groups) + 1
        color = self._pending_color or self._measurement_color(measurement_index)
        self._pending_color = color
        if len(self._measure_points) < 2:
            self.draw_idle()
            return
        (t1, s1), (t2, s2) = self._measure_points
        lines = self.axes.plot(
            [t1, t2], [s1, s2], color=color,
            linewidth=self.slope_linewidth, linestyle=self.slope_linestyle,
        )
        for artist in lines:
            artist.set_gid("slope_measurement")
        self._measurement_artists.extend(lines)
        delta_t = abs((t2 - t1) * 86400.0) if self._true_time else abs(t2 - t1)
        delta_s = s2 - s1
        velocity = self._velocity_text(delta_s, delta_t, measurement_index)
        text_color = color if self.slope_auto_colors else self.slope_text_color
        transparent = self.slope_background_color.lower() == "transparent"
        label = self.axes.text(
            (t1 + t2) / 2.0,
            (s1 + s2) / 2.0,
            velocity,
            color=text_color, fontsize=self.slope_fontsize,
            bbox={
                "facecolor": "none" if transparent else self.slope_background_color,
                "alpha": 0.0 if transparent else 0.55,
                "edgecolor": color, "pad": 2,
            },
        )
        label.set_gid("slope_measurement")
        self._measurement_artists.append(label)
        group = {
            "index": measurement_index,
            "delta_s": delta_s,
            "delta_t": delta_t,
            "line_color": color,
            "text_color": text_color,
            "background_color": self.slope_background_color,
            "line": lines[0],
            "label": label,
            "artists": [*lines, label],
        }
        self._measurement_groups.append(group)
        self._selected_measurement_index = measurement_index
        plain_velocity = velocity.replace("$", "").replace("{", "").replace("}", "")
        time_unit = "s" if self._true_time else "frame"
        self.slope_measured.emit(
            f"Δt = {delta_t:.3g} {time_unit}; Δs = {delta_s:.4g} "
            f"{self.result.distance_unit}; {plain_velocity}"
        )
        self._measure_mode = False
        self._measure_points.clear()
        self._pending_artists = []
        self._pending_color = None
        self.draw_idle()
        self.measurements_changed.emit()
        self.measurement_selected.emit(measurement_index)

    def _on_motion(self, event: Any) -> None:
        if self._drag_label_group is None or event.inaxes is not self.axes:
            return
        if event.xdata is None or event.ydata is None:
            return
        label = self._drag_label_group.get("label")
        if isinstance(label, Text):
            label.set_position((float(event.xdata), float(event.ydata)))
            self.draw_idle()

    def _on_release(self, _event: Any) -> None:
        self._drag_label_group = None

    def _velocity_text(self, delta_s: float, delta_t: float, index: int = 1) -> str:
        if delta_t == 0:
            return rf"$v_{{{index}}}$ = undefined"
        assert self.result is not None
        source_unit = self.result.distance_unit
        unit = source_unit if self.slope_velocity_unit == "auto" else self.slope_velocity_unit
        precision = self.slope_precision
        try:
            converted = convert_distance_value(
                delta_s,
                source_unit,
                unit,
                pixel_scale_arcsec_value=self.result.metadata.get("reference_pixel_scale_arcsec"),
            )
        except ValueError:
            return rf"$v_{{{index}}}$ = unavailable"
        denominator = "s" if self._true_time else "frame"
        return rf"$v_{{{index}}}$ = {converted / delta_t:.{precision}f} {unit}/{denominator}"
