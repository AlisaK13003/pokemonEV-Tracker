"""Offline Platinum species ability slots and canonical ability names.

Slot IDs use PKHeX's Platinum personal table; English names use PokeAPI's ability names.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class AbilityDetails:
    slot: int | None
    id: int
    name: str | None


@lru_cache(maxsize=1)
def _load_ability_data() -> tuple[dict[int, str], dict[int, tuple[int, int]]]:
    data_path = Path(__file__).resolve().parent / "data" / "pokemon_abilities.json"
    data = json.loads(data_path.read_text(encoding="utf-8"))
    names = {int(key): value for key, value in data["ability_names"].items()}
    species = {
        int(key): (int(value[0]), int(value[1]))
        for key, value in data["species_abilities"].items()
    }
    return names, species


def get_platinum_ability(species_id: int, ability_id: int) -> AbilityDetails:
    names, species = _load_ability_data()
    ability_pair = species.get(species_id)
    slot = None
    if ability_pair is not None:
        if ability_pair[0] == ability_id:
            slot = 1
        elif ability_pair[1] == ability_id:
            slot = 2
    return AbilityDetails(slot, ability_id, names.get(ability_id))
