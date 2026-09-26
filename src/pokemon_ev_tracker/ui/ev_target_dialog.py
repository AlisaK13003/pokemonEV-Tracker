"""Compact editor for one Pokémon's intended EV spread."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
)

from pokemon_ev_tracker.core.ev_targets import EV_STAT_KEYS, EVTarget

EV_STAT_LABELS = {
    "hp": "HP",
    "attack": "Attack",
    "defense": "Defense",
    "special_attack": "Sp. Atk",
    "special_defense": "Sp. Def",
    "speed": "Speed",
}


class EVTargetDialog(QDialog):
    def __init__(
        self,
        species: str,
        target: EVTarget | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"EV Target: {species}")
        self.setMinimumWidth(405)
        self._inputs: dict[str, QSpinBox] = {}

        layout = QVBoxLayout(self)
        fields = QGridLayout()
        fields.setHorizontalSpacing(10)
        fields.setVerticalSpacing(7)
        values = target.as_mapping() if target is not None else {}
        for index, stat in enumerate(EV_STAT_KEYS):
            row, pair = divmod(index, 2)
            column = pair * 2
            label = QLabel(EV_STAT_LABELS[stat])
            spin_box = QSpinBox()
            spin_box.setRange(0, 252)
            spin_box.setValue(values.get(stat, 0))
            spin_box.setFixedWidth(96)
            spin_box.setAlignment(Qt.AlignmentFlag.AlignRight)
            spin_box.valueChanged.connect(self._update_total)
            fields.addWidget(label, row, column)
            fields.addWidget(spin_box, row, column + 1)
            self._inputs[stat] = spin_box
        layout.addLayout(fields)

        self.total_label = QLabel()
        layout.addWidget(self.total_label)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        self.save_button = self.buttons.button(QDialogButtonBox.StandardButton.Save)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self._update_total()

    def target(self) -> EVTarget:
        return EVTarget(
            **{f"{stat}_target": spin_box.value() for stat, spin_box in self._inputs.items()}
        )

    def _update_total(self) -> None:
        total = sum(spin_box.value() for spin_box in self._inputs.values())
        valid = total <= 510
        self.total_label.setText(
            f"Target total: {total} / 510" if valid else f"Target total: {total} / 510 (over limit)"
        )
        self.total_label.setStyleSheet("color: palette(mid);" if valid else "color: #d18888;")
        self.save_button.setEnabled(valid)
