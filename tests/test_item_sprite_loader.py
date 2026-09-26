from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

import pokemon_ev_tracker.ui.item_sprite_loader as loader
from pokemon_ev_tracker.games.platinum.items import _ITEM_CONSTANTS, get_gen4_item_name


def test_item_sprite_slug_resolution() -> None:
    assert loader.item_sprite_slug("Power Anklet") == "power-anklet"
    assert loader.item_sprite_slug("Exp. Share") == "exp-share"
    assert loader.item_sprite_slug("King's Rock") == "kings-rock"
    assert loader.item_sprite_slug("Zap Plate") == "zap-plate"
    assert loader.item_sprite_slug("TM68") == "tm-normal"
    assert loader.item_sprite_slug("HM08") == "hm-normal"
    assert loader.item_sprite_slug("S.S. Ticket") == "ss-ticket"


def test_power_anklet_sprite_is_copied_and_loads() -> None:
    app = QApplication.instance() or QApplication([])
    loader.clear_item_sprite_cache()

    path = loader.item_sprite_path("Power Anklet")
    assert path == loader.ITEM_SPRITE_DIRECTORY / "power-anklet.png"
    assert path.is_file()
    assert not loader.get_item_sprite("Power Anklet", 22).isNull()
    assert app is not None


def test_all_gen4_ev_training_item_icons_are_installed() -> None:
    app = QApplication.instance() or QApplication([])
    loader.clear_item_sprite_cache()
    names = (
        "Macho Brace",
        "Exp. Share",
        "Power Bracer",
        "Power Belt",
        "Power Lens",
        "Power Band",
        "Power Anklet",
        "Power Weight",
    )

    assert all(loader.item_sprite_path(name).is_file() for name in names)
    assert all(not loader.get_item_sprite(name, 22).isNull() for name in names)
    assert app is not None


def test_gen4_held_items_resolve_to_installed_icons() -> None:
    app = QApplication.instance() or QApplication([])
    loader.clear_item_sprite_cache()
    expected = {
        "Power Anklet": "power-anklet.png",
        "Zap Plate": "zap-plate.png",
        "TM68": "tm-normal.png",
        "Leftovers": "leftovers.png",
        "Oran Berry": "oran-berry.png",
        "Lucky Egg": "lucky-egg.png",
    }

    for item_name, filename in expected.items():
        path = loader.item_sprite_path(item_name)
        assert path == loader.ITEM_SPRITE_DIRECTORY / filename
        assert loader.item_sprite_exists(item_name)
        assert path.is_file()
        assert not loader.get_item_sprite(item_name, 22).isNull()
    assert app is not None


def test_all_gen4_tm_types_resolve_to_available_sprite_files() -> None:
    assert len(loader._GEN4_TM_TYPES) == 92
    for number in range(1, 93):
        assert loader.item_sprite_exists(f"TM{number:02}")
    for number in range(1, 9):
        assert loader.item_sprite_exists(f"HM{number:02}")


def test_every_active_platinum_item_has_a_local_sprite() -> None:
    loader.clear_item_sprite_cache()
    item_names = (get_gen4_item_name(item_id) for item_id in range(1, len(_ITEM_CONSTANTS) - 1))
    supported_names = [
        name for name in item_names if name is not None and not name.startswith("Unknown item #")
    ]

    assert len(supported_names) == 445
    assert all(loader.item_sprite_exists(name) for name in supported_names)


def test_no_held_item_has_no_sprite() -> None:
    app = QApplication.instance() or QApplication([])
    loader.clear_item_sprite_cache()

    assert loader.item_sprite_slug(None) is None
    assert loader.item_sprite_path(None) is None
    assert not loader.item_sprite_exists(None)
    assert loader.get_item_sprite(None, 22).isNull()
    assert app is not None


def test_item_sprite_cache_reuses_loaded_pixmap() -> None:
    app = QApplication.instance() or QApplication([])
    loader.clear_item_sprite_cache()

    first = loader.get_item_sprite("Power Anklet", 22)
    second = loader.get_item_sprite("Power Anklet", 22)

    assert first is second
    assert app is not None


def test_missing_item_sprite_returns_cached_blank_pixmap(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    loader.clear_item_sprite_cache()
    monkeypatch.setattr(
        loader,
        "ITEM_SPRITE_DIRECTORY",
        Path.cwd() / "assets" / "sprites" / "items" / "missing-test-dir",
    )

    first = loader.get_item_sprite("Power Anklet", 22)
    second = loader.get_item_sprite("Power Anklet", 22)

    assert first.isNull()
    assert first is second
    assert not loader.item_sprite_exists("Power Anklet")
    assert app is not None
