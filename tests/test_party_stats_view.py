from __future__ import annotations

import os
from dataclasses import replace
from itertools import pairwise

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPoint, Qt
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
from pokemon_ev_tracker.ui.party_card import PartyCardSize


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


@pytest.mark.parametrize("compact", [False, True])
def test_ram_warning_footer_never_reflows_tracker_controls(make_window, compact) -> None:
    app = QApplication.instance()
    window = make_window()
    window.resize(640, 520)
    if compact:
        window.set_compact_mode(True)
    window.show()
    app.processEvents()

    valid_state = decode_party(_party_payload((_party_record(0x12345678, 183, 47, attack=27),)))
    warning_text = (
        "RAM checksum failed for slot(s) 3; showing the last valid matching-PID sample. "
        "This full message remains available in the status tooltip."
    )
    warning_state = replace(valid_state, live_read_warning=warning_text)
    window._refresh_tracker_party(True, valid_state)
    app.processEvents()
    start_button = window.start_friendship_walk_button
    original_y = start_button.mapToGlobal(QPoint(0, 0)).y()

    window._refresh_tracker_party(True, warning_state)
    app.processEvents()
    assert start_button.mapToGlobal(QPoint(0, 0)).y() == original_y
    assert window.statusBar().isAncestorOf(window.tracker_status_message)
    assert window.tracker_layout.indexOf(window.tracker_status_message) == -1
    assert not window.tracker_status_message.wordWrap()
    assert window.tracker_status_message.toolTip() == warning_text
    assert window.statusBar().height() == 26
    if compact:
        assert window.tracker_status_message.text() == "⚠ RAM checksum warning"

    window._refresh_tracker_party(True, valid_state)
    app.processEvents()
    assert start_button.mapToGlobal(QPoint(0, 0)).y() == original_y
    assert window.tracker_status_message.text() == "BizHawk RAM • CONNECTED"
    assert window.tracker_status_message.toolTip() == ""
    window.close()


