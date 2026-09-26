from __future__ import annotations

import json

from pokemon_ev_tracker.config.settings import AppSettings


def test_settings_round_trip(tmp_path) -> None:
    path = tmp_path / "settings.json"
    original = AppSettings(
        compact_mode=True,
        window_geometry=(-1200, 55, 744, 620),
        normal_window_geometry=(20, 30, 1260, 850),
    )

    original.save(path)
    loaded = AppSettings.load(path)

    assert loaded == original
    assert set(json.loads(path.read_text(encoding="utf-8"))) == {
        "compact_mode",
        "window_geometry",
        "normal_window_geometry",
    }


def test_settings_ignore_unknown_preferences(tmp_path) -> None:
    path = tmp_path / "old-settings.json"
    path.write_text(
        json.dumps(
            {
                "obsolete_option": "ignored",
                "another_unknown_option": {"value": 0.1},
                "compact_mode": True,
                "window_geometry": [10, 20, 800, 600],
            }
        ),
        encoding="utf-8",
    )

    loaded = AppSettings.load(path)

    assert loaded.compact_mode
    assert loaded.window_geometry == (10, 20, 800, 600)
    assert not hasattr(loaded, "obsolete_option")


def test_load_default_migrates_only_tracker_preferences(monkeypatch, tmp_path) -> None:
    legacy = tmp_path / "legacy-config.json"
    legacy.write_text(
        '{"compact_mode": true, "window_geometry": [1, 2, 600, 400], "obsolete_option": true}',
        encoding="utf-8",
    )
    destination = tmp_path / "local-settings.json"
    monkeypatch.setattr("pokemon_ev_tracker.config.settings.DEFAULT_SETTINGS_PATH", destination)
    monkeypatch.setattr("pokemon_ev_tracker.config.settings.LEGACY_SETTINGS_PATH", legacy)

    settings = AppSettings.load_default()

    assert settings.compact_mode
    assert settings.window_geometry == (1, 2, 600, 400)
    assert set(json.loads(destination.read_text(encoding="utf-8"))) == {
        "compact_mode",
        "window_geometry",
        "normal_window_geometry",
    }
    assert legacy.exists()
