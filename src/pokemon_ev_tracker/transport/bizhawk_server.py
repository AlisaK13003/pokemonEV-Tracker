"""Localhost NDJSON receiver for BizHawk Lua diagnostics."""

from __future__ import annotations

import json
import logging
import os
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
        self.stale_after_seconds = stale_after_seconds
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._heartbeat: BizHawkHeartbeat | None = None
        self._party_payload: BizHawkHeartbeat | None = None
        self._server_socket: socket.socket | None = None
        self._tcp_thread: threading.Thread | None = None
        self._file_thread: threading.Thread | None = None
        self._client_threads: list[threading.Thread] = []
        self._file_position: int | None = None

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

    def _poll_fallback_file(self) -> None:
        while not self._stop_event.wait(0.5):
            try:
                if not self.fallback_file.exists():
                    continue
                size = self.fallback_file.stat().st_size
                if self._file_position is None:
                    self._file_position = size
                    continue
                if size < self._file_position:
                    self._file_position = 0
                with self.fallback_file.open("r", encoding="utf-8") as handle:
                    handle.seek(self._file_position)
                    for line in handle:
                        self._record_line(line, "file")
                    self._file_position = handle.tell()
            except OSError:
                LOGGER.exception("Could not poll BizHawk fallback file.")

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
        with self._lock:
            received = BizHawkHeartbeat(
                received_at=time.monotonic(), payload=payload, source=source
            )
            if message_type == "heartbeat":
                self._heartbeat = received
            elif message_type == "party_memory":
                self._party_payload = received
