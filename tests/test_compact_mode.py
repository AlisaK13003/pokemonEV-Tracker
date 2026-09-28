from __future__ import annotations

import os
import time
from itertools import pairwise
from types import SimpleNamespace
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from pokemon_ev_tracker.config.settings import AppSettings
from pokemon_ev_tracker.core.ev_targets import EVTargetStore
from pokemon_ev_tracker.core.nuzlocke.storage import NuzlockeStore
from pokemon_ev_tracker.data_sources.bizhawk import (
    BizHawkRamDataSource,
    CoordinateCaptureRequest,
)
from pokemon_ev_tracker.games.platinum.coordinate_discovery import CoordinateCandidate
from pokemon_ev_tracker.transport.bizhawk_server import FriendshipWalkCommandReceipt
from pokemon_ev_tracker.ui.main_window import MainWindow
from pokemon_ev_tracker.ui.party_card import PartyCardSize
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

    assert window.tracker_layout.indexOf(
        window.current_opponent_panel
    ) < window.tracker_layout.indexOf(window.party_grid)
    assert window.ev_change_list.minimumHeight() >= 150
    assert window.ev_change_list.maximumHeight() >= 200
    assert window.tracker_layout.indexOf(
        window.friendship_walk_group
    ) < window.tracker_layout.indexOf(window.party_grid)
    window.close()


@pytest.mark.parametrize("transport", ["file", "tcp"])
def test_friendship_walk_waits_for_matching_start_ack_and_stop_is_explicit(
    make_window, transport
) -> None:
    window = make_window(AppSettings(friendship_walk_axis="vertical"))
    payload = SimpleNamespace(
        payload={
            "frame": 120,
            "player_x": 4,
            "player_y": -2,
            "player_coordinates_validated": True,
        },
        source="file",
    )
    window.ram_data_source.snapshot = Mock(
        return_value=SimpleNamespace(
            connected=True,
            details={
                "party_payload": payload,
                "party_payload_fresh": True,
                "active_enemy_battlers": (),
            },
        )
    )
    sender = Mock(
        side_effect=[
            FriendshipWalkCommandReceipt(42, transport),
            FriendshipWalkCommandReceipt(43, f"{transport}+tcp"),
            FriendshipWalkCommandReceipt(44, f"{transport}+tcp"),
        ]
    )
    window.ram_data_source.send_friendship_walk_command = sender

    window._start_friendship_walk()

    assert not window.friendship_walk.active
    assert window.friendship_walk_status_label.text() == "Starting — waiting for Lua acknowledgement"
    sender.assert_called_once_with("START", "vertical")
    assert window.friendship_walk_shortcut.key().toString() == "Ctrl+Shift+W"

    acknowledged = SimpleNamespace(
        payload={
            **payload.payload,
            "frame": 124,
            "friendship_walk_enabled": True,
            "friendship_walk_ack_sequence": 42,
            "friendship_walk_ack_frame": 124,
        },
        source=transport,
    )
    window._refresh_friendship_walk(
        SimpleNamespace(details={"party_payload_fresh": True}), acknowledged, ()
    )

    assert window.friendship_walk.active
    assert window.friendship_walk.status.value == "Walking Up"

    walking = SimpleNamespace(
        payload={
            **acknowledged.payload,
            "frame": 125,
            "player_y": -3,
            "friendship_walk_requested_direction": "Up",
            "friendship_walk_injected_direction": "Up",
        },
        source=transport,
    )
    window._refresh_friendship_walk(
        SimpleNamespace(details={"party_payload_fresh": True}), walking, ()
    )

    assert window.friendship_walk.active
    assert window.friendship_walk.successful_moves == 1

    window._stop_friendship_walk()

    assert not window.friendship_walk.active
    assert sender.call_args_list[-1].args == ("STOP", None)
    assert window.friendship_walk_status_label.text() == "Idle"
    window.close()


