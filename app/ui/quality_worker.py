"""Cancellable header-only quality scan, without image I/O on the GUI thread."""
from PySide6.QtCore import QThread, Signal
from app.data.quality import quality_report
import logging


class QualityWorker(QThread):
    progress = Signal(int, int)
    ready = Signal(object)
    failed = Signal(str)

    def __init__(self, dataset, parent=None):
        super().__init__(parent)
        self.dataset = dataset

    def run(self):
        try:
            report = quality_report(self.dataset, self.progress.emit, self.isInterruptionRequested)
            if not self.isInterruptionRequested():
                self.ready.emit(report)
        except InterruptedError:
            pass
        except Exception as exc:
            logging.getLogger(__name__).exception("Quality report failed")
            self.failed.emit(str(exc))
