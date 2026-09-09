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
    active = [region for region in regions if region.complete]
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
        if not region.complete:
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
        region_colors=[item.display_color for item in regions if item.complete],
        time=time,
    )
