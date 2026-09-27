"""Pokemon Platinum RAM profile for BizHawk Main RAM reads."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PlatinumMemoryProfile:
    """Address constants for Pokemon Platinum player/opponent party reads."""

    main_ram_base: int = 0x02000000
    party_pointer_address: int = 0x02101D2C
    player_party_relative_offset: int = 0xD088
    player_party_relative_offset_candidates: tuple[int, ...] = (0xD088, 0xD090, 0xD094)
    player_party_count_relative_offset: int = 0xD090
    player_party_records_relative_offset: int = 0xD094
    battle_battler_candidate_offsets: tuple[int, ...] = (
        0x54598,
        0x54658,
        0x54718,
        0x547D8,
    )
    battle_battler_stride: int = 0xC0
    battle_battler_record_size: int = 0xC0
    party_pokemon_size: int = 236
    max_party_slots: int = 6

    def main_ram_offset(self, address: int) -> int:
        if address >= self.main_ram_base:
            return address - self.main_ram_base
        return address


PLATINUM_US = PlatinumMemoryProfile()