def test_friendship_walk_debug_reports_frame_axis_and_input_state(make_window) -> None:
    window = make_window()
    window.friendship_walk.start("horizontal", 90, 8, 12)
    window.friendship_walk.update(95, 8, 12)
    payload = SimpleNamespace(
        payload={
            "frame": 95,
            "player_x": 8,
            "player_y": 12,
            "player_coordinates_validated": True,
            "friendship_walk_enabled": True,
            "friendship_walk_requested_direction": "Left",
            "friendship_walk_injected_direction": "Left",
            "friendship_walk_b_injected": True,
            "friendship_walk_status": "Walking Left",
            "friendship_walk_reversal_until_frame": None,
        },
        source="file",
        received_at=time.monotonic(),
    )

    lines = window._friendship_walk_transport_debug_lines(payload, True)

    assert "Mode: Horizontal (X)" in lines
    assert "Current direction: LEFT" in lines
    assert "Injected direction: LEFT" in lines
    assert "B injected: True" in lines
    assert "Friendship Walk enabled: True" in lines
    assert "Lua walk status: Walking Left" in lines
    assert "Relevant axis value: 8" in lines
    assert "Last axis change frame: 90" in lines
    assert "Current emulator frame: 95" in lines
    assert "Frames since axis change: 5" in lines
    assert "Blocked timeout: 36 frames" in lines
    assert "Reversal grace: 0 / 20 frames" in lines
    assert "Successful moves since reversal: 0 / 2" in lines
    assert "Wall detection armed: True" in lines
    assert "State: MOVING_CONFIRMED" in lines
    window.close()


def test_stationary_file_payload_frames_trigger_wall_reversal(make_window) -> None:
    window = make_window()
    window.friendship_walk.start("horizontal", 100, 8, 12)
    sender = Mock(return_value=FriendshipWalkCommandReceipt(51, "file"))
    window.ram_data_source.send_friendship_walk_command = sender

    for frame in (110, 120, 130, 136):
        payload = SimpleNamespace(
            payload={
                "frame": frame,
                "player_x": 8,
                "player_y": 12,
                "player_coordinates_validated": True,
                "friendship_walk_enabled": True,
                "friendship_walk_injected_direction": "Left",
            },
            source="file",
        )
        window._refresh_friendship_walk(
            SimpleNamespace(details={"party_payload_fresh": True}), payload, ()
        )

    assert window.friendship_walk.direction.value == "Right"
    assert window.friendship_walk.status.value == "Blocked — reversing"
    assert window.friendship_walk.successful_moves == 0
    assert sender.call_args_list[-1].args == ("DIRECTION", "Right")
    window.close()


def test_tracker_restart_sends_stop_if_lua_reports_an_active_walk(make_window) -> None:
    window = make_window()
    payload = SimpleNamespace(
        payload={
            "frame": 150,
            "player_x": 4,
            "player_y": -2,
            "player_coordinates_validated": True,
            "friendship_walk_enabled": True,
        },
        source="file",
    )
    sender = Mock(return_value=FriendshipWalkCommandReceipt(77, "file"))
    window.ram_data_source.send_friendship_walk_command = sender
    snapshot = SimpleNamespace(
        connected=True,
        details={"party_payload_fresh": True},
    )

    window._refresh_friendship_walk(snapshot, payload, ())
    window._refresh_friendship_walk(snapshot, payload, ())

    sender.assert_called_once_with("STOP", None)
    assert not window.friendship_walk.active
    window.close()


def test_friendship_walk_start_requires_fresh_party_ram_not_heartbeat(make_window) -> None:
    window = make_window()
    payload = SimpleNamespace(
        payload={
            "frame": 120,
            "player_x": 4,
            "player_y": -2,
            "player_coordinates_validated": True,
        },
        source="file",
    )
    window.ram_data_source.snapshot = Mock(
        return_value=SimpleNamespace(
            connected=False,
            details={
                "party_payload": payload,
                "party_payload_fresh": True,
                "active_enemy_battlers": (),
            },
        )
    )
    sender = Mock(return_value=FriendshipWalkCommandReceipt(123, "file"))
    window.ram_data_source.send_friendship_walk_command = sender

    window._start_friendship_walk()

    assert window.friendship_walk_status_label.text() == "Starting — waiting for Lua acknowledgement"
    sender.assert_called_once_with("START", "horizontal")
    window.close()


def test_active_walk_uses_fresh_party_ram_even_if_heartbeat_is_stale(make_window) -> None:
    window = make_window()
    window.friendship_walk.start("horizontal", 120, 4, -2)
    window.ram_data_source.send_friendship_walk_command = Mock(
        return_value=FriendshipWalkCommandReceipt(124, "file")
    )
    payload = SimpleNamespace(
        payload={
            "frame": 121,
            "player_x": 4,
            "player_y": -2,
            "player_coordinates_validated": True,
            "friendship_walk_enabled": True,
            "friendship_walk_ack_sequence": 123,
        },
        source="file",
    )

    window._refresh_friendship_walk(
        SimpleNamespace(connected=False, details={"party_payload_fresh": True}),
        payload,
        (),
    )

    assert window.friendship_walk.active
    assert window.friendship_walk.status.value == "Walking Left"
    window.close()


