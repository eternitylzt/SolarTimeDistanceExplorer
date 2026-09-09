"""Cancellable Qt worker for multi-region time trends."""

from __future__ import annotations

import traceback

from PySide6.QtCore import QThread, Signal

from app.data.base import TimeSeriesDataset
from app.processing.region_analysis import RegionTrendResult, analyze_region_trends
from app.regions.base import RegionGeometry


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
