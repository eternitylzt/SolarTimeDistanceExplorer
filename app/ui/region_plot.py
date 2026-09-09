"""Matplotlib canvas for publication-ready multi-region analysis plots."""

from __future__ import annotations

import matplotlib.dates as mdates
import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from app.processing.region_analysis import RegionHistogramResult, RegionTrendResult


class RegionAnalysisCanvas(FigureCanvasQTAgg):
    """Render region trends/histograms while preserving marker colour identity."""

    def __init__(self) -> None:
        self.figure = Figure(figsize=(8, 6), layout="constrained")
        layout_engine = self.figure.get_layout_engine()
        if layout_engine is not None:
            layout_engine.set(w_pad=7.0 / 72.0, h_pad=5.0 / 72.0, wspace=0.04, hspace=0.04)
        super().__init__(self.figure)
        self.axes = self.figure.add_subplot(111)

    def clear_plot(self, message: str = "No selected regions") -> None:
        """Clear stale analysis when no checked region remains."""
        self.figure.clear()
        self.axes = self.figure.add_subplot(111)
        self.axes.text(0.5, 0.5, message, ha="center", va="center", transform=self.axes.transAxes)
        self.axes.set_axis_off()
        self.draw_idle()

    def show_trends(
        self,
        result: RegionTrendResult,
        *,
        time_format: str = "%H:%M:%S",
        title: str = "",
        x_label: str = "",
        y_label: str = "",
        line_style: str = "-",
        line_width: float = 1.5,
        marker: str = ".",
        grid: bool = True,
        y_scale: str = "linear",
        axis_label_size: float = 11.0,
        tick_label_size: float = 9.0,
        title_size: float = 12.0,
        legend_fontsize: float = 12.0,
        plot_type: str = "line",
    ) -> None:
        self.figure.clear()
        self.axes = self.figure.add_subplot(111)
        is_time = result.times is not None
        if is_time:
            x = mdates.date2num(result.times.utc.to_datetime())
            self.axes.xaxis_date()
            locator = mdates.AutoDateLocator(minticks=3, maxticks=9, interval_multiples=True)
            self.axes.xaxis.set_major_locator(locator)
            self.axes.xaxis.set_major_formatter(mdates.DateFormatter(time_format, tz="UTC"))
            default_x = "Observation Time [UTC]"
        else:
            x = result.frame_indices
            default_x = "Frame Index"
        entries = list(zip(result.region_names, result.values, result.region_colors, strict=True))
        if plot_type == "bar":
            # Group bars rather than overplot them. Larger-amplitude series are
            # ordered first and smaller ones receive the higher z-order.
            entries.sort(
                key=lambda item: float(np.nanmax(np.abs(item[1]))) if np.any(np.isfinite(item[1])) else 0.0,
                reverse=True,
            )
            if len(x) > 1:
                intervals = np.diff(np.asarray(x, dtype=float))
                positive = intervals[intervals > 0]
                base_width = float(np.min(positive)) * 0.82 if positive.size else 0.8
            else:
                base_width = (1.0 / 86400.0) if is_time else 0.8
            width = base_width / max(1, len(entries))
            origin = (len(entries) - 1) / 2.0
            for index, (name, values, color) in enumerate(entries):
                offset = (index - origin) * width
                self.axes.bar(
                    np.asarray(x) + offset, values, width=width * 0.94,
                    label=name, color=color, edgecolor=color, alpha=0.72,
                    linewidth=line_width, linestyle=line_style, zorder=3 + index,
                )
        else:
            for name, values, color in entries:
                self.axes.plot(
                    x, values, marker=marker, linestyle=line_style,
                    linewidth=line_width, label=name, color=color,
                )
        statistic = "Mean" if result.statistic == "mean" else "Sum"
        self.axes.set_xlabel(x_label.strip() or default_x, fontsize=axis_label_size)
        self.axes.set_ylabel(y_label.strip() or f"Region {statistic}", fontsize=axis_label_size)
        self.axes.set_title(title.strip() or f"Region {statistic} vs Time", fontsize=title_size)
        self.axes.set_yscale(y_scale)
        if grid:
            self.axes.grid(True, which="both", alpha=0.25)
        else:
            self.axes.grid(False)
        self.axes.minorticks_on()
        self.axes.tick_params(axis="both", which="both", labelsize=tick_label_size)
        if entries:
            self.axes.legend(fontsize=legend_fontsize)
        self.draw_idle()

    def show_histograms(
        self,
        result: RegionHistogramResult,
        *,
        title: str = "",
        x_label: str = "",
        y_label: str = "",
        line_style: str = "-",
        line_width: float = 1.5,
        marker: str = "None",
        grid: bool = True,
        x_scale: str = "linear",
        y_scale: str = "linear",
        plot_type: str = "bar",
        axis_label_size: float = 11.0,
        tick_label_size: float = 9.0,
        title_size: float = 12.0,
        legend_fontsize: float = 12.0,
        y_unit: str = "count",
    ) -> None:
        self.figure.clear()
        self.axes = self.figure.add_subplot(111)
        entries = list(zip(
            result.region_names, result.edges, result.counts, result.region_colors, strict=True
        ))
        # Draw the tallest distribution first. Small distributions are drawn
        # later/on top, which keeps their correct colours visible without an
        # expensive collision algorithm.
        entries.sort(key=lambda item: float(np.max(item[2])) if len(item[2]) else 0.0, reverse=True)
        for z_index, (name, edges, raw_counts, color) in enumerate(entries):
            counts = np.asarray(raw_counts, dtype=float)
            if y_unit == "frequency":
                total = float(np.sum(counts))
                counts = counts / total if total > 0 else counts
            centers = (edges[:-1] + edges[1:]) / 2
            if plot_type == "bar":
                self.axes.bar(
                    centers, counts, width=edges[1:] - edges[:-1], align="center",
                    linewidth=line_width, linestyle=line_style, label=name,
                    color=color, edgecolor=color, alpha=0.46, zorder=3 + z_index,
                )
            else:
                self.axes.plot(
                    centers, counts, drawstyle="steps-mid", linestyle=line_style,
                    linewidth=line_width, marker=marker, label=name, color=color,
                )
        self.axes.set_xlabel(x_label.strip() or "Pixel Value", fontsize=axis_label_size)
        default_y = "Relative Frequency" if y_unit == "frequency" else "Count"
        self.axes.set_ylabel(y_label.strip() or default_y, fontsize=axis_label_size)
        observation = (
            result.time.utc.isot if result.time is not None
            else f"Frame {result.frame_index + 1}"
        )
        self.axes.set_title(
            title.strip() or f"Region Distribution — {observation}; Bin Width = {result.bin_width:g}",
            fontsize=title_size,
        )
        self.axes.set_xscale(x_scale)
        self.axes.set_yscale(y_scale)
        if grid:
            self.axes.grid(True, which="both", alpha=0.25)
        else:
            self.axes.grid(False)
        self.axes.minorticks_on()
        self.axes.tick_params(axis="both", which="both", labelsize=tick_label_size)
        if entries:
            self.axes.legend(fontsize=legend_fontsize)
        self.draw_idle()