@pytest.mark.parametrize("direction", ["Left", "Right", "Up", "Down"])
def test_injected_directions_do_not_pause_the_tracker_walk(make_window, direction) -> None:
    window = make_window()
    window.friendship_walk.start("horizontal", 100, 4, -2)
    window._last_walk_ping_at = time.monotonic()
    payload = SimpleNamespace(
        payload={
            "frame": 101,
            "player_x": 5,
            "player_y": -2,
            "player_coordinates_validated": True,
            "friendship_walk_enabled": True,
            "friendship_walk_requested_direction": direction,
            "friendship_walk_injected_direction": direction,
        },
        source="file",
    )

    window._refresh_friendship_walk(
        SimpleNamespace(details={"party_payload_fresh": True}), payload, ()
    )

    assert window.friendship_walk.active
    assert window.friendship_walk.successful_moves == 1
    window.close()


def test_walk_shortcut_stops_and_requests_input_release(make_window) -> None:
    window = make_window()
    window.friendship_walk.start("horizontal", 100, 4, -2)
    sender = Mock(return_value=FriendshipWalkCommandReceipt(700, "file+tcp"))
    window.ram_data_source.send_friendship_walk_command = sender

    window.friendship_walk_shortcut.activated.emit()

    assert not window.friendship_walk.active
    assert window.friendship_walk.direction is None
    assert window.friendship_walk.status.value == "Idle"
    sender.assert_called_once_with("STOP", None)
    window.close()


def test_friendship_walk_start_ignores_ack_from_before_start(make_window) -> None:
    window = make_window()
    window._walk_unacked_since = time.monotonic() - 20
    payload = SimpleNamespace(
        payload={
            "frame": 120,
            "player_x": 4,
            "player_y": -2,
            "player_coordinates_validated": True,
            "friendship_walk_ack_sequence": 122,
            "friendship_walk_enabled": False,
        },
        source="file",
    )
    window.ram_data_source.snapshot = Mock(
        return_value=SimpleNamespace(
            connected=True,
            details={
                "party_payload": payload,
                "party_payload_fresh": True,
                "active_enemy_battlers": (),
            },
        )
    )
    window.ram_data_source.send_friendship_walk_command = Mock(
        return_value=FriendshipWalkCommandReceipt(123, "file")
    )

    window._start_friendship_walk()
    assert window._walk_unacked_since > time.monotonic() - 3
    window._refresh_friendship_walk(
        SimpleNamespace(details={"party_payload_fresh": True}), payload, ()
    )

    assert not window.friendship_walk.active
    assert window._friendship_walk_pending_sequence == 123
    assert window.friendship_walk_status_label.text() == "Starting — waiting for Lua acknowledgement"
    window.close()


def test_missing_start_ack_reports_command_channel_unavailable(make_window) -> None:
    import time

    window = make_window()
    payload = SimpleNamespace(
        payload={
            "frame": 120,
            "player_x": 4,
            "player_y": -2,
            "player_coordinates_validated": True,
        },
        source="file",
    )
    window.ram_data_source.snapshot = Mock(
        return_value=SimpleNamespace(
            connected=True,
            details={
                "party_payload": payload,
                "party_payload_fresh": True,
                "active_enemy_battlers": (),
            },
        )
    )
    window.ram_data_source.send_friendship_walk_command = Mock(
        return_value=FriendshipWalkCommandReceipt(500, "file")
    )

    window._start_friendship_walk()
    window._friendship_walk_ack_deadline = time.monotonic() - 1
    window._refresh_friendship_walk(
        SimpleNamespace(details={"party_payload_fresh": True}), payload, ()
    )

    assert not window.friendship_walk.active
    assert window.friendship_walk.status.value == (
        "Paused — Movement command channel unavailable"
    )
    window.close()


def test_stale_walk_ack_pauses_command_channel_without_marking_ram_lost(make_window) -> None:
    window = make_window()
    window.friendship_walk.start("horizontal", 100, 4, -2)
    window._walk_unacked_since = __import__("time").monotonic() - 5
    window._walk_last_command_sequence = 42
    window._walk_command_transport = "file"
    payload = SimpleNamespace(
        payload={
            "frame": 101,
            "player_x": 4,
            "player_y": -2,
            "player_coordinates_validated": True,
            "friendship_walk_enabled": True,
            "friendship_walk_ack_sequence": 41,
        },
        source="file",
    )
    window.ram_data_source.send_friendship_walk_command = Mock(
        return_value=FriendshipWalkCommandReceipt(43, "file")
    )

    window._refresh_friendship_walk(
        SimpleNamespace(details={"party_payload_fresh": True}), payload, ()
    )

    assert not window.friendship_walk.active
    assert window.friendship_walk.status.value == "Paused — Movement command channel lost"
    window.close()


