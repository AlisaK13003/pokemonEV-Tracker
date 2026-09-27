"""Generation IV individual-value packed field decoding."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IndividualValues:
    hp: int
    attack: int
    defense: int
    speed: int
    special_attack: int
    special_defense: int
    is_egg: bool
    has_nickname: bool


def decode_individual_values(packed: int) -> IndividualValues:
    return IndividualValues(
        hp=packed & 0x1F,
        attack=(packed >> 5) & 0x1F,
        defense=(packed >> 10) & 0x1F,
        speed=(packed >> 15) & 0x1F,
        special_attack=(packed >> 20) & 0x1F,
        special_defense=(packed >> 25) & 0x1F,
        is_egg=bool(packed & (1 << 30)),
        has_nickname=bool(packed & (1 << 31)),
    )
