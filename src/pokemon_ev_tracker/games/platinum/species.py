"""Species names bundled for the Platinum party decoder."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Species:
    national_dex_number: int
    name: str


def load_gen4_species(path: Path | None = None) -> tuple[Species, ...]:
    catalog_path = path or Path(__file__).resolve().parent / "data" / "pokemon_species.json"
    names = json.loads(catalog_path.read_text(encoding="utf-8"))
    if not isinstance(names, list) or len(names) != 493:
        raise ValueError("Generation IV species data must contain National Dex numbers 1-493.")
    return tuple(Species(number, str(name)) for number, name in enumerate(names, 1))
