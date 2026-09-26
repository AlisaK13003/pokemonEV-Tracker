from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from pokemon_ev_tracker.core.ev_targets import EVTarget
from pokemon_ev_tracker.ui.ev_target_dialog import EVTargetDialog


def test_target_dialog_loads_spread_and_bounds_each_input() -> None:
    app = QApplication.instance() or QApplication([])
    target = EVTarget(hp_target=4, attack_target=252, speed_target=252)

    dialog = EVTargetDialog("Mareep", target)

    assert dialog.target() == target
    assert all(spin.minimum() == 0 and spin.maximum() == 252 for spin in dialog._inputs.values())
    assert dialog.total_label.text() == "Target total: 508 / 510"
    assert dialog.save_button.isEnabled()
    assert dialog.minimumWidth() >= 405
    assert all(spin.width() >= 96 for spin in dialog._inputs.values())
    assert app is not None


def test_target_dialog_disables_save_above_total_limit() -> None:
    app = QApplication.instance() or QApplication([])
    dialog = EVTargetDialog("Mareep")
    dialog._inputs["hp"].setValue(252)
    dialog._inputs["attack"].setValue(252)
    dialog._inputs["defense"].setValue(7)

    assert dialog.total_label.text() == "Target total: 511 / 510 (over limit)"
    assert not dialog.save_button.isEnabled()
    assert app is not None
