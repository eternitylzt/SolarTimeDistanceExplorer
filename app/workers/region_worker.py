"""Cancellable Qt worker for multi-region time trends."""

from __future__ import annotations

import traceback
from pathlib import Path
from typing import Any

from PySide6.QtCore import QThread, Signal

from app.data.base import TimeSeriesDataset
from app.processing.region_analysis import (
    RegionHistogramSequence,
    RegionTrendResult,
    analyze_region_trends,
    region_histogram_sequence,
)
from app.regions.base import RegionGeometry
from app.animation.exporter import export_region_histogram_animation


class RegionTrendWorker(QThread):
    progress = Signal(int); completed = Signal(object); failed = Signal(str, str); cancelled = Signal()

    def __init__(self, dataset: TimeSeriesDataset, regions: list[RegionGeometry], statistic: str) -> None:
        super().__init__(); self.dataset = dataset; self.regions = regions; self.statistic = statistic; self._cancel = False

    def request_cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        try:
            result = analyze_region_trends(
                self.dataset, self.regions, self.statistic,
                progress=lambda current, total: self.progress.emit(current),
                cancelled=lambda: self._cancel,
            )
            self.completed.emit(result)
        except InterruptedError:
            self.cancelled.emit()
        except Exception as exc:
            self.failed.emit(str(exc), traceback.format_exc())


class RegionHistogramSequenceWorker(QThread):
    """Cancellable worker for a range of per-frame region histograms."""

    progress = Signal(int)
    completed = Signal(object)
    failed = Signal(str, str)
    cancelled = Signal()

    def __init__(
        self,
        dataset: TimeSeriesDataset,
        regions: list[RegionGeometry],
        start_frame: int,
        end_frame: int,
        step: int,
        bin_width: float,
    ) -> None:
        super().__init__()
        self.dataset = dataset
        self.regions = regions
        self.start_frame = start_frame
        self.end_frame = end_frame
        self.step = step
        self.bin_width = bin_width
        self._cancel = False

    def request_cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        try:
            result: RegionHistogramSequence = region_histogram_sequence(
                self.dataset,
                self.regions,
                self.start_frame,
                self.end_frame,
                self.step,
                self.bin_width,
                progress=lambda current, total: self.progress.emit(current),
                cancelled=lambda: self._cancel,
            )
            self.completed.emit(result)
        except InterruptedError:
            self.cancelled.emit()
        except Exception as exc:
            self.failed.emit(str(exc), traceback.format_exc())


class RegionHistogramExportWorker(QThread):
    """Render/encode a histogram movie outside the Qt GUI thread."""

    progress = Signal(int, int)
    completed = Signal(str)
    failed = Signal(str, str)
    cancelled = Signal()

    def __init__(
        self,
        sequence: RegionHistogramSequence,
        destination: str | Path,
        settings: dict[str, Any],
    ) -> None:
        super().__init__()
        self.sequence = sequence
        self.destination = str(destination)
        self.settings = dict(settings)
        self._cancel = False

    def request_cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        try:
            export_region_histogram_animation(
                self.sequence,
                self.destination,
                progress=lambda current, total: self.progress.emit(current, total),
                cancelled=lambda: self._cancel,
                **self.settings,
            )
            self.completed.emit(self.destination)
        except InterruptedError:
            self.cancelled.emit()
        except Exception as exc:
            self.failed.emit(str(exc), traceback.format_exc())
