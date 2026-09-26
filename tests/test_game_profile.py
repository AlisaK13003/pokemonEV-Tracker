from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path

import pytest

from pokemon_ev_tracker.config.paths import app_data_directory
from pokemon_ev_tracker.core.ev_targets import EVTarget, EVTargetStore
from pokemon_ev_tracker.games.platinum.profile import PLATINUM_PROFILE
from pokemon_ev_tracker.games.platinum.species import load_gen4_species


def test_platinum_profile_binds_game_memory_and_party_decoder() -> None:
    profile = PLATINUM_PROFILE

    assert profile.game_id == "pokemon-platinum"
    assert profile.display_name == "Pokémon Platinum"
    assert "NDS" in profile.supported_cores
    assert profile.memory_profile.party_pointer_address == 0x02101D2C
    assert callable(profile.party_decoder)


def test_species_catalog_resolves_independently_of_working_directory(monkeypatch) -> None:
    monkeypatch.chdir(Path(__file__).resolve().parents[1] / "tests")

    catalog = load_gen4_species()

    assert len(catalog) == 493
    assert catalog[178].name == "Mareep"


@pytest.mark.skipif(os.name != "nt", reason="Windows LocalAppData behavior")
def test_app_data_directory_uses_windows_local_application_data(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    assert app_data_directory() == tmp_path / "PokemonEVTracker"


def test_legacy_ev_targets_migrate_to_user_path(monkeypatch, tmp_path) -> None:
    legacy = tmp_path / "legacy-targets.json"
    destination = tmp_path / "migrated-targets.json"
    legacy.write_text(
        json.dumps({"00001234": asdict(EVTarget(attack_target=252))}),
        encoding="utf-8",
    )
    monkeypatch.setattr("pokemon_ev_tracker.core.ev_targets.LEGACY_EV_TARGETS_PATH", legacy)
    monkeypatch.setattr("pokemon_ev_tracker.core.ev_targets.DEFAULT_EV_TARGETS_PATH", destination)
    store = EVTargetStore()
    assert store.get(0x1234) == EVTarget(attack_target=252)
    assert EVTargetStore(destination).get(0x1234) == EVTarget(attack_target=252)
    assert not legacy.exists()
