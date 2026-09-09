"""A cancellable QThread worker that emits only data/progress, never touches widgets."""

from __future__ import annotations

import traceback

from PySide6.QtCore import QThread, Signal

from app.data.base import TimeSeriesDataset
from app.paths.base import PathGeometry
from app.processing.td_generator import TDConfig, TDResult, generate_time_distance


class TDWorker(QThread):
    """Run time-distance extraction outside the GUI event loop."""

    progress = Signal(int, int)
    completed = Signal(object)
    failed = Signal(str, str)
    cancelled = Signal()

    def __init__(self, dataset: TimeSeriesDataset, path: PathGeometry, config: TDConfig) -> None:
        super().__init__()
        self.dataset = dataset
        self.path = path
        self.config = config
        self._cancel_requested = False

    def request_cancel(self) -> None:
        """Ask the cooperative core loop to stop between frame reads."""
        self._cancel_requested = True

    def run(self) -> None:
        """Compute and translate failures into UI-safe signals."""
        try:
            result: TDResult = generate_time_distance(
                self.dataset,
                self.path,
                self.config,
                progress=lambda current, total: self.progress.emit(current, total),
                cancelled=lambda: self._cancel_requested,
            )
            self.completed.emit(result)
        except InterruptedError:
            self.cancelled.emit()
        except Exception as exc:
            self.failed.emit(str(exc), traceback.format_exc())
