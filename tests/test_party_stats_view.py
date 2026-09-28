from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from pokemon_ev_tracker.config.settings import AppSettings
from pokemon_ev_tracker.core.ev_targets import EVTargetStore
from pokemon_ev_tracker.core.nuzlocke.storage import NuzlockeStore
from pokemon_ev_tracker.data_sources.base import DataSourceSnapshot
from pokemon_ev_tracker.data_sources.bizhawk import BizHawkRamDataSource
from pokemon_ev_tracker.games.platinum.decoder import decode_party
from pokemon_ev_tracker.games.platinum.nuzlocke import PLATINUM_NUZLOCKE_PROFILE
from pokemon_ev_tracker.games.platinum.profile import PLATINUM_PROFILE
from pokemon_ev_tracker.pokemon.gen4.crypto import (
    BOX_DATA_SIZE,
    calculate_checksum,
    encrypt_box_data,
    xor_words,
)
from pokemon_ev_tracker.pokemon.gen4.structure import PARTY_POKEMON_SIZE
from pokemon_ev_tracker.ui.main_window import MainWindow


@pytest.fixture
def make_window(monkeypatch, tmp_path):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(BizHawkRamDataSource, "start", lambda self: None)
    monkeypatch.setattr(BizHawkRamDataSource, "stop", lambda self: None)
    monkeypatch.setattr(AppSettings, "save_default", lambda self: None)

    def create(settings: AppSettings | None = None) -> MainWindow:
        return MainWindow(
            settings or AppSettings(),
            target_store=EVTargetStore(tmp_path / "targets.json"),
            nuzlocke_store=NuzlockeStore(tmp_path / "nuzlocke_runs.json"),
        )

    yield create
    assert app is not None


def test_training_stats_toggle_hides_log_without_clearing_history(make_window) -> None:
    window = make_window()
    window._ev_history_records = [("15:42:11  Marill Attack 0 -> 1  +1", "+1 Attack")]
    window._render_ev_history()

    window.set_tracker_view("stats")
    card = window.tracker_party_cards[1]
    assert card["training_content"].isHidden()
    assert not card["stats_content"].isHidden()
    assert window.ev_change_log.isHidden()
    assert window.ev_change_list.count() == 1
    assert window.settings.tracker_view == "stats"

    window.set_tracker_view("training")
    assert not card["training_content"].isHidden()
    assert card["stats_content"].isHidden()
    assert not window.ev_change_log.isHidden()
    assert window.ev_change_list.item(0).text().startswith("15:42:11")
    window.close()


def test_stats_view_is_restored_from_settings(make_window) -> None:
    window = make_window(AppSettings(tracker_view="stats"))

    assert window.tracker_view == "stats"
    assert window.tracker_view_buttons["stats"].isChecked()
    assert window.tracker_party_cards[1]["training_content"].isHidden()
    assert not window.tracker_party_cards[1]["stats_content"].isHidden()
    assert window.ev_change_log.isHidden()
    window.close()


def test_stats_view_works_in_compact_mode(make_window) -> None:
    window = make_window()
    window.set_tracker_view("stats")
    window.set_compact_mode(True)

    assert window.compact_mode
    assert not window.tracker_party_cards[1]["stats_content"].isHidden()
    assert window.ev_change_log.isHidden()
    window.close()


def test_party_reorder_keeps_stats_attached_to_each_ram_record(make_window) -> None:
    window = make_window()
    window.set_tracker_view("stats")
    first = _party_payload(
        (
            _party_record(0x12345678, 183, 47, attack=27),
            _party_record(0x12345679, 443, 8, attack=41),
        )
    )
    second = _party_payload(
        (
            _party_record(0x12345679, 443, 8, attack=41),
            _party_record(0x12345678, 183, 47, attack=27),
        )
    )

    window._refresh_tracker_party(True, decode_party(first))
    assert window.tracker_party_cards[1]["stat_values"]["attack"].text() == "27"
    assert window.tracker_party_cards[2]["stat_values"]["attack"].text() == "41"

    window._refresh_tracker_party(True, decode_party(second))
    assert window.tracker_party_cards[1]["stat_values"]["attack"].text() == "41"
    assert window.tracker_party_cards[1]["ability"].text() == "Ability: Sand Veil"
    assert window.tracker_party_cards[2]["stat_values"]["attack"].text() == "27"
    assert window.tracker_party_cards[2]["ability"].text() == "Ability: Thick Fat"
    window.close()


def test_nature_highlights_only_boosted_and_lowered_non_hp_stats(make_window) -> None:
    window = make_window()
    window.set_tracker_view("stats")
    record = _party_record(3, 183, 47, attack=27)
    window._refresh_tracker_party(True, decode_party(_party_payload((record,))))
    card = window.tracker_party_cards[1]

    assert card["nature"].text() == "Nature: Adamant"
    assert "#df8585" in card["stat_names"]["attack"].styleSheet()
    assert "#86aee0" in card["stat_names"]["special_attack"].styleSheet()
    assert "#df8585" not in card["stat_names"]["hp"].styleSheet()
    assert "#86aee0" not in card["stat_names"]["hp"].styleSheet()
    window.close()


def test_party_stats_renders_friendship_and_debug_value(make_window) -> None:
    window = make_window()
    window.set_tracker_view("stats")
    party_state = decode_party(
        _party_payload((_party_record(3, 183, 47, attack=27, friendship=164),))
    )

    window._refresh_tracker_party(True, party_state)
    window._refresh_ram_party_debug(party_state, None)
    card = window.tracker_party_cards[1]

    assert not card["stats_content"].isHidden()
    assert card["friendship"].text() == "Friendship: 164 / 255 • High"
    assert card["friendship_bar"].maximum() == 255
    assert card["friendship_bar"].value() == 164
    assert "Friendship: 164" in window.ram_party_details.toPlainText()
    window.close()


