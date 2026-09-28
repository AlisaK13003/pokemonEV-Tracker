"""Offline Generation IV move names and party move-slot helpers."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def _load_move_names() -> dict[int, str]:
    data_path = Path(__file__).resolve().parent / "data" / "pokemon_moves.json"
    data = json.loads(data_path.read_text(encoding="utf-8"))
    names = {int(move_id): str(name) for move_id, name in data.items()}
    if len(names) != 467:
        raise ValueError("Platinum move data must contain move IDs 1-467.")
    return names


def get_platinum_move_name(move_id: int) -> str | None:
    if move_id == 0:
        return None
    return _load_move_names().get(move_id, f"Unknown move #{move_id}")
