"""Matplotlib canvas for publication-ready multi-region analysis plots."""

from __future__ import annotations

import matplotlib.dates as mdates
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from app.processing.region_analysis import RegionHistogramResult, RegionTrendResult


class RegionAnalysisCanvas(FigureCanvasQTAgg):
    """Render region trends/histograms while preserving marker colour identity."""

    def __init__(self) -> None:
        self.figure = Figure(figsize=(8, 6), layout="constrained")
        super().__init__(self.figure)
        self.axes = self.figure.add_subplot(111)

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
    ) -> None:
        self.figure.clear()
        self.axes = self.figure.add_subplot(111)
        if result.times is not None:
            x = mdates.date2num(result.times.utc.to_datetime())
            self.axes.xaxis_date()
            locator = mdates.AutoDateLocator(minticks=3, maxticks=9, interval_multiples=True)
            self.axes.xaxis.set_major_locator(locator)
            self.axes.xaxis.set_major_formatter(mdates.DateFormatter(time_format, tz="UTC"))
            default_x = "Observation Time [UTC]"
        else:
            x = result.frame_indices
            default_x = "Frame Index"
        for name, values, color in zip(
            result.region_names, result.values, result.region_colors, strict=True
        ):
            self.axes.plot(
                x, values, marker=marker, linestyle=line_style,
                linewidth=line_width, label=name, color=color,
            )
        statistic = "Mean" if result.statistic == "mean" else "Sum"
        self.axes.set_xlabel(x_label.strip() or default_x, fontsize=axis_label_size)
        self.axes.set_ylabel(y_label.strip() or f"Region {statistic}", fontsize=axis_label_size)
        self.axes.set_title(title.strip() or f"Region {statistic} vs Time")
        self.axes.set_yscale(y_scale)
        if grid:
            self.axes.grid(True, which="both", alpha=0.25)
        else:
            self.axes.grid(False)
        self.axes.minorticks_on()
        self.axes.tick_params(axis="both", which="both", labelsize=tick_label_size)
        self.axes.legend()
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
    ) -> None:
        self.figure.clear()
        self.axes = self.figure.add_subplot(111)
        for name, edges, counts, color in zip(
            result.region_names, result.edges, result.counts, result.region_colors, strict=True
        ):
            centers = (edges[:-1] + edges[1:]) / 2
            if plot_type == "bar":
                self.axes.bar(
                    centers, counts, width=edges[1:] - edges[:-1], align="center",
                    linewidth=line_width, linestyle=line_style, label=name,
                    color=color, edgecolor=color, alpha=0.42,
                )
            else:
                self.axes.plot(
                    centers, counts, drawstyle="steps-mid", linestyle=line_style,
                    linewidth=line_width, marker=marker, label=name, color=color,
                )
        self.axes.set_xlabel(x_label.strip() or "Pixel Value", fontsize=axis_label_size)
        self.axes.set_ylabel(y_label.strip() or "Count", fontsize=axis_label_size)
        observation = (
            result.time.utc.isot if result.time is not None
            else f"Frame {result.frame_index + 1}"
        )
        self.axes.set_title(title.strip() or f"Region Distribution — {observation}; Bin Width = {result.bin_width:g}")
        self.axes.set_xscale(x_scale)
        self.axes.set_yscale(y_scale)
        if grid:
            self.axes.grid(True, which="both", alpha=0.25)
        else:
            self.axes.grid(False)
        self.axes.minorticks_on()
        self.axes.tick_params(axis="both", which="both", labelsize=tick_label_size)
        self.axes.legend()
        self.draw_idle()