def test_friendship_updates_live_when_ram_value_changes(make_window) -> None:
    window = make_window()
    window.set_tracker_view("stats")

    first = decode_party(
        _party_payload((_party_record(3, 183, 47, attack=27, friendship=164),))
    )
    updated = decode_party(
        _party_payload((_party_record(3, 183, 47, attack=27, friendship=165),))
    )
    window._refresh_tracker_party(True, first)
    bar = window.tracker_party_cards[1]["friendship_bar"]
    original_bar_id = id(bar)

    window._refresh_tracker_party(True, updated)

    card = window.tracker_party_cards[1]
    assert card["friendship"].text() == "Friendship: 165 / 255 • High"
    assert card["friendship_bar"].value() == 165
    assert id(card["friendship_bar"]) == original_bar_id
    window.close()


def test_compact_party_stats_shows_minimal_friendship_without_bar(make_window) -> None:
    window = make_window()
    window.set_tracker_view("stats")
    window.set_compact_mode(True)
    party_state = decode_party(
        _party_payload((_party_record(3, 183, 47, attack=27, friendship=164),))
    )

    window._refresh_tracker_party(True, party_state)
    card = window.tracker_party_cards[1]

    assert card["nature"].text().startswith("Adamant • ")
    assert card["ability"].isHidden()
    assert card["friendship"].text() == "Friendship 164"
    assert card["friendship_bar"].isHidden()
    window.close()


def test_main_window_baselines_then_surfaces_new_party_acquisition(monkeypatch, tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(AppSettings, "save_default", lambda _self: None)
    run_store = NuzlockeStore(tmp_path / "runs.json")
    run = run_store.create_run("Platinum", PLATINUM_NUZLOCKE_PROFILE)
    original = _party_record(0x12345678, 21, 0, attack=20, met_location_id=0x11, met_level=3)

    class SnapshotSource:
        profile = PLATINUM_PROFILE

        def __init__(self):
            self.state = decode_party(_party_payload((original,)))

        def start(self):
            pass

        def stop(self):
            pass

        def snapshot(self):
            return DataSourceSnapshot(
                "BizHawk RAM",
                True,
                {
                    "heartbeat": None,
                    "party_state": self.state,
                    "display_party_state": self.state,
                    "party_payload": None,
                    "battle_battlers": (),
                    "active_enemy_battlers": (),
                },
            )

    source = SnapshotSource()
    window = MainWindow(
        AppSettings(),
        data_source=source,
        target_store=EVTargetStore(tmp_path / "targets.json"),
        nuzlocke_store=run_store,
    )
    try:
        assert run.acquisition_events == []
        assert run.observed_pokemon_ids == ["pid:12345678:ot:0000:0000"]

        newly_seen = _party_record(
            0x87654321,
            403,
            0,
            attack=23,
            met_location_id=0x11,
            met_level=4,
        )
        source.state = decode_party(_party_payload((original, newly_seen)))
        window._refresh_ram_backend_debug()
        app.processEvents()

        assert len(run.acquisition_events) == 1
        assert run.acquisition_events[0].species_name == "Shinx"
        assert run.acquisition_events[0].suggested_location_name == "Route 202"
        assert window.nuzlocke_view.acquisition_selector.currentData() == (
            "pid:87654321:ot:0000:0000"
        )
        debug_text = window.ram_party_details.toPlainText()
        assert "Met location: ID 17 (Route 202)" in debug_text
        assert "decrypted box +0x3E" in debug_text
        assert "Acquisition classification: WILD" in debug_text
        assert "Already observed in active run: true" in debug_text
        assert (
            run.encounters[
                next(
                    item.location_id
                    for item in PLATINUM_NUZLOCKE_PROFILE.locations
                    if item.name == "Route 202"
                )
            ].species
            == ""
        )
    finally:
        window.close()


def _party_payload(records: tuple[bytes, ...]) -> bytes:
    return (
        len(records).to_bytes(4, "little")
        + b"".join(records)
        + bytes(PARTY_POKEMON_SIZE * (6 - len(records)))
    )


def _party_record(
    pid: int,
    species_id: int,
    ability_id: int,
    *,
    attack: int,
    met_location_id: int = 0,
    met_level: int = 0,
    friendship: int = 0,
) -> bytes:
    box = bytearray(BOX_DATA_SIZE)
    box[0:2] = species_id.to_bytes(2, "little")
    box[0x0C] = friendship
    box[0x0D] = ability_id
    box[0x3E:0x40] = met_location_id.to_bytes(2, "little")
    box[0x57] = 12
    box[0x7C] = met_level
    box[0x30:0x34] = (31 << 5).to_bytes(4, "little")
    checksum = calculate_checksum(bytes(box))

    record = bytearray(PARTY_POKEMON_SIZE)
    record[0:4] = pid.to_bytes(4, "little")
    record[6:8] = checksum.to_bytes(2, "little")
    record[8 : 8 + BOX_DATA_SIZE] = encrypt_box_data(bytes(box), pid, checksum)
    stats = bytearray(0x14)
    stats[4] = 17
    stats[6:8] = (30).to_bytes(2, "little")
    stats[8:10] = (53).to_bytes(2, "little")
    stats[10:12] = attack.to_bytes(2, "little")
    stats[12:14] = (30).to_bytes(2, "little")
    stats[14:16] = (22).to_bytes(2, "little")
    stats[16:18] = (18).to_bytes(2, "little")
    stats[18:20] = (29).to_bytes(2, "little")
    record[0x88:0x9C] = xor_words(bytes(stats), pid)
    return bytes(record)
