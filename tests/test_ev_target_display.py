from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel, QProgressBar

from pokemon_ev_tracker.core.ev_targets import EV_STAT_KEYS, EVTarget
from pokemon_ev_tracker.ui.main_window import MainWindow


def test_target_card_display_shows_remaining_overshoot_and_completion() -> None:
    app = QApplication.instance() or QApplication([])
    target = EVTarget(attack_target=252, speed_target=252)
    store = SimpleNamespace(get=lambda _pid: target)
    card = {
        "ev_target": None,
        "clear_target_button": SimpleNamespace(setEnabled=lambda _value: None),
        "target_summary": QLabel(),
        "evs": {stat: QLabel() for stat in EV_STAT_KEYS},
        "ev_annotations": {stat: QLabel() for stat in EV_STAT_KEYS},
        "ev_bars": {stat: QProgressBar() for stat in EV_STAT_KEYS},
    }
    pokemon = SimpleNamespace(
        decoded=SimpleNamespace(diagnostics=SimpleNamespace(pid=0x1234)),
        checksum_valid=True,
        evs={
            "hp": 0,
            "attack": 253,
            "defense": 0,
            "special_attack": 0,
            "special_defense": 0,
            "speed": 157,
        },
    )
    window_stub = SimpleNamespace(ev_target_store=store)

    MainWindow._refresh_tracker_target_display(window_stub, card, pokemon)

    assert card["evs"]["attack"].text() == "253 / 252"
    assert card["ev_annotations"]["attack"].text() == "+1 over target"
    assert card["evs"]["speed"].text() == "157 / 252"
    assert card["ev_annotations"]["speed"].text() == "95 remaining"
    assert card["ev_bars"]["speed"].maximum() == 252
    assert card["ev_bars"]["speed"].value() == 157
    assert card["target_summary"].text() == ("Target progress: 409 / 504 • 95 EVs remaining")

    pokemon.evs["speed"] = 252
    MainWindow._refresh_tracker_target_display(window_stub, card, pokemon)

    assert card["target_summary"].text() == "Target complete"
    assert app is not None
