from __future__ import annotations

from pathlib import Path

from pokemon_ev_tracker.transport.bizhawk_server import BizHawkDebugServer


class _CommandSocket:
    def __init__(self):
        self.sent = []

    def sendall(self, data: bytes) -> None:
        self.sent.append(data)


def test_default_fallback_file_uses_system_temp_not_working_directory(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("TEMP", str(tmp_path))
    monkeypatch.delenv("TMP", raising=False)
    monkeypatch.delenv("TMPDIR", raising=False)

    server = BizHawkDebugServer()

    assert server.fallback_file == tmp_path / "ev_tracker_bizhawk.jsonl"
    assert server.fallback_file.parent != Path.cwd()


def test_coordinate_capture_command_is_sent_only_for_valid_range() -> None:
    server = BizHawkDebugServer()
    fake_socket = _CommandSocket()
    server._active_client = fake_socket

    assert server.request_coordinate_capture("abc123", "right", 0, 0x400000)
    assert fake_socket.sent == [b"CAPTURE|abc123|right|0|4194304\n"]
    assert not server.request_coordinate_capture("abc123", "unknown", 0, 16)
    assert not server.request_coordinate_capture("abc123", "left", 0, 0x400001)


def test_live_coordinate_preview_command_uses_domain_offsets() -> None:
    server = BizHawkDebugServer()
    fake_socket = _CommandSocket()
    server._active_client = fake_socket

    assert server.set_coordinate_preview(0x1234, 0x5678, "s16")
    assert server.set_coordinate_preview(None, None)
    assert fake_socket.sent == [b"PREVIEW|4660|22136|s16\n", b"CLEAR_PREVIEW\n"]


def test_friendship_walk_tcp_commands_are_high_level_and_validated() -> None:
    server = BizHawkDebugServer()
    fake_socket = _CommandSocket()
    server._active_client = fake_socket

    receipts = [
        server.send_friendship_walk_command("START", "horizontal"),
        server.send_friendship_walk_command("DIRECTION", "Right"),
        server.send_friendship_walk_command("PING"),
        server.send_friendship_walk_command("STOP"),
    ]
    assert all(receipt is not None for receipt in receipts)
    assert [receipt.sequence for receipt in receipts] == sorted(
        receipt.sequence for receipt in receipts
    )
    assert not server.send_friendship_walk_command("DIRECTION", "A")
    assert not server.send_friendship_walk_command("START", "diagonal")
    assert [command.split(b"|")[2].splitlines()[0] for command in fake_socket.sent] == [
        b"START",
        b"DIRECTION",
        b"PING",
        b"STOP",
    ]
    assert fake_socket.sent[0].endswith(b"|START|horizontal\n")
    assert fake_socket.sent[1].endswith(b"|DIRECTION|Right\n")


def test_friendship_walk_file_command_supports_fallback_transport(tmp_path) -> None:
    server = BizHawkDebugServer(fallback_file=tmp_path / "ram.jsonl")

    receipt = server.send_friendship_walk_command("START", "vertical", transport="file")

    assert receipt is not None
    assert server.command_file.read_text(encoding="ascii") == (
        f"WALK|{receipt.sequence}|START|vertical\n"
    )


def test_walk_stop_can_release_over_both_routes_with_one_sequence(tmp_path) -> None:
    server = BizHawkDebugServer(fallback_file=tmp_path / "ram.jsonl")
    fake_socket = _CommandSocket()
    server._active_client = fake_socket

    receipt = server.send_friendship_walk_command("STOP", transport=("file", "tcp"))

    assert receipt is not None
    assert receipt.transport == "file+tcp"
    assert server.command_file.read_text(encoding="ascii") == f"WALK|{receipt.sequence}|STOP\n"
    assert fake_socket.sent == [f"WALK|{receipt.sequence}|STOP\n".encode("ascii")]
