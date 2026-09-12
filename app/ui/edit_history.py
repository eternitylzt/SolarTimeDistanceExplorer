"""Bounded Qt undo commands for marker editing, separate from plot history."""
from __future__ import annotations
from typing import Any
from PySide6.QtCore import QObject, QTimer
from PySide6.QtGui import QUndoCommand, QUndoStack


class MarkerCommand(QUndoCommand):
    def __init__(self, owner: Any, before: dict, after: dict) -> None:
        super().__init__("Slit / Region edit")
        self.owner, self.before, self.after = owner, before, after
        self.initial = True

    def undo(self) -> None:
        self.owner.restore(self.before)

    def redo(self) -> None:
        if self.initial:
            self.initial = False
        else:
            self.owner.restore(self.after)


class MarkerUndo(QObject):
    """Merge continuous drags/spinbox changes without storing image arrays."""
    def __init__(self, window: Any) -> None:
        super().__init__(window)
        self.window = window
        self.stack = QUndoStack(self); self.stack.setUndoLimit(100)
        self.timer = QTimer(self); self.timer.setSingleShot(True)
        self.timer.timeout.connect(lambda: self.flush(wait_for_gesture=True))
        self.restoring = False
        self.last = window._marker_edit_state()

    def changed(self) -> None:
        if not self.restoring:
            self.timer.start(300)

    def reset(self) -> None:
        self.timer.stop(); self.stack.clear()
        self.last = self.window._marker_edit_state()

    def flush(self, *, wait_for_gesture: bool = False) -> None:
        self.timer.stop()
        if self.restoring:
            return
        if wait_for_gesture and any(e._drag_index is not None or e._drag_label
                                    for e in (self.window.path_editor, self.window.region_editor)):
            self.timer.start(100)
            return
        current = self.window._marker_edit_state()
        # Mere selection changes are not edits, but update the selection used
        # when undoing the next actual change.
        if (current["paths"], current["regions"]) != (self.last["paths"], self.last["regions"]):
            self.stack.push(MarkerCommand(self, self.last, current))
        self.last = current

    def restore(self, state: dict) -> None:
        self.restoring = True
        try:
            self.window._restore_marker_edit_state(state)
            self.last = self.window._marker_edit_state()
        finally:
            self.restoring = False

    def undo(self) -> None:
        self.flush(); self.stack.undo()

    def redo(self) -> None:
        self.flush(); self.stack.redo()
