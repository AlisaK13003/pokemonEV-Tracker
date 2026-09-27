from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from pokemon_ev_tracker.config.settings import AppSettings
from pokemon_ev_tracker.core.ev_targets import EVTargetStore
from pokemon_ev_tracker.data_sources.bizhawk import BizHawkRamDataSource
from pokemon_ev_tracker.games.platinum.decoder import decode_party
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
) -> bytes:
    box = bytearray(BOX_DATA_SIZE)
    box[0:2] = species_id.to_bytes(2, "little")
    box[0x0D] = ability_id
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
