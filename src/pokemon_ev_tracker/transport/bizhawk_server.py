"""Localhost NDJSON receiver for BizHawk Lua diagnostics."""

from __future__ import annotations

import json
import logging
import os
import queue
import secrets
import socket
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class BizHawkHeartbeat:
    """Latest diagnostic message received from BizHawk."""

    received_at: float
    payload: dict[str, Any]
    source: str


@dataclass(frozen=True)
class FriendshipWalkCommandReceipt:
    """Sequence and route used for a queued Lua walk command."""

    sequence: int
    transport: str


class BizHawkDebugServer:
    """Receives newline-delimited JSON from BizHawk over localhost.

    The matching Lua script tries TCP first. If LuaSocket is unavailable inside
    EmuHawk, it appends the same JSON lines to ``fallback_file`` and this class
    polls that file.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 46387,
        fallback_file: Path | None = None,
        stale_after_seconds: float = 5.0,
    ) -> None:
        self.host = host
        self.port = int(port)
        self.fallback_file = (
            fallback_file
            or Path(
                os.environ.get("TEMP")
                or os.environ.get("TMP")
                or os.environ.get("TMPDIR")
                or tempfile.gettempdir()
            )
            / "ev_tracker_bizhawk.jsonl"
        )
        self.command_file = self.fallback_file.with_name("ev_tracker_bizhawk_command.txt")
        self.coordinate_file = self.fallback_file.with_name("ev_tracker_bizhawk_coordinates.jsonl")
        self.stale_after_seconds = stale_after_seconds
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._walk_command_lock = threading.Lock()
        self._walk_command_sequence = secrets.randbelow(8_000_000_000) + 1_000_000_000
        self._heartbeat: BizHawkHeartbeat | None = None
        self._party_payload: BizHawkHeartbeat | None = None
        self._server_socket: socket.socket | None = None
        self._tcp_thread: threading.Thread | None = None
        self._file_thread: threading.Thread | None = None
        self._client_threads: list[threading.Thread] = []
        self._file_position: int | None = None
        self._client_lock = threading.Lock()
        self._active_client: socket.socket | None = None
        self._coordinate_events: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=2048)
        self._coordinate_file_lock = threading.Lock()
        self._coordinate_file_capture_id: str | None = None
        self._coordinate_file_position = 0

    def start(self) -> None:
        if self._tcp_thread is not None and self._tcp_thread.is_alive():
            return
        self._stop_event.clear()
        self._tcp_thread = threading.Thread(
            target=self._serve_tcp,
            name="bizhawk-ram-tcp-server",
            daemon=True,
        )
        self._file_thread = threading.Thread(
            target=self._poll_fallback_file,
            name="bizhawk-ram-file-poller",
            daemon=True,
        )
        self._tcp_thread.start()
        self._file_thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        with self._client_lock:
            client = self._active_client
            self._active_client = None
        if client is not None:
            try:
                client.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                client.close()
            except OSError:
                pass
        if self._server_socket is not None:
            try:
                self._server_socket.close()
            except OSError:
                pass

    def latest_heartbeat(self) -> BizHawkHeartbeat | None:
        with self._lock:
            return self._heartbeat

    def latest_party_payload(self) -> BizHawkHeartbeat | None:
        with self._lock:
            return self._party_payload

    def request_coordinate_capture(
        self,
        capture_id: str,
        label: str,
        start_offset: int,
        length: int,
        *,
        transport: str = "tcp",
    ) -> FriendshipWalkCommandReceipt | None:
        if label not in {"baseline", "idle", "right", "left", "down", "up"}:
            return False
        if start_offset < 0 or length <= 0 or length > 0x400000:
            return False
        if transport not in {"tcp", "file"}:
            return False
        command = f"CAPTURE|{capture_id}|{label}|{start_offset}|{length}\n"
        if transport == "tcp":
            return self._send_tcp_command(command)
        with self._coordinate_file_lock:
            self._coordinate_file_capture_id = capture_id
            self._coordinate_file_position = 0
            try:
                self.coordinate_file.write_bytes(b"")
            except OSError:
                self._coordinate_file_capture_id = None
                return False
            if not self._write_command_file(command):
                self._coordinate_file_capture_id = None
                return False
        return True

    def send_friendship_walk_command(
        self,
        action: str,
        value: str | None = None,
        *,
        transport: str | tuple[str, ...] = "tcp",
    ) -> FriendshipWalkCommandReceipt | None:
        with self._walk_command_lock:
            self._walk_command_sequence += 1
            sequence = self._walk_command_sequence
        if action == "START" and value in {"horizontal", "vertical"}:
            command = f"WALK|{sequence}|START|{value}\n"
        elif action == "DIRECTION" and value in {"Left", "Right", "Up", "Down"}:
            command = f"WALK|{sequence}|DIRECTION|{value}\n"
        elif action == "STOP" and value is None:
            command = f"WALK|{sequence}|STOP\n"
        elif action == "PING" and value is None:
            command = f"WALK|{sequence}|PING\n"
        else:
            return None
        transports = (transport,) if isinstance(transport, str) else transport
        accepted = []
        for route in transports:
            sent = (
                route == "tcp" and self._send_tcp_command(command)
            ) or (route == "file" and self._write_command_file(command))
            if sent:
                accepted.append(route)
        if not accepted:
            return None
        return FriendshipWalkCommandReceipt(sequence, "+".join(accepted))

    def set_coordinate_preview(
        self,
        x_offset: int | None,
        y_offset: int | None,
        data_type: str = "u16",
        *,
        transport: str = "tcp",
    ) -> bool:
        if x_offset is None or y_offset is None:
            command = "CLEAR_PREVIEW\n"
        else:
            if data_type not in {"u16", "s16"}:
                return False
            if not (0 <= x_offset <= 0x3FFFFE and 0 <= y_offset <= 0x3FFFFE):
                return False
            command = f"PREVIEW|{x_offset}|{y_offset}|{data_type}\n"
        if transport == "tcp":
            return self._send_tcp_command(command)
        if transport == "file":
            return self._write_command_file(command)
        return False

    def drain_coordinate_events(self, limit: int = 1024) -> tuple[dict[str, Any], ...]:
        events = []
        for _ in range(max(0, limit)):
            try:
                events.append(self._coordinate_events.get_nowait())
            except queue.Empty:
                break
        return tuple(events)

    def _send_tcp_command(self, command: str) -> bool:
        with self._client_lock:
            client = self._active_client
            if client is None:
                return False
            try:
                client.sendall(command.encode("ascii"))
            except OSError:
                self._active_client = None
                return False
        return True

    def _write_command_file(self, command: str) -> bool:
        temporary = self.command_file.with_name(self.command_file.name + ".tmp")
        try:
            temporary.write_text(command, encoding="ascii")
            os.replace(temporary, self.command_file)
        except OSError:
            LOGGER.exception("Could not write BizHawk Lua command file.")
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            return False
        return True

    def is_connected(self) -> bool:
        heartbeat = self.latest_heartbeat()
        if heartbeat is None:
            return False
        return time.monotonic() - heartbeat.received_at <= self.stale_after_seconds

    def _serve_tcp(self) -> None:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
                self._server_socket = server
                server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                server.bind((self.host, self.port))
                server.listen(1)
                server.settimeout(0.5)
                LOGGER.info("BizHawk RAM server listening on %s:%s", self.host, self.port)
                while not self._stop_event.is_set():
                    try:
                        client, address = server.accept()
                    except TimeoutError:
                        continue
                    except OSError:
                        break
                    thread = threading.Thread(
                        target=self._handle_client,
                        args=(client, address),
                        name="bizhawk-ram-client",
                        daemon=True,
                    )
                    self._client_threads.append(thread)
                    thread.start()
        except OSError:
            LOGGER.exception("BizHawk RAM TCP server failed.")
        finally:
            self._server_socket = None

    def _handle_client(self, client: socket.socket, address: tuple[str, int]) -> None:
        LOGGER.info("BizHawk RAM Lua client connected from %s:%s", *address)
        with self._client_lock:
            previous = self._active_client
            self._active_client = client
        if previous is not None and previous is not client:
            try:
                previous.close()
            except OSError:
                pass
        with client:
            file = client.makefile("r", encoding="utf-8", newline="\n")
            while not self._stop_event.is_set():
                try:
                    line = file.readline()
                except OSError:
                    break
                if not line:
                    break
                self._record_line(line, "tcp")
        with self._client_lock:
            if self._active_client is client:
                self._active_client = None

    def _poll_fallback_file(self) -> None:
        while not self._stop_event.wait(0.1):
            try:
                self._poll_log_file(self.fallback_file)
                self._poll_coordinate_file()
            except OSError:
                LOGGER.exception("Could not poll BizHawk fallback file.")

    def _poll_log_file(self, path: Path) -> None:
        if not path.exists():
            return
        size = path.stat().st_size
        if self._file_position is None:
            self._file_position = size
            return
        if size < self._file_position:
            self._file_position = 0
        with path.open("r", encoding="utf-8") as handle:
            handle.seek(self._file_position)
            for line in handle:
                self._record_line(line, "file")
            self._file_position = handle.tell()

    def _poll_coordinate_file(self) -> None:
        with self._coordinate_file_lock:
            capture_id = self._coordinate_file_capture_id
            position = self._coordinate_file_position
        if capture_id is None or not self.coordinate_file.exists():
            return
        size = self.coordinate_file.stat().st_size
        if size < position:
            position = 0
        with self.coordinate_file.open("rb") as handle:
            handle.seek(position)
            data = handle.read()
        complete_length = data.rfind(b"\n") + 1
        if complete_length == 0:
            return
        text = data[:complete_length].decode("utf-8", errors="replace")
        completed = False
        for line in text.splitlines():
            self._record_line(line, "file")
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if (
                event.get("type") in {"coordinate_scan_end", "coordinate_scan_error"}
                and event.get("capture_id") == capture_id
            ):
                completed = True
        with self._coordinate_file_lock:
            if self._coordinate_file_capture_id == capture_id:
                self._coordinate_file_position = position + complete_length
                if completed:
                    self._coordinate_file_capture_id = None

    def _record_line(self, line: str, source: str) -> None:
        line = line.strip()
        if not line:
            return
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            LOGGER.warning("Ignoring invalid BizHawk JSON line: %s", line[:200])
            return
        if not isinstance(payload, dict):
            return
        message_type = payload.get("type")
        if isinstance(message_type, str) and message_type.startswith("coordinate_scan_"):
            if message_type in {"coordinate_scan_end", "coordinate_scan_error"}:
                with self._coordinate_file_lock:
                    if payload.get("capture_id") == self._coordinate_file_capture_id:
                        self._coordinate_file_capture_id = None
            try:
                self._coordinate_events.put_nowait(payload)
            except queue.Full:
                LOGGER.warning("Dropping coordinate discovery event because its queue is full.")
            return
        with self._lock:
            received = BizHawkHeartbeat(
                received_at=time.monotonic(), payload=payload, source=source
            )
            if message_type == "heartbeat":
                self._heartbeat = received
            elif message_type == "party_memory":
                self._party_payload = received
