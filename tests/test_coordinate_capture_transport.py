from __future__ import annotations

import json
import time

from pokemon_ev_tracker.data_sources.bizhawk import BizHawkRamDataSource
from pokemon_ev_tracker.transport.bizhawk_server import (
    BizHawkDebugServer,
    BizHawkHeartbeat,
)


def _file_connected_source(tmp_path, *, age: float = 0.0):
    server = BizHawkDebugServer(fallback_file=tmp_path / "tracker.jsonl")
    received_at = time.monotonic() - age
    server._heartbeat = BizHawkHeartbeat(
        received_at,
        {"type": "heartbeat", "frame": 100},
        "file",
    )
    server._party_payload = BizHawkHeartbeat(
        received_at,
        {"type": "party_memory", "party_count": 1},
        "file",
    )
    return BizHawkRamDataSource(server=server), server


def test_fresh_file_fallback_can_request_coordinate_capture(tmp_path) -> None:
    source, server = _file_connected_source(tmp_path)

    result = source.request_coordinate_capture("capture-1", "baseline", 0, 0x400000)

    assert result.accepted
    assert result.source == "file"
    assert server.command_file.read_text(encoding="ascii") == (
        "CAPTURE|capture-1|baseline|0|4194304\n"
    )
    assert server._coordinate_file_capture_id == "capture-1"


def test_fresh_file_fallback_can_select_live_preview(tmp_path) -> None:
    source, server = _file_connected_source(tmp_path)

    assert source.set_coordinate_preview(0x220, 0x222, "s16")
    assert server.command_file.read_text(encoding="ascii") == "PREVIEW|544|546|s16\n"


def test_stale_file_snapshot_is_rejected_with_transport_neutral_message(tmp_path) -> None:
    source, _server = _file_connected_source(tmp_path, age=10.0)

    result = source.request_coordinate_capture("capture-1", "right", 0, 0x10000)

    assert not result.accepted
    assert result.reason == "No fresh BizHawk RAM snapshot available."


def test_file_coordinate_response_reads_only_complete_lines(tmp_path) -> None:
    _source, server = _file_connected_source(tmp_path)
    server._coordinate_file_capture_id = "capture-1"
    start = json.dumps(
        {
            "type": "coordinate_scan_start",
            "capture_id": "capture-1",
            "label": "baseline",
            "start_offset": 0,
            "length": 2,
        }
    )
    end = json.dumps({"type": "coordinate_scan_end", "capture_id": "capture-1"})
    server.coordinate_file.write_text(start, encoding="utf-8")

    server._poll_coordinate_file()
    assert server.drain_coordinate_events() == ()

    with server.coordinate_file.open("a", encoding="utf-8") as handle:
        handle.write("\n" + end + "\n")
    server._poll_coordinate_file()

    events = server.drain_coordinate_events()
    assert [event["type"] for event in events] == [
        "coordinate_scan_start",
        "coordinate_scan_end",
    ]
    assert server._coordinate_file_capture_id is None
