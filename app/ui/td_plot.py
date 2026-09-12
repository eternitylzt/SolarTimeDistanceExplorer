"""True-time Matplotlib time-distance canvas and slope measurement."""

from __future__ import annotations

from typing import Any
import numpy as np

import matplotlib.dates as mdates
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.text import Text
from PySide6.QtCore import Signal, Qt

from app.plotting.normalization import make_norm
from app.processing.td_generator import TDResult
from app.processing.time_edges import centers_to_edges
from app.processing.time_edges import gap_aware_edges
from app.processing.velocity import fit_velocity, fit_motion
from matplotlib.collections import PolyCollection
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
        self.fit_mode = "two"
        self.show_acceleration = False
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
        self.mpl_connect("key_press_event", self._on_key)

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
        show_gaps: bool = False,
        gap_factor: float = 5.0,
    ) -> None:
        """Render distance by time without making irregular cadence uniform."""
        saved = self.measurement_snapshot() if self.result is result and self._true_time == bool(true_time and result.times is not None) else []
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
        rendered_matrix = result.matrix
        if show_gaps and self._true_time:
            time_edges, rendered_matrix = gap_aware_edges(time_centers, result.matrix, gap_factor)
        mesh = self.axes.pcolormesh(
            time_edges,
            distance_edges,
            rendered_matrix,
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
        # Time is stored in days, distance in arcsec: equal DATA aspect has no
        # physical meaning. These options constrain the physical plot box only.
        self.axes.set_aspect("auto")
        self.axes.set_box_aspect({"equal": 1.0, "wide": 0.6}.get(aspect))
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
        if saved:
            self.restore_measurements(saved)
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
                artist.set_fontsize(float(group.get("font_size", self.slope_fontsize)))
                artist.set_text(self._velocity_text(group["delta_s"], group["delta_t"], group["index"], group.get("stderr")))
                if group.get("acceleration") is not None and self.show_acceleration:
                    artist.set_text(artist.get_text() + "\n" + self._acceleration_text(group))
                patch = artist.get_bbox_patch()
                if patch is not None:
                    transparent = background_color.lower() == "transparent"
                    patch.set_facecolor("none" if transparent else background_color)
                    patch.set_alpha(0.0 if transparent else 0.55)
                    patch.set_edgecolor(color)
            elif isinstance(artist, Line2D):
                artist.set_color(color)
                artist.set_linewidth(self.slope_linewidth)
                artist.set_linestyle("None" if artist.get_marker() == "o" else self.slope_linestyle)
            elif isinstance(artist, PolyCollection):
                artist.set_facecolor(color)

    @property
    def measurement_count(self) -> int:
        return len(self._measurement_groups)

    def measurement_style(self, index: int) -> tuple[str, str, str, float] | None:
        """Return line/text/background colours and text size for one marker."""
        if index == 0:
            return (
                self.slope_color, self.slope_text_color,
                self.slope_background_color, self.slope_fontsize,
            )
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
            float(group.get("font_size", self.slope_fontsize)),
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
        font_size: float | None = None,
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
            if font_size is not None:
                group["font_size"] = float(font_size)
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
        button = getattr(event, "button", 1)
        if button == 3 or getattr(event, "dblclick", False):
            self._finish_measurement()
            return
        if button != 1:
            return
        self._measure_points.append((float(event.xdata), float(event.ydata)))
        if self.fit_mode != "two":
            for artist in self._pending_artists:
                artist.remove()
            points = np.asarray(self._measure_points)
            self._pending_artists = self.axes.plot(points[:, 0], points[:, 1], "o", color=self._measurement_color(self.measurement_count+1), markersize=4)
            self.draw_idle()
            return
        self._finish_measurement()

    def _on_key(self, event: Any) -> None:
        if event.key == "enter" and self._measure_mode:
            self._finish_measurement()
        elif event.key == "escape":
            self.enable_slope_measurement(False)
            self.draw_idle()

    def _finish_measurement(self) -> None:
        if len(self._measure_points) < 2:
            return
        if self.fit_mode == "segmented" and len(self._measure_points) > 2:
            points = list(self._measure_points)
            mode = self.fit_mode; self.fit_mode = "two"
            for first, second in zip(points[:-1], points[1:]):
                self._measure_points = [first, second]
                self._finish_measurement()
            self.fit_mode = mode
            return
        points = np.asarray(sorted(self._measure_points), dtype=float)
        if self._true_time:
            time = (points[:, 0]-points[0, 0])*86400.0
        elif self.result.times is not None:
            elapsed = (self.result.times-self.result.times[0]).to_value("s")
            time = np.interp(points[:, 0], self.result.frame_indices, elapsed)
        else:
            time = points[:, 0]
        try:
            fit = fit_velocity(time, points[:, 1])
            # Keep the velocity line linear. A separate quadratic estimates
            # full-interval acceleration regardless of label visibility.
            motion = fit_motion(time, points[:, 1], self.fit_mode == "acceleration") if self.fit_mode in {"ols", "acceleration"} else None
            acceleration_fit = None
            acceleration_reason = None
            if motion is not None:
                try:
                    acceleration_fit = fit_motion(time, points[:, 1], True, allow_exact=True)
                except ValueError as exc:
                    acceleration_reason = str(exc)
        except ValueError as exc:
            self.slope_measured.emit(str(exc))
            return
        for artist in self._pending_artists:
            artist.remove()
        self._pending_artists.clear()
        measurement_index = len(self._measurement_groups) + 1
        color = self._pending_color or self._measurement_color(measurement_index)
        self._pending_color = color
        t1, t2 = points[0, 0], points[-1, 0]
        line_x = np.interp(motion["time"], time, points[:, 0]) if motion is not None else points[:, 0]
        line_y = motion["fitted"] if motion is not None else fit.fitted
        s1, s2 = line_y[0], line_y[-1]
        lines = self.axes.plot(
            line_x, line_y, color=color,
            linewidth=self.slope_linewidth, linestyle=self.slope_linestyle,
        )
        for artist in lines:
            artist.set_gid("slope_measurement")
        self._measurement_artists.extend(lines)
        delta_t = float(time[-1]-time[0])
        delta_s = s2 - s1
        velocity = self._velocity_text(delta_s, delta_t, measurement_index,
            motion["velocity_stderr"] if motion is not None else fit.stderr)
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
            "font_size": self.slope_fontsize,
            "stderr": motion["velocity_stderr"] if motion is not None else fit.stderr,
            "points": points.tolist(),
            "residuals": (motion["residuals"] if motion is not None else fit.residuals).tolist(),
            "fit_method": "constant acceleration" if self.fit_mode == "acceleration" else ("OLS" if len(points)>2 else "two-point"),
            "time_basis": "UTC date days" if self._true_time else "frame index",
            "distance_unit": self.result.distance_unit,
            "slope_time_unit": "s" if self.result.times is not None else "frame",
            "line": lines[0],
            "label": label,
            "artists": [*lines, label],
        }
        if motion is not None:
            group.update(band_x=line_x.tolist(), band_low=(line_y-motion["sigma"]).tolist(),
                         band_high=(line_y+motion["sigma"]).tolist(), retain_points=True,
                         acceleration=motion["acceleration"], acceleration_stderr=motion["acceleration_stderr"],
                         reverses_direction=motion["reverses_direction"], band_definition="1-sigma fitted mean")
            self._add_fit_artists(group)
            if acceleration_fit is not None:
                group.update(acceleration=acceleration_fit["acceleration"],
                    acceleration_stderr=acceleration_fit["acceleration_stderr"],
                    acceleration_residuals=acceleration_fit["residuals"].tolist(),
                    reverses_direction=acceleration_fit["reverses_direction"])
            group["acceleration_reason"] = acceleration_reason
            self._style_measurement_group(group)
        self._measurement_groups.append(group)
        self._selected_measurement_index = measurement_index
        plain_velocity = label.get_text().replace("$", "").replace("{", "").replace("}", "")
        time_unit = "s" if self.result.times is not None else "frame"
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

    def measurement_snapshot(self) -> list[dict[str, Any]]:
        """Serialize data, residuals, styles and draggable labels, never artists."""
        result = []
        for group in self._measurement_groups:
            snapshot = {k: v for k, v in group.items() if k not in {"line", "label", "artists"}}
            snapshot["line_x"] = list(group["line"].get_xdata())
            snapshot["line_y"] = list(group["line"].get_ydata())
            snapshot["label_position"] = list(group["label"].get_position())
            result.append(snapshot)
        return result

    def restore_measurements(self, snapshots: list[dict[str, Any]]) -> None:
        self.clear_measurements()
        for snapshot in snapshots:
            group = dict(snapshot)
            line, = self.axes.plot(group.pop("line_x"), group.pop("line_y"))
            label = self.axes.text(*group.pop("label_position"), "", bbox={"pad": 2})
            line.set_gid("slope_measurement"); label.set_gid("slope_measurement")
            group.update(line=line, label=label, artists=[line, label])
            self._add_fit_artists(group)
            self._measurement_groups.append(group)
            self._measurement_artists.extend([line, label])
            self._style_measurement_group(group)
        self.measurements_changed.emit(); self.draw_idle()

    def _add_fit_artists(self, group: dict[str, Any]) -> None:
        """Reconstruct auditable picks and mean confidence band from plain data."""
        extra = []
        if group.get("retain_points"):
            points = np.asarray(group["points"])
            extra.extend(self.axes.plot(points[:, 0], points[:, 1], "o", markersize=4, linestyle="None"))
        if "band_x" in group:
            extra.append(self.axes.fill_between(group["band_x"], group["band_low"], group["band_high"], alpha=0.22))
        for artist in extra:
            artist.set_gid("slope_measurement")
        group["artists"].extend(extra)
        self._measurement_artists.extend(extra)

    def set_show_acceleration(self, show: bool) -> None:
        """Change label visibility without recalculating fits or moving labels."""
        self.show_acceleration = bool(show)
        for group in self._measurement_groups:
            self._style_measurement_group(group)
        self.draw_idle()

    def _acceleration_text(self, group: dict[str, Any]) -> str:
        unit = self.result.distance_unit if self.slope_velocity_unit == "auto" else self.slope_velocity_unit
        try:
            factor = convert_distance_value(1, self.result.distance_unit, unit,
                pixel_scale_arcsec_value=self.result.metadata.get("reference_pixel_scale_arcsec"))
        except ValueError:
            return "a = unavailable"
        denominator = "s" if self.result.times is not None else "frame"
        def formatted(value: float) -> str:
            # A small but finite acceleration must not silently read as zero.
            return f"{value:.{self.slope_precision}e}" if value != 0 and round(value, self.slope_precision) == 0 else f"{value:.{self.slope_precision}f}"
        error = group.get("acceleration_stderr")
        error_text = f" ± {formatted(abs(factor)*error)}" if error is not None else " (uncertainty unavailable)"
        text = rf"$a_{{{group['index']}}}$ = {formatted(factor*group['acceleration'])}{error_text} {unit}/{denominator}²"
        return text + (" (direction reversal)" if group.get("reverses_direction") else "")

    def _velocity_text(self, delta_s: float, delta_t: float, index: int = 1, stderr: float | None = None) -> str:
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
        denominator = "s" if self.result.times is not None else "frame"
        error_text = ""
        if stderr is not None:
            error = abs(convert_distance_value(stderr, source_unit, unit,
                pixel_scale_arcsec_value=self.result.metadata.get("reference_pixel_scale_arcsec")))
            error_text = f" ± {error:.{precision}f}"
        return rf"$v_{{{index}}}$ = {converted / delta_t:.{precision}f}{error_text} {unit}/{denominator}"
