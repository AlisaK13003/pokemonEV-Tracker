"""Validated player-coordinate decoding for Pokemon Platinum Main RAM."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pokemon_ev_tracker.games.platinum.memory import PLATINUM_US

PLAYER_X_OFFSET = PLATINUM_US.player_x_offset
PLAYER_Y_OFFSET = PLATINUM_US.player_y_offset


@dataclass(frozen=True)
class PlayerPosition:
    x: int
    y: int
    delta_x: int | None = None
    delta_y: int | None = None
    validated_offsets: bool = True


def decode_s16_le(value: bytes | bytearray | int) -> int:
    """Decode one signed 16-bit little-endian coordinate."""
    if isinstance(value, int) and not isinstance(value, bool):
        if not 0 <= value <= 0xFFFF:
            raise ValueError("Unsigned coordinate word must be within 0..65535.")
        raw = value
    elif isinstance(value, (bytes, bytearray)) and len(value) == 2:
        raw = int.from_bytes(value, "little", signed=False)
    else:
        raise ValueError("Coordinate must be a 16-bit word or exactly two bytes.")
    return raw - 0x10000 if raw >= 0x8000 else raw


def decode_player_position(payload: Any) -> PlayerPosition | None:
    """Extract coordinates and optional deltas from a RAM payload."""
    if not isinstance(payload, dict):
        return None
    x = payload.get("player_x")
    y = payload.get("player_y")
    if not _is_coordinate(x) or not _is_coordinate(y):
        return None
    delta_x = payload.get("player_delta_x")
    delta_y = payload.get("player_delta_y")
    return PlayerPosition(
        x=x,
        y=y,
        delta_x=delta_x if _is_coordinate(delta_x) else None,
        delta_y=delta_y if _is_coordinate(delta_y) else None,
        validated_offsets=payload.get("player_coordinates_validated") is True,
    )


def _is_coordinate(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and -0x8000 <= value <= 0x7FFF
