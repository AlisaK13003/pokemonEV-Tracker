"""Layout positions for the six Gen IV party slots."""

from __future__ import annotations


def party_card_positions(member_count: int) -> tuple[tuple[int, int], ...]:
    if not 0 <= member_count <= 6:
        raise ValueError("Party size must be between 0 and 6.")
    return tuple((index // 3, index % 3) for index in range(member_count))
