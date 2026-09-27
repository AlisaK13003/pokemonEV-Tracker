"""Decode candidate active-battler records from Platinum Main RAM."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache

from pokemon_ev_tracker.games.platinum.memory import PLATINUM_US, PlatinumMemoryProfile
from pokemon_ev_tracker.games.platinum.species import Species, load_gen4_species

_SPECIES_MAX = 493
_LEVEL_RANGE = range(1, 101)


class BattleValidationState(str, Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


@dataclass(frozen=True)
class BattleBattler:
    battler_index: int
    relative_offset: int
    address: int | None
    raw_hex: str
    species_id: int | None
    species_name: str | None
    level: int | None
    current_hp: int | None
    max_hp: int | None
    hp_region_raw_hex: str
    pid: int | None
    ability_id: int | None
    held_item_id: int | None
    stats: Mapping[str, int | None]
    nickname_raw_hex: str
    validation_state: BattleValidationState
    validation_reason: str | None

    @property
    def active(self) -> bool:
        return self.validation_state is not BattleValidationState.INACTIVE

    @property
    def species(self) -> str:
        if self.species_name:
            return self.species_name
        return f"Unknown #{self.species_id}" if self.species_id is not None else "Unknown"

    @property
    def nickname(self) -> None:
        return None

    @property
    def role(self) -> str:
        return (
            "Player 1",
            "Enemy 1",
            "Player 2 / Partner",
            "Enemy 2",
        )[self.battler_index]


def decode_battle_battlers(
    raw_records: Mapping[int, str | bytes],
    base_pointer: int | str | None,
    profile: PlatinumMemoryProfile = PLATINUM_US,
    species_catalog: tuple[Species, ...] | None = None,
) -> tuple[BattleBattler, ...]:
    """Decode the four candidate 0xC0 battler records without hiding failures."""
    pointer = _parse_pointer(base_pointer)
    species_names = _species_names(species_catalog)
    battlers = []
    for index, relative_offset in enumerate(profile.battle_battler_candidate_offsets):
        raw = _to_bytes(raw_records.get(index))
        address = pointer + relative_offset if pointer is not None else None
        battlers.append(
            _decode_battler(index, relative_offset, address, raw, species_names, profile)
        )
    return tuple(battlers)


def active_enemy_battlers(
    battlers: tuple[BattleBattler, ...],
) -> tuple[BattleBattler, ...]:
    """Return active enemies only when their corresponding player slot is active."""
    by_index = {battler.battler_index: battler for battler in battlers}
    return tuple(
        enemy
        for player_index, enemy_index in ((0, 1), (2, 3))
        if (player := by_index.get(player_index)) is not None
        and (enemy := by_index.get(enemy_index)) is not None
        and player.active
        and enemy.active
    )


def _decode_battler(index, relative_offset, address, raw, species_names, profile):
    values = {
        "species_id": _read_u16(raw, 0x00),
        "attack": _read_u16(raw, 0x02),
        "defense": _read_u16(raw, 0x04),
        "speed": _read_u16(raw, 0x06),
        "special_attack": _read_u16(raw, 0x08),
        "special_defense": _read_u16(raw, 0x0A),
        "packed_ivs": _read_u32(raw, 0x14),
        "ability_id": _read_u8(raw, 0x27),
        "level": _read_u8(raw, 0x34),
        "current_hp": _read_u16(raw, 0x4C),
        "max_hp": _read_u16(raw, 0x4E),
        "pid": _read_u32(raw, 0x68),
        "held_item_id": _read_u16(raw, 0x78),
    }
    species_id = values["species_id"]
    species_name = species_names.get(species_id)
    invalid_reasons = []
    if len(raw) < profile.battle_battler_record_size:
        invalid_reasons.append(
            f"Record is {len(raw):#x} bytes; expected {profile.battle_battler_record_size:#x}."
        )
    if raw and not any(raw):
        invalid_reasons.append("Record is all zeroes.")
    if species_id is None or not 1 <= species_id <= _SPECIES_MAX:
        invalid_reasons.append(f"Species ID {species_id!r} is outside 1-{_SPECIES_MAX}.")
    if values["level"] not in _LEVEL_RANGE:
        invalid_reasons.append(f"Level {values['level']!r} is outside 1-100.")
    validation_state = (
        BattleValidationState.INACTIVE if invalid_reasons else BattleValidationState.ACTIVE
    )
    validation_reason = " ".join(invalid_reasons) if invalid_reasons else None

    return BattleBattler(
        battler_index=index,
        relative_offset=relative_offset,
        address=address,
        raw_hex=raw.hex(" ").upper(),
        species_id=species_id,
        species_name=species_name,
        level=values["level"],
        current_hp=values["current_hp"],
        max_hp=values["max_hp"],
        hp_region_raw_hex=raw[0x48:0x54].hex(" ").upper(),
        pid=values["pid"],
        ability_id=values["ability_id"],
        held_item_id=values["held_item_id"],
        stats={name: values[name] for name in ("attack", "defense", "speed", "special_attack", "special_defense")},
        nickname_raw_hex=raw[0x36:0x4C].hex(" ").upper(),
        validation_state=validation_state,
        validation_reason=validation_reason,
    )


def _read_u8(raw: bytes, offset: int) -> int | None:
    return raw[offset] if len(raw) > offset else None


def _read_u16(raw: bytes, offset: int) -> int | None:
    if len(raw) < offset + 2:
        return None
    return int.from_bytes(raw[offset : offset + 2], "little")


def _read_u32(raw: bytes, offset: int) -> int | None:
    if len(raw) < offset + 4:
        return None
    return int.from_bytes(raw[offset : offset + 4], "little")


def _parse_pointer(value: int | str | None) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value, 16)
        except ValueError:
            return None
    return None


def _to_bytes(value: str | bytes | None) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        try:
            return bytes.fromhex(value)
        except ValueError:
            return b""
    return b""


@lru_cache(maxsize=1)
def _species_names(species_catalog: tuple[Species, ...] | None) -> dict[int, str]:
    catalog = species_catalog or load_gen4_species()
    return {species.national_dex_number: species.name for species in catalog}
