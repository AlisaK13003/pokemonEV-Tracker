from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from pokemon_ev_tracker.config.settings import AppSettings
from pokemon_ev_tracker.core.ev_targets import EVTargetStore
from pokemon_ev_tracker.core.nuzlocke.storage import NuzlockeStore
from pokemon_ev_tracker.data_sources.bizhawk import BizHawkRamDataSource
from pokemon_ev_tracker.ui.main_window import MainWindow
from pokemon_ev_tracker.ui.party_layout import party_card_positions


@pytest.fixture
def make_window(monkeypatch, tmp_path):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(BizHawkRamDataSource, "start", lambda self: None)
    monkeypatch.setattr(BizHawkRamDataSource, "stop", lambda self: None)
    monkeypatch.setattr(AppSettings, "save_default", lambda self: None)

    def create(settings: AppSettings | None = None) -> MainWindow:
        window = MainWindow(
            settings or AppSettings(),
            target_store=EVTargetStore(tmp_path / "ev_targets.json"),
            nuzlocke_store=NuzlockeStore(tmp_path / "nuzlocke_runs.json"),
        )
        return window

    yield create
    assert app is not None


def test_compact_mode_sets_always_on_top_hides_debug_and_restores_normal(make_window) -> None:
    window = make_window()
    window.resize(920, 700)
    window.main_tabs.setCurrentIndex(1)
    normal_geometry = window._current_window_geometry()

    window.set_compact_mode(True)

    assert window.compact_mode
    assert window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    assert window.main_tabs.currentIndex() == 0
    assert window.main_tabs.tabBar().isHidden()
    assert not window.main_tabs.isTabVisible(1)
    assert not window.main_tabs.isTabVisible(2)
    assert window.settings.normal_window_geometry == normal_geometry
    assert window.tracker_title.isHidden()
    assert not window.compact_status_label.isHidden()

    window.set_compact_mode(False)

    assert not window.compact_mode
    assert not window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    assert not window.main_tabs.tabBar().isHidden()
    assert window.main_tabs.isTabVisible(1)
    assert window.main_tabs.isTabVisible(2)
    assert window.main_tabs.currentIndex() == 1
    assert window._current_window_geometry() == normal_geometry
    window.close()


def test_compact_toggle_keeps_visible_window_visible(make_window) -> None:
    app = QApplication.instance()
    window = make_window()
    window.show()
    app.processEvents()
    assert window.isVisible()

    window.set_compact_mode(True)
    app.processEvents()
    assert window.isVisible()

    window.set_compact_mode(False)
    app.processEvents()
    assert window.isVisible()
    window.close()


def test_saved_compact_mode_and_geometry_are_applied_on_startup(make_window) -> None:
    settings = AppSettings(
        compact_mode=True,
        window_geometry=(40, 50, 600, 430),
        normal_window_geometry=(70, 80, 1000, 720),
    )

    window = make_window(settings)

    assert window.compact_mode
    assert window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    assert window.main_tabs.tabBar().isHidden()
    assert window.width() == 600
    assert window.height() == 430
    window.close()


def test_compact_history_shows_four_recent_entries_and_normal_restores_full_text(
    make_window,
) -> None:
    window = make_window()
    window._ev_history_records = [
        (
            f"15:42:0{index}  sheepy (Mareep) Attack 0 -> {index}  +{index}",
            f"+{index} Attack — sheepy (Mareep)",
        )
        for index in range(1, 7)
    ]
    window._render_ev_history()
    assert window.ev_change_list.count() == 6

    window.set_compact_mode(True)
    assert window.ev_change_list.count() == 4
    assert window.ev_change_list.minimumHeight() == 112
    assert window.ev_change_list.item(0).text() == "+3 Attack — sheepy (Mareep)"
    assert window.ev_change_list.item(3).text() == "+6 Attack — sheepy (Mareep)"

    window.set_compact_mode(False)
    assert window.ev_change_list.count() == 6
    assert window.ev_change_list.item(0).text().startswith("15:42:01")
    window.close()


