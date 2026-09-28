from __future__ import annotations

import pytest

from pokemon_ev_tracker.games.platinum.memory import PLATINUM_US
from pokemon_ev_tracker.games.platinum.player_position import (
    PLAYER_X_OFFSET,
    PLAYER_Y_OFFSET,
    decode_player_position,
    decode_s16_le,
)


def test_profile_has_user_validated_coordinate_offsets() -> None:
    assert PLAYER_X_OFFSET == PLATINUM_US.player_x_offset == 0x001C5AFE
    assert PLAYER_Y_OFFSET == PLATINUM_US.player_y_offset == 0x001C5B02
    assert PLATINUM_US.player_coordinates_validated


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (b"\x00\x00", 0),
        (b"\xfe\x7f", 32766),
        (b"\x00\x80", -32768),
        (b"\xfe\xff", -2),
        (0xFFFF, -1),
    ],
)
def test_signed_little_endian_coordinate_decoding(raw, expected) -> None:
    assert decode_s16_le(raw) == expected


@pytest.mark.parametrize("raw", [b"\x00", b"\x00\x00\x00", -1, 0x10000, True])
def test_coordinate_decoder_rejects_malformed_words(raw) -> None:
    with pytest.raises(ValueError):
        decode_s16_le(raw)


def test_player_position_includes_frame_deltas_when_available() -> None:
    position = decode_player_position(
        {
            "player_x": -3,
            "player_y": 12,
            "player_delta_x": 1,
            "player_delta_y": -2,
            "player_coordinates_validated": True,
        }
    )

    assert position is not None
    assert (position.x, position.y) == (-3, 12)
    assert (position.delta_x, position.delta_y) == (1, -2)
    assert position.validated_offsets


def test_player_position_rejects_missing_or_out_of_range_values() -> None:
    assert decode_player_position({"player_x": 2, "player_y": None}) is None
    assert decode_player_position({"player_x": 40000, "player_y": 2}) is None
