"""Manual geometry dialog for reproducible circle and rectangle regions."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QPushButton, QVBoxLayout

from app.regions.base import RegionGeometry


class ManualRegionDialog(QDialog):
    def __init__(self, name: str, preview: Callable[[RegionGeometry], None], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("手动设置闭合区域")
        self.name = name; self._preview = preview
        layout = QVBoxLayout(self); form = QFormLayout()
        self.kind = QComboBox(); self.kind.addItem("圆形", "circle"); self.kind.addItem("长方形", "rectangle")
        self.x = _spin(0.0); self.y = _spin(0.0); self.radius = _spin(10.0, positive=True)
        self.width = _spin(20.0, positive=True); self.height = _spin(10.0, positive=True)
        self.angle = _spin(0.0); self.angle.setRange(-360.0, 360.0)
        form.addRow("形状", self.kind); form.addRow("中心 X [pixel]", self.x); form.addRow("中心 Y [pixel]", self.y)
        form.addRow("圆半径 [pixel]", self.radius); form.addRow("长方形宽度 [pixel]", self.width)
        form.addRow("长方形高度 [pixel]", self.height); form.addRow("旋转角 [deg]", self.angle)
        layout.addLayout(form)
        preview_button = QPushButton("预览"); preview_button.clicked.connect(lambda: self._preview(self.geometry()))
        layout.addWidget(preview_button)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); layout.addWidget(buttons)

    def geometry(self) -> RegionGeometry:
        center = (self.x.value(), self.y.value())
        if self.kind.currentData() == "circle":
            return RegionGeometry.circle(self.name, center, self.radius.value())
        return RegionGeometry.rectangle(
            self.name, center, self.width.value(), self.height.value(), self.angle.value()
        )


def _spin(value: float, positive: bool = False) -> QDoubleSpinBox:
    control = QDoubleSpinBox(); control.setDecimals(4)
    control.setRange(1e-6 if positive else -1e9, 1e9); control.setValue(value)
    return control