def test_tracker_cards_reflow_and_scroll_at_desktop_breakpoints(make_window) -> None:
    app = QApplication.instance()
    window = make_window()
    window.show()
    party = decode_party(
        _party_payload(
            tuple(
                _party_record(0x1000 + slot, 183 + slot, 47, attack=20 + slot)
                for slot in range(6)
            )
        )
    )
    window._refresh_tracker_party(True, party)

    expected_layouts = (
        (1400, PartyCardSize.LARGE, 3),
        (1000, PartyCardSize.MEDIUM, 3),
        (800, PartyCardSize.SMALL, 3),
        (600, PartyCardSize.SMALL, 2),
    )
    for width, card_size, columns in expected_layouts:
        window.resize(width, 500)
        app.processEvents()
        assert window.party_grid.card_size is card_size
        assert window.party_grid.columns == columns, (
            f"window={window.width()} page={window.tracker_scroll_area.widget().width()} "
            f"grid={window.party_grid.width()} viewport="
            f"{window.tracker_scroll_area.viewport().width()}"
        )
        assert window.tracker_scroll_area.horizontalScrollBarPolicy() == (
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        visible_cards = [
            card["widget"]
            for card in window.tracker_party_cards.values()
            if not card["widget"].isHidden()
        ]
        assert len(visible_cards) == 6
        assert max(card.geometry().right() for card in visible_cards) <= window.party_grid.width()

        rows = [
            visible_cards[index : index + columns]
            for index in range(0, len(visible_cards), columns)
        ]
        assert len({row[0].geometry().x() for row in rows}) == 1
        for row in rows:
            assert all(
                card_size.minimum_width
                <= card.width()
                <= card_size.preferred_width
                for card in row
            )
            for previous, following in pairwise(row):
                assert (
                    following.geometry().x()
                    - previous.geometry().x()
                    - previous.geometry().width()
                ) == window.party_grid.HORIZONTAL_SPACING
        for previous_row, following_row in pairwise(rows):
            previous_bottom = max(
                card.geometry().y() + card.geometry().height()
                for card in previous_row
            )
            assert (
                following_row[0].geometry().y() - previous_bottom
            ) == window.party_grid.VERTICAL_SPACING

    assert window.tracker_scroll_area.widgetResizable()
    assert window.tracker_scroll_area.verticalScrollBar().maximum() > 0
    window._geometry_save_timer.stop()
    window.close()


def test_small_cards_collapse_details_but_keep_ev_summary(make_window) -> None:
    app = QApplication.instance()
    window = make_window()
    window.resize(600, 500)
    window.show()
    party = decode_party(_party_payload((_party_record(0x1234, 183, 47, attack=20),)))
    window._refresh_tracker_party(True, party)
    app.processEvents()

    card = window.tracker_party_cards[1]
    assert card["card_size"] is PartyCardSize.SMALL
    assert card["sprite"].width() == PartyCardSize.SMALL.sprite_size
    assert not card["ev_section"].is_expanded
    assert card["total"].isVisible()
    assert card["total_bar"].isVisible()

    window.set_tracker_view("stats")
    app.processEvents()
    assert not card["stats_section"].is_expanded
    assert not card["moves_section"].is_expanded
    assert not card["friendship_section"].is_expanded

    window.resize(1000, 650)
    app.processEvents()
    assert card["card_size"] is PartyCardSize.MEDIUM
    assert card["stats_section"].is_expanded
    assert card["friendship_section"].is_expanded
    window._geometry_save_timer.stop()
    window.close()


def test_party_sections_collapse_and_ev_log_scrolls_internally(make_window) -> None:
    app = QApplication.instance()
    window = make_window()
    window.resize(900, 650)
    window.show()
    party_state = decode_party(
        _party_payload((_party_record(3, 183, 47, attack=27),))
    )
    window._refresh_tracker_party(True, party_state)
    app.processEvents()
    card = window.tracker_party_cards[1]
    expanded_height = card["widget"].sizeHint().height()
    card["ev_section"].toggle.click()
    app.processEvents()
    assert card["ev_section"].content.isHidden()
    assert card["widget"].sizeHint().height() < expanded_height

    records = [
        (f"15:42:{index:02d}   sheepy   Attack 0 -> 1   +1", "+1 Attack")
        for index in range(80)
    ]
    window._ev_history_records = records
    window._render_ev_history()
    app.processEvents()
    assert window.ev_change_list.maximumHeight() <= 230
    assert window.ev_change_list.verticalScrollBar().maximum() > 0
    window._geometry_save_timer.stop()
    window.close()


@pytest.mark.parametrize("width", (700, 900, 1400))
def test_party_stats_accordions_grow_to_show_all_content(make_window, width: int) -> None:
    app = QApplication.instance()
    window = make_window()
    window.resize(width, 520)
    window.show()
    party_state = decode_party(
        _party_payload((_party_record(0x12345678, 183, 47, attack=27),))
    )
    window._refresh_tracker_party(True, party_state)
    window.set_tracker_view("stats")
    app.processEvents()

    card = window.tracker_party_cards[1]
    card["moves_list"].setText("Quick Attack\nGrowl\nPound\nThunderbolt")
    sections = ("stats_section", "moves_section", "friendship_section")
    for key in sections:
        card[key].toggle.setChecked(False)
    app.processEvents()
    previous_height = card["widget"].height()

    for key in sections:
        card[key].toggle.setChecked(True)
        app.processEvents()
        assert card["widget"].height() > previous_height
        previous_height = card["widget"].height()

    stats = card["stats_section"]
    assert stats.content.height() >= stats.content.sizeHint().height()
    assert all(
        label.isVisible() and label.geometry().bottom() < stats.content.height()
        for label in card["stat_names"].values()
    )
    assert card["moves_list"].text().splitlines() == [
        "Quick Attack", "Growl", "Pound", "Thunderbolt"
    ]
    assert card["moves_list"].height() >= card["moves_list"].sizeHint().height()
    assert card["friendship_bar"].isVisible()
    assert card["friendship_bar"].geometry().height() > 0
    assert window.tracker_scroll_area.verticalScrollBar().maximum() > 0

    window.set_tracker_view("training")
    app.processEvents()
    card["ev_section"].toggle.setChecked(False)
    card["target_section"].toggle.setChecked(False)
    app.processEvents()
    training_height = card["widget"].height()
    card["ev_section"].toggle.setChecked(True)
    app.processEvents()
    ev_height = card["widget"].height()
    assert ev_height > training_height
    card["target_section"].toggle.setChecked(True)
    app.processEvents()
    assert card["widget"].height() > ev_height
    window.close()


def test_party_card_header_stays_compact_when_window_grows(make_window) -> None:
    app = QApplication.instance()
    window = make_window()
    window.resize(900, 520)
    window.show()
    party_state = decode_party(
        _party_payload((_party_record(0x12345678, 183, 47, attack=27),))
    )
    window._refresh_tracker_party(True, party_state)
    window.set_tracker_view("stats")
    app.processEvents()

    card = window.tracker_party_cards[1]
    assert card["item_name"].text() == "No held item"
    assert card["item_name"].height() <= 24
    header = card["widget"].layout().itemAt(0).geometry()
    header_height = header.height()
    stats_top = card["widget"].layout().itemAt(2).geometry().top()
    assert 0 <= stats_top - header.bottom() - 1 <= 12

    window.resize(900, 820)
    app.processEvents()
    new_header = card["widget"].layout().itemAt(0).geometry()
    assert new_header.height() == header_height
    assert card["widget"].height() == card["widget"].sizeHint().height()
    window.close()


def test_party_grid_keeps_card_heights_independent_and_rows_below_tallest(make_window) -> None:
    app = QApplication.instance()
    window = make_window()
    window.resize(1400, 600)
    window.show()
    party_state = decode_party(
        _party_payload(
            tuple(
                _party_record(0x1000 + slot, 183 + slot, 47, attack=20 + slot)
                for slot in range(1, 7)
            )
        )
    )
    window._refresh_tracker_party(True, party_state)
    window.set_tracker_view("stats")
    app.processEvents()

    first = [window.tracker_party_cards[slot] for slot in (1, 2, 3)]
    for card in first:
        for key in ("stats_section", "moves_section", "friendship_section"):
            card[key].toggle.setChecked(False)
    first[1]["stats_section"].toggle.setChecked(True)
    first[2]["moves_list"].setText("Move 1\nMove 2\nMove 3\nMove 4")
    first[2]["moves_section"].toggle.setChecked(True)
    first[2]["friendship_section"].toggle.setChecked(True)
    app.processEvents()

    heights = [card["widget"].height() for card in first]
    assert len(set(heights)) > 1
    second_row_y = window.tracker_party_cards[4]["widget"].geometry().top()
    tallest_bottom = max(
        card["widget"].geometry().bottom() for card in first
    )
    assert second_row_y == tallest_bottom + 1 + window.party_grid.VERTICAL_SPACING
    assert window.party_grid._grid.rowStretch(0) == 0
    assert window.party_grid._grid.rowStretch(1) == 0
    window.close()


def test_nuzlocke_tables_remain_locally_scrollable_at_narrow_width(make_window) -> None:
    app = QApplication.instance()
    window = make_window()
    window.nuzlocke_view.store.create_run("Narrow layout", PLATINUM_NUZLOCKE_PROFILE)
    window.nuzlocke_view._refresh_all()
    window.resize(620, 500)
    window.show()
    window.main_tabs.setCurrentIndex(2)
    app.processEvents()

    assert window.nuzlocke_scroll_area.widgetResizable()
    assert window.nuzlocke_scroll_area.horizontalScrollBarPolicy() == (
        Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    )
    assert window.nuzlocke_view.encounters_table.horizontalScrollBar().maximum() > 0
    window._geometry_save_timer.stop()
    window.close()


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
    assert card["stat_names"]["attack"].property("natureRole") == "up"
    assert card["stat_names"]["special_attack"].property("natureRole") == "down"
    assert card["stat_names"]["hp"].property("natureRole") == "neutral"
    window.close()


def test_party_stats_renders_friendship_and_debug_value(make_window) -> None:
    window = make_window()
    window.set_tracker_view("stats")
    party_state = decode_party(
        _party_payload(
            (
                _party_record(
                    3,
                    183,
                    47,
                    attack=27,
                    friendship=164,
                    moves=(98, 45, 0, 1),
                ),
            )
        )
    )

    window._refresh_tracker_party(True, party_state)
    window._refresh_ram_party_debug(party_state, None)
    card = window.tracker_party_cards[1]

    assert not card["stats_content"].isHidden()
    assert card["friendship"].text() == "Friendship: 164 / 255 • High"
    assert card["friendship_bar"].maximum() == 255
    assert card["friendship_bar"].value() == 164
    assert card["moves_list"].text().splitlines() == ["Quick Attack", "Growl", "Pound"]
    assert "Friendship: 164" in window.ram_party_details.toPlainText()
    window.close()


def test_party_stats_moves_update_live_from_ram(make_window) -> None:
    window = make_window()
    window.set_tracker_view("stats")
    first = decode_party(
        _party_payload(
            (_party_record(3, 183, 47, attack=27, moves=(98, 45, 0, 1)),)
        )
    )
    updated = decode_party(
        _party_payload(
            (_party_record(3, 183, 47, attack=27, moves=(85, 44, 0, 1)),)
        )
    )

    window._refresh_tracker_party(True, first)
    card = window.tracker_party_cards[1]
    original_label = card["moves_list"]
    window._refresh_tracker_party(True, updated)

    assert card["moves_list"] is original_label
    assert card["moves_list"].text().splitlines() == ["Thunderbolt", "Bite", "Pound"]
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
    moves: tuple[int, int, int, int] = (0, 0, 0, 0),
) -> bytes:
    box = bytearray(BOX_DATA_SIZE)
    box[0:2] = species_id.to_bytes(2, "little")
    box[0x0C] = friendship
    box[0x0D] = ability_id
    for index, move_id in enumerate(moves):
        offset = 0x20 + index * 2
        box[offset : offset + 2] = move_id.to_bytes(2, "little")
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
