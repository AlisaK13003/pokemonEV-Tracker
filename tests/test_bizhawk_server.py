from __future__ import annotations

from pathlib import Path

from pokemon_ev_tracker.transport.bizhawk_server import BizHawkDebugServer


def test_default_fallback_file_uses_system_temp_not_working_directory(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("TEMP", str(tmp_path))
    monkeypatch.delenv("TMP", raising=False)
    monkeypatch.delenv("TMPDIR", raising=False)

    server = BizHawkDebugServer()

    assert server.fallback_file == tmp_path / "ev_tracker_bizhawk.jsonl"
    assert server.fallback_file.parent != Path.cwd()