def test_stale_party_ram_pauses_with_ram_specific_status(make_window) -> None:
    window = make_window()
    window.ram_data_source.snapshot = Mock(
        return_value=SimpleNamespace(
            connected=False,
            details={
                "party_payload": None,
                "party_payload_fresh": False,
                "active_enemy_battlers": (),
            },
        )
    )

    window._start_friendship_walk()

    assert window.friendship_walk.status.value == "Paused — RAM connection lost"
    window.close()


def test_coordinate_discovery_is_collapsed_under_advanced_debug(make_window) -> None:
    window = make_window()

    assert window.coordinate_discovery_group.isCheckable()
    assert not window.coordinate_discovery_group.isChecked()
    assert window.coordinate_discovery_contents.isHidden()
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


def test_ram_debug_coordinate_candidate_selection_requests_live_preview(make_window) -> None:
    window = make_window()
    candidate = CoordinateCandidate(
        x_offset=0x220,
        y_offset=0x222,
        data_type="u16",
        score=0.98,
        idle_stability=1.0,
        right_delta=1,
        left_delta=-1,
        down_delta=1,
        up_delta=-1,
        x_values=(10, 10, 11, 10, 10, 10),
        y_values=(7, 7, 7, 7, 8, 7),
    )
    window.coordinate_discovery.candidates = (candidate,)
    window._render_coordinate_candidates()
    preview = Mock()
    window.ram_data_source.set_coordinate_preview = preview

    window.coordinate_candidate_combo.setCurrentIndex(1)

    preview.assert_called_once_with(0x220, 0x222, "u16")
    assert "live gameplay validation" in window.coordinate_candidate_details.text()
    window.close()


def test_coordinate_capture_ui_reports_file_source_without_tcp_requirement(make_window) -> None:
    window = make_window()
    request = Mock(return_value=CoordinateCaptureRequest(True, source="file"))
    window.ram_data_source.request_coordinate_capture = request
    window.coordinate_discovery_group.setChecked(True)

    window.coordinate_capture_buttons["baseline"].click()

    request.assert_called_once()
    assert "via file" in window.coordinate_discovery_status.text()
    assert "TCP" not in window.coordinate_discovery_status.text()
    window.close()


def test_compact_ev_change_includes_pokemon_identity(make_window) -> None:
    window = make_window()
    before = {
        "hp": 0,
        "attack": 0,
        "defense": 0,
        "special_attack": 0,
        "special_defense": 0,
        "speed": 0,
    }
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


def test_compact_party_cards_use_small_size_and_wrap_to_fit(make_window) -> None:
    app = QApplication.instance()
    window = make_window()
    window.show()
    app.processEvents()
    window.party_grid.arrange(tuple(SimpleNamespace(slot=slot) for slot in range(1, 7)))
    window.party_grid.show()
    window.set_compact_mode(True)
    app.processEvents()

    for width, expected_columns in ((1000, 3), (800, 3), (600, 2), (400, 1)):
        window.resize(width, 700)
        app.processEvents()
        assert window.party_grid.card_size is PartyCardSize.SMALL
        assert window.party_grid.columns == expected_columns, (
            f"window={window.width()} grid={window.party_grid.width()} "
            f"viewport={window.tracker_scroll_area.viewport().width()}"
        )
        cards = [
            card["widget"]
            for card in window.tracker_party_cards.values()
            if not card["widget"].isHidden()
        ]
        rows = [
            cards[index : index + expected_columns]
            for index in range(0, len(cards), expected_columns)
        ]
        assert len({row[0].geometry().x() for row in rows}) == 1
        assert max(card.geometry().right() for card in cards) <= window.party_grid.width()
        assert (
            window.party_grid.x() + rows[0][-1].geometry().right() + 1
            <= window.tracker_scroll_area.viewport().width()
        )
        for row in rows:
            for previous, following in pairwise(row):
                assert (
                    following.geometry().x()
                    - previous.geometry().x()
                    - previous.geometry().width()
                ) == window.party_grid.HORIZONTAL_SPACING
        for card in cards:
            assert card.width() == PartyCardSize.SMALL.preferred_width

    window._geometry_save_timer.stop()
    window.close()


def test_muted_tracker_labels_keep_readable_dark_theme_contrast(make_window) -> None:
    window = make_window()
    card = window.tracker_party_cards[1]

    assert card["item_name"].property("uiRole") == "muted"
    assert card["target_summary"].property("targetSeverity") == "normal"
    assert all(
        label.property("natureRole") in (None, "neutral")
        for label in card["ev_stat_names"].values()
    )
    assert "QLabel[uiRole=\"muted\"]" in window.styleSheet()
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