def test_tracker_places_opponent_above_party_and_gives_log_room_for_multiple_rows(
    make_window,
) -> None:
    window = make_window()

    assert window.tracker_layout.indexOf(window.current_opponent_panel) < window.tracker_layout.indexOf(
        window.party_grid
    )
    assert window.ev_change_list.minimumHeight() >= 150
    assert window.ev_change_list.maximumHeight() >= 200
    window.close()


def test_ram_debug_updates_preserve_manual_scroll_position(make_window) -> None:
    app = QApplication.instance()
    window = make_window()
    window.main_tabs.setCurrentIndex(1)
    window.show()
    lines = [f"RAM diagnostic row {index:03d}: value 0000" for index in range(120)]
    window._set_ram_party_debug_text("\n".join(lines))
    app.processEvents()

    scroll_bar = window.ram_party_details.verticalScrollBar()
    assert scroll_bar.maximum() > 30
    scroll_bar.setValue(20)
    app.processEvents()
    lines[0] = "RAM diagnostic row 000: value 0001"

    window._set_ram_party_debug_text("\n".join(lines))

    assert scroll_bar.value() == 20
    window.close()


def test_compact_ev_change_includes_pokemon_identity(make_window) -> None:
    window = make_window()
    before = {"hp": 0, "attack": 0, "defense": 0, "special_attack": 0,
              "special_defense": 0, "speed": 0}
    after = {**before, "attack": 1}

    def party(evs):
        pokemon = SimpleNamespace(
            slot=1,
            species="Mareep",
            nickname="sheepy",
            checksum_valid=True,
            evs=evs,
            decoded=SimpleNamespace(diagnostics=SimpleNamespace(pid=1234)),
        )
        return SimpleNamespace(party_count_valid=True, pokemon=(pokemon,))

    window._record_ev_changes(party(before))
    window._record_ev_changes(party(after))

    assert window._ev_history_records[-1][1] == "+1 Attack — sheepy (Mareep)"
    window.set_compact_mode(True)
    assert window.ev_change_list.item(0).text() == "+1 Attack — sheepy (Mareep)"
    window.close()


def test_party_layout_keeps_three_columns_for_one_through_six_members() -> None:
    for count in range(1, 7):
        positions = party_card_positions(count)
        assert max(column for _row, column in positions) < 3
        assert all(row < 2 for row, _column in positions)


def test_compact_window_sizes_cover_one_through_six_members(make_window) -> None:
    window = make_window()
    window.set_compact_mode(True)
    sizes = {}
    for count in range(1, 7):
        window._resize_compact_window(count)
        sizes[count] = (window.width(), window.height())

    assert all(width >= 320 for width, _height in sizes.values())
    assert sizes[1][0] < sizes[2][0] < sizes[3][0]
    assert sizes[3][0] == sizes[4][0] == sizes[5][0] == sizes[6][0]
    assert sizes[1][1] == sizes[3][1]
    assert sizes[4][1] == sizes[6][1]
    assert sizes[4][1] > sizes[3][1]
    window.close()


def test_muted_tracker_labels_keep_readable_dark_theme_contrast(make_window) -> None:
    window = make_window()
    card = window.tracker_party_cards[1]

    assert "#b9c2cc" in card["item_name"].styleSheet()
    assert "#b9c2cc" in card["target_summary"].styleSheet()
    assert all("#d7dce2" in label.styleSheet() for label in card["ev_stat_names"].values())
    window.close()


def test_party_stats_compact_mode_keeps_stats_visible_and_log_hidden(make_window) -> None:
    window = make_window()
    window.set_tracker_view("stats")
    window.set_compact_mode(True)

    assert window.tracker_view_buttons["stats"].isChecked()
    assert window.tracker_party_cards[1]["stats_content"].isHidden() is False
    assert window.tracker_party_cards[1]["training_content"].isHidden()
    assert window.ev_change_log.isHidden()
    assert window.compact_mode
    window.close()


def test_compact_mode_hides_nuzlocke_and_restores_its_tab(make_window) -> None:
    window = make_window()
    window.main_tabs.setCurrentIndex(2)

    window.set_compact_mode(True)
    assert not window.main_tabs.isTabVisible(2)
    assert window.main_tabs.currentIndex() == 0

    window.set_compact_mode(False)
    assert window.main_tabs.isTabVisible(2)
    assert window.main_tabs.currentIndex() == 2
    window.close()
