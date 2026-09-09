"""True-time Matplotlib time-distance canvas and slope measurement."""

from __future__ import annotations

from typing import Any

import matplotlib.dates as mdates
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtCore import Signal, Qt

from app.plotting.normalization import make_norm
from app.processing.td_generator import TDResult
from app.processing.time_edges import centers_to_edges


class TimeDistanceCanvas(FigureCanvasQTAgg):
    """Publication-quality TD renderer using real timestamp bin widths."""

    slope_measured = Signal(str)

    def __init__(self) -> None:
        self.figure = Figure(figsize=(8, 7), layout="constrained")
        super().__init__(self.figure)
        self.axes = self.figure.add_subplot(111)
        self.result: TDResult | None = None
        self._measure_mode = False
        self._measure_points: list[tuple[float, float]] = []
        self._measurement_artists: list[Any] = []
        self.slope_color = "#ffffff"
        self.slope_linewidth = 1.5
        self.slope_linestyle = "-"
        self.slope_fontsize = 10.0
        self.mpl_connect("button_press_event", self._on_press)

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
        self.figure.clear()
        self.axes = self.figure.add_subplot(111)
        distance_edges = centers_to_edges(result.distance)
        if true_time and result.times is not None:
            time_centers = mdates.date2num(result.times.to_datetime())
            time_edges = centers_to_edges(time_centers)
            default_x_label = "Observation Time [UTC]"
            if include_start_time:
                default_x_label += f" (Start: {result.times[0].utc.isot})"
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
        self.axes.set_xlabel(x_label.strip() or default_x_label, fontsize=axis_label_size)
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
        self._measure_points.clear()
        self.draw_idle()

    def enable_slope_measurement(self, enabled: bool) -> None:
        """Enter two-click slope mode while leaving the TD image unchanged."""
        self._measure_mode = enabled
        self._measure_points.clear()
        if enabled:
            self.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.unsetCursor()

    def set_slope_style(
        self, color: str, linewidth: float, fontsize: float, linestyle: str = "-"
    ) -> None:
        self.slope_color = color
        self.slope_linewidth = linewidth
        self.slope_fontsize = fontsize
        self.slope_linestyle = linestyle
        for artist in self._measurement_artists:
            if hasattr(artist, "set_color"):
                artist.set_color(color)
            if hasattr(artist, "set_linewidth") and artist.__class__.__name__ == "Line2D":
                artist.set_linewidth(linewidth)
            if hasattr(artist, "set_linestyle") and artist.__class__.__name__ == "Line2D":
                artist.set_linestyle(linestyle)
            if hasattr(artist, "set_fontsize"):
                artist.set_fontsize(fontsize)
        self.draw_idle()

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
        self._measure_points.clear()
        self._measure_mode = False
        self.unsetCursor()
        self.draw_idle()

    def _on_press(self, event: Any) -> None:
        if not self._measure_mode or self.result is None or event.inaxes is not self.axes:
            return
        if event.xdata is None or event.ydata is None:
            return
        self._measure_points.append((float(event.xdata), float(event.ydata)))
        points = self.axes.plot(
            event.xdata, event.ydata, "o", color=self.slope_color, markeredgecolor="black"
        )
        for artist in points:
            artist.set_gid("slope_measurement")
        self._measurement_artists.extend(points)
        if len(self._measure_points) < 2:
            self.draw_idle()
            return
        (t1, s1), (t2, s2) = self._measure_points
        lines = self.axes.plot(
            [t1, t2], [s1, s2], color=self.slope_color,
            linewidth=self.slope_linewidth, linestyle=self.slope_linestyle,
        )
        for artist in lines:
            artist.set_gid("slope_measurement")
        self._measurement_artists.extend(lines)
        delta_t = abs((t2 - t1) * 86400.0) if self.result.times is not None else abs(t2 - t1)
        delta_s = s2 - s1
        velocity = self._velocity_text(delta_s, delta_t)
        label = self.axes.annotate(
            velocity,
            ((t1 + t2) / 2.0, (s1 + s2) / 2.0),
            xytext=(8, 8), textcoords="offset points",
            color=self.slope_color, fontsize=self.slope_fontsize,
            bbox={"facecolor": "black", "alpha": 0.55, "edgecolor": self.slope_color, "pad": 2},
        )
        label.set_gid("slope_measurement")
        self._measurement_artists.append(label)
        self.slope_measured.emit(
            f"Δt = {delta_t:.3g} s; Δs = {delta_s:.4g} {self.result.distance_unit}; {velocity}"
        )
        self._measure_mode = False
        self._measure_points.clear()
        self.draw_idle()

    def _velocity_text(self, delta_s: float, delta_t: float) -> str:
        if delta_t == 0:
            return "v = undefined (Δt = 0)"
        assert self.result is not None
        unit = self.result.distance_unit
        if unit == "Mm":
            return f"v = {delta_s * 1000.0 / delta_t:.4g} km/s"
        if unit == "km":
            return f"v = {delta_s / delta_t:.4g} km/s"
        if unit == "arcsec":
            return f"v = {delta_s / delta_t:.4g} arcsec/s"
        return f"v = {delta_s / delta_t:.4g} pixel/s"
