from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel

from pokemon_ev_tracker.games.platinum.items import get_gen4_item_hint, get_gen4_item_name
from pokemon_ev_tracker.ui.main_window import MainWindow


def test_generation_four_item_mapping_and_ev_effects() -> None:
    assert get_gen4_item_name(0) is None
    assert get_gen4_item_name(290) == "Power Belt"
    assert get_gen4_item_name(291) == "Power Lens"
    assert get_gen4_item_name(292) == "Power Band"
    assert get_gen4_item_name(293) == "Power Anklet"
    assert get_gen4_item_name(294) == "Power Weight"
    assert get_gen4_item_name(289) == "Power Bracer"
    assert get_gen4_item_name(215) == "Macho Brace"
    assert get_gen4_item_name(216) == "Exp. Share"
    assert get_gen4_item_hint(294) == "+4 HP EV"
    assert get_gen4_item_hint(289) == "+4 Attack EV"
    assert get_gen4_item_hint(290) == "+4 Defense EV"
    assert get_gen4_item_hint(291) == "+4 Sp. Atk EV"
    assert get_gen4_item_hint(292) == "+4 Sp. Def EV"
    assert get_gen4_item_hint(293) == "+4 Speed EV"
    assert get_gen4_item_hint(215) == "EV gain x2"
    assert get_gen4_item_hint(216) == "Receives EXP/EVs"
    assert get_gen4_item_name(300) == "Zap Plate"
    assert get_gen4_item_name(395) == "TM68"
    assert get_gen4_item_name(234) == "Leftovers"
    assert get_gen4_item_name(155) == "Oran Berry"
    assert get_gen4_item_name(231) == "Lucky Egg"


def test_platinum_catalog_covers_all_active_nonzero_ids() -> None:
    from pokemon_ev_tracker.games.platinum.items import _ITEM_CONSTANTS

    supported = [
        item_id
        for item_id in range(1, len(_ITEM_CONSTANTS) - 1)
        if (name := get_gen4_item_name(item_id)) is not None
        and not name.startswith("Unknown item #")
    ]
    assert len(supported) == 445


def test_tracker_card_updates_held_item_only_when_id_changes(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    icon = QLabel()
    name = QLabel()
    hint = QLabel()
    card = {
        "held_item_id": None,
        "item_icon": icon,
        "item_name": name,
        "item_hint": hint,
    }
    loads = []

    from PySide6.QtGui import QPixmap

    import pokemon_ev_tracker.ui.main_window as main_window_module

    monkeypatch.setattr(
        main_window_module,
        "get_item_sprite",
        lambda item_name, size: loads.append((item_name, size)) or QPixmap(),
    )

    anklet = SimpleNamespace(held_item_id=293, held_item_name="Power Anklet")
    assert MainWindow._refresh_tracker_held_item(card, anklet) is True
    assert name.text() == "Power Anklet"
    assert hint.text() == "+4 Speed EV"
    assert MainWindow._refresh_tracker_held_item(card, anklet) is False
    assert loads == [("Power Anklet", 22)]

    none = SimpleNamespace(held_item_id=0, held_item_name=None)
    assert MainWindow._refresh_tracker_held_item(card, none) is True
    assert name.text() == "No held item"
    assert hint.text() == ""
    assert hint.isHidden()
    assert loads == [("Power Anklet", 22)]
    assert app is not None


def test_tracker_keeps_item_name_when_sprite_is_missing(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    icon = QLabel()
    name = QLabel()
    hint = QLabel()
    card = {
        "held_item_id": None,
        "item_icon": icon,
        "item_name": name,
        "item_hint": hint,
    }

    from PySide6.QtGui import QPixmap

    import pokemon_ev_tracker.ui.main_window as main_window_module

    monkeypatch.setattr(main_window_module, "get_item_sprite", lambda item_name, size: QPixmap())
    pokemon = SimpleNamespace(held_item_id=300, held_item_name="Zap Plate")

    assert MainWindow._refresh_tracker_held_item(card, pokemon) is True
    assert name.text() == "Zap Plate"
    assert app is not None
