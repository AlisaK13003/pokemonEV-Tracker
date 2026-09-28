"""Small editors used by the game-independent Nuzlocke view."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from pokemon_ev_tracker.core.nuzlocke.models import DeathRecord, LevelCap, NuzlockeGameProfile


class NewRunDialog(QDialog):
    def __init__(self, profiles: tuple[NuzlockeGameProfile, ...], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Create Nuzlocke Run")
        self.profiles = profiles
        layout = QFormLayout(self)
        self.name_input = QLineEdit("New Run")
        self.game_input = QComboBox()
        for profile in profiles:
            self.game_input.addItem(profile.display_name, profile.game_id)
        layout.addRow("Run name", self.name_input)
        layout.addRow("Game", self.game_input)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def values(self) -> tuple[str, NuzlockeGameProfile]:
        profile = next(profile for profile in self.profiles if profile.game_id == self.game_input.currentData())
        return self.name_input.text(), profile


class EncounterDialog(QDialog):
    def __init__(self, location: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Encounter: {location}")
        form = QFormLayout(self)
        self.species_input = QLineEdit()
        self.nickname_input = QLineEdit()
        self.level_input = QSpinBox()
        self.level_input.setRange(0, 100)
        self.level_input.setSpecialValueText("—")
        self.status_input = QComboBox()
        for value, label in (
            ("NOT_ENCOUNTERED", "Not encountered"),
            ("CAUGHT", "Caught"),
            ("FAILED", "Failed"),
            ("DEAD", "Dead"),
            ("SKIPPED", "Skipped"),
            ("DUPES", "Dupes clause"),
        ):
            self.status_input.addItem(label, value)
        self.notes_input = QTextEdit()
        self.notes_input.setFixedHeight(74)
        form.addRow("Status", self.status_input)
        form.addRow("Pokémon", self.species_input)
        form.addRow("Nickname", self.nickname_input)
        form.addRow("Level", self.level_input)
        form.addRow("Notes", self.notes_input)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)


class LevelCapsDialog(QDialog):
    def __init__(self, caps: tuple[LevelCap, ...], overrides: dict[str, int], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Edit Level Caps")
        self._cap_rows: list[tuple[LevelCap, QCheckBox, QSpinBox]] = []
        layout = QVBoxLayout(self)
        self.table = QTableWidget(len(caps), 3)
        self.table.setHorizontalHeaderLabels(("Fight", "Category", "Cap"))
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.table.setColumnWidth(0, 220)
        self.table.setColumnWidth(1, 130)
        for row, cap in enumerate(caps):
            self.table.setItem(row, 0, QTableWidgetItem(cap.name))
            self.table.setItem(row, 1, QTableWidgetItem(cap.category))
            custom = QCheckBox("Custom")
            spin = QSpinBox()
            spin.setRange(1, 100)
            spin.setValue(overrides.get(cap.cap_id, cap.level_cap))
            custom.setChecked(cap.cap_id in overrides)
            spin.setEnabled(custom.isChecked())
            custom.toggled.connect(spin.setEnabled)
            cell = QWidget()
            cell_layout = QHBoxLayout(cell)
            cell_layout.setContentsMargins(4, 1, 4, 1)
            cell_layout.addWidget(spin)
            cell_layout.addWidget(custom)
            self.table.setCellWidget(row, 2, cell)
            self._cap_rows.append((cap, custom, spin))
        self.table.resizeRowsToContents()
        layout.addWidget(self.table)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.resize(520, min(680, 150 + len(caps) * 31))

    def overrides(self) -> dict[str, int | None]:
        return {
            cap.cap_id: spin.value() if custom.isChecked() else None
            for cap, custom, spin in self._cap_rows
        }


class DeathDialog(QDialog):
    def __init__(self, locations: tuple[str, ...], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Record a Death")
        form = QFormLayout(self)
        self.species_input = QLineEdit()
        self.nickname_input = QLineEdit()
        self.level_input = QSpinBox()
        self.level_input.setRange(0, 100)
        self.level_input.setSpecialValueText("—")
        self.location_input = QComboBox()
        self.location_input.setEditable(True)
        self.location_input.addItems(locations)
        self.notes_input = QTextEdit()
        self.notes_input.setFixedHeight(70)
        form.addRow("Pokémon", self.species_input)
        form.addRow("Nickname", self.nickname_input)
        form.addRow("Level at death", self.level_input)
        form.addRow("Location / fight", self.location_input)
        form.addRow("Notes", self.notes_input)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def record(self) -> DeathRecord:
        from datetime import UTC, datetime
        from uuid import uuid4

        return DeathRecord(
            death_id=uuid4().hex,
            species=self.species_input.text().strip(),
            nickname=self.nickname_input.text().strip(),
            level_at_death=self.level_input.value() or None,
            location_or_fight=self.location_input.currentText().strip(),
            timestamp=datetime.now(UTC).isoformat(timespec="seconds"),
            notes=self.notes_input.toPlainText().strip(),
        )
