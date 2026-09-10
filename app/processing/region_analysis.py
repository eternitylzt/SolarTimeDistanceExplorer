"""Numerical closed-region trend and histogram analysis."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np
from astropy.time import Time

from app.data.base import TimeSeriesDataset
from app.regions.base import RegionGeometry


@dataclass
class RegionTrendResult:
    times: Time | None
    frame_indices: np.ndarray
    region_ids: list[str]
    region_names: list[str]
    values: np.ndarray  # [region, time]
    statistic: str
    region_colors: list[str]


@dataclass
class RegionHistogramResult:
    region_ids: list[str]
    region_names: list[str]
    edges: list[np.ndarray]
    counts: list[np.ndarray]
    frame_index: int
    bin_width: float
    region_colors: list[str]
    time: Time | None = None


@dataclass
class RegionHistogramSequence:
    """A frame-ordered histogram series suitable for review and animation."""

    results: list[RegionHistogramResult]
    frame_indices: np.ndarray
    start_frame: int
    end_frame: int
    step: int

    @property
    def n_frames(self) -> int:
        return len(self.results)


def analyze_region_trends(
    dataset: TimeSeriesDataset,
    regions: list[RegionGeometry],
    statistic: str,
    progress: Callable[[int, int], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> RegionTrendResult:
    """Calculate NaN-aware mean or sum inside every region for every frame."""
    if statistic not in {"mean", "sum"}:
        raise ValueError("Region statistic must be mean or sum.")
    active = [region for region in regions if region.complete and region.visible]
    if not active:
        raise ValueError("Finish at least one closed region first.")
    output = np.full((len(active), dataset.n_frames), np.nan, dtype=float)
    for frame_index in range(dataset.n_frames):
        if cancelled and cancelled():
            raise InterruptedError("Region analysis cancelled by user.")
        frame = np.asarray(dataset.get_frame(frame_index), dtype=float)
        wcs = dataset.get_wcs(frame_index)
        for region_index, region in enumerate(active):
            values = frame[region.mask(frame.shape, wcs)]
            values = values[np.isfinite(values)]
            if values.size:
                output[region_index, frame_index] = np.mean(values) if statistic == "mean" else np.sum(values)
        if progress:
            progress(frame_index + 1, dataset.n_frames)
    return RegionTrendResult(
        times=dataset.times,
        frame_indices=np.arange(dataset.n_frames),
        region_ids=[item.id for item in active],
        region_names=[item.name for item in active],
        values=output,
        statistic=statistic,
        region_colors=[item.display_color for item in active],
    )


def region_histograms(
    frame: np.ndarray,
    regions: list[RegionGeometry],
    wcs,
    frame_index: int,
    bin_width: float,
    time: Time | None = None,
) -> RegionHistogramResult:
    """Histogram finite pixel values in each region with an exact bin width."""
    if bin_width <= 0:
        raise ValueError("Histogram bin width must be positive.")
    names: list[str] = []
    ids: list[str] = []
    all_edges: list[np.ndarray] = []
    all_counts: list[np.ndarray] = []
    for region in regions:
        if not region.complete or not region.visible:
            continue
        values = np.asarray(frame, dtype=float)[region.mask(frame.shape, wcs)]
        values = values[np.isfinite(values)]
        if not values.size:
            edges = np.array([0.0, bin_width])
            counts = np.array([0])
        else:
            start = np.floor(values.min() / bin_width) * bin_width
            stop = np.ceil(values.max() / bin_width) * bin_width
            if stop <= start:
                stop = start + bin_width
            edges = np.arange(start, stop + bin_width * 1.000001, bin_width)
            counts, edges = np.histogram(values, bins=edges)
        names.append(region.name); ids.append(region.id); all_edges.append(edges); all_counts.append(counts)
    return RegionHistogramResult(
        region_ids=ids, region_names=names, edges=all_edges, counts=all_counts,
        frame_index=frame_index, bin_width=bin_width,
        region_colors=[item.display_color for item in regions if item.complete and item.visible],
        time=time,
    )


def region_histogram_sequence(
    dataset: TimeSeriesDataset,
    regions: list[RegionGeometry],
    start_frame: int,
    end_frame: int,
    step: int,
    bin_width: float,
    progress: Callable[[int, int], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> RegionHistogramSequence:
    """Calculate selected-region histograms for an inclusive frame range.

    Histogram bins retain the requested physical data-value width. Each frame
    therefore remains a faithful distribution even when its value range changes;
    the animation renderer applies shared axes limits to avoid visual jitter.
    """
    if dataset.n_frames < 1:
        raise ValueError("The dataset has no frames.")
    start = max(0, min(int(start_frame), dataset.n_frames - 1))
    end = max(0, min(int(end_frame), dataset.n_frames - 1))
    if start > end:
        start, end = end, start
    stride = max(1, int(step))
    indices = np.arange(start, end + 1, stride, dtype=int)
    results: list[RegionHistogramResult] = []
    for position, frame_index in enumerate(indices, start=1):
        if cancelled and cancelled():
            raise InterruptedError("Region histogram sequence cancelled by user.")
        results.append(
            region_histograms(
                dataset.get_frame(int(frame_index)),
                regions,
                dataset.get_wcs(int(frame_index)),
                int(frame_index),
                bin_width,
                time=dataset.get_time(int(frame_index)),
            )
        )
        if progress:
            progress(position, len(indices))
    if not results or not results[0].region_names:
        raise ValueError("Select at least one completed closed region.")
    return RegionHistogramSequence(results, indices, start, end, stride)
