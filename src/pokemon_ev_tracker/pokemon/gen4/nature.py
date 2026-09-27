"""Generation IV nature names and stat modifiers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Nature:
    id: int
    name: str
    increased_stat: str | None
    decreased_stat: str | None


_NATURES = (
    ("Hardy", None, None),
    ("Lonely", "attack", "defense"),
    ("Brave", "attack", "speed"),
    ("Adamant", "attack", "special_attack"),
    ("Naughty", "attack", "special_defense"),
    ("Bold", "defense", "attack"),
    ("Docile", None, None),
    ("Relaxed", "defense", "speed"),
    ("Impish", "defense", "special_attack"),
    ("Lax", "defense", "special_defense"),
    ("Timid", "speed", "attack"),
    ("Hasty", "speed", "defense"),
    ("Serious", None, None),
    ("Jolly", "speed", "special_attack"),
    ("Naive", "speed", "special_defense"),
    ("Modest", "special_attack", "attack"),
    ("Mild", "special_attack", "defense"),
    ("Quiet", "special_attack", "speed"),
    ("Bashful", None, None),
    ("Rash", "special_attack", "special_defense"),
    ("Calm", "special_defense", "attack"),
    ("Gentle", "special_defense", "defense"),
    ("Sassy", "special_defense", "speed"),
    ("Careful", "special_defense", "special_attack"),
    ("Quirky", None, None),
)


def nature_from_pid(pid: int) -> Nature:
    nature_id = int(pid) % len(_NATURES)
    name, increased_stat, decreased_stat = _NATURES[nature_id]
    return Nature(nature_id, name, increased_stat, decreased_stat)
