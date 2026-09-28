from __future__ import annotations

from types import SimpleNamespace

import pytest

from pokemon_ev_tracker.data_sources.bizhawk import BizHawkRamDataSource
from pokemon_ev_tracker.games.platinum.decoder import decode_party, nickname_is_default
from pokemon_ev_tracker.games.platinum.memory import PLATINUM_US
from pokemon_ev_tracker.pokemon.gen4.crypto import (
    BOX_DATA_SIZE,
    block_order,
    calculate_checksum,
    decrypt_box_data,
    encrypt_box_data,
    prng,
    shuffle_index,
    unshuffle_blocks,
    xor_words,
)
from pokemon_ev_tracker.pokemon.gen4.ivs import decode_individual_values
from pokemon_ev_tracker.pokemon.gen4.nature import nature_from_pid
from pokemon_ev_tracker.pokemon.gen4.structure import (
    FRIENDSHIP_BOX_DATA_OFFSET,
    FRIENDSHIP_RECORD_OFFSET,
    HELD_ITEM_BOX_DATA_OFFSET,
    HELD_ITEM_RECORD_OFFSET,
    PARTY_POKEMON_SIZE,
    decode_party_pokemon,
)
from pokemon_ev_tracker.ui.party_layout import party_card_positions


def test_prng_returns_upper_16_bits_after_lcg_step() -> None:
    rng = prng(0)

    assert next(rng) == 0
    assert next(rng) == 0xE97E


def test_shuffle_permutation_selection() -> None:
    assert shuffle_index(0x00000000) == 0
    assert block_order(0x00000000) == "ABCD"
    assert shuffle_index(0x00002000) == 1
    assert block_order(0x00002000) == "ABDC"


def test_block_unshuffle_restores_original_order() -> None:
    original = b"A" * 32 + b"B" * 32 + b"C" * 32 + b"D" * 32
    shuffled = b"A" * 32 + b"C" * 32 + b"D" * 32 + b"B" * 32

    assert block_order(0x00006000) == "ACDB"
    assert unshuffle_blocks(shuffled, 0x00006000) == original


def test_checksum_calculation_uses_16_bit_words() -> None:
    data = bytearray(BOX_DATA_SIZE)
    data[0:2] = (1).to_bytes(2, "little")
    data[2:4] = (0xFFFF).to_bytes(2, "little")
    data[4:6] = (2).to_bytes(2, "little")

    assert calculate_checksum(bytes(data)) == 2


def test_decrypt_and_extract_evs_for_party_pokemon() -> None:
    record = _party_record(
        pid=0x12345678,
        species_id=253,
        evs=(0, 32, 0, 28, 0, 4),
        level=18,
        current_hp=44,
    )

    decoded = decode_party_pokemon(record, address=0x0210EDC4)

    assert decoded.diagnostics.checksum_valid is True
    assert decoded.species_id == 253
    assert decoded.evs.hp == 0
    assert decoded.evs.attack == 32
    assert decoded.evs.defense == 0
    assert decoded.evs.special_attack == 0
    assert decoded.evs.special_defense == 4
    assert decoded.evs.speed == 28
    assert decoded.evs.total == 64
    assert decoded.level == 18
    assert decoded.current_hp == 44


def test_gen4_move_slots_decode_and_resolve_to_platinum_names() -> None:
    record = _party_record(
        pid=0x12345678,
        species_id=179,
        evs=(0, 0, 0, 0, 0, 0),
        moves=(98, 45, 0, 1),
    )

    decoded = decode_party_pokemon(record)
    party = decode_party((1).to_bytes(4, "little") + record + bytes(PARTY_POKEMON_SIZE * 5))

    assert decoded.diagnostics.checksum_valid
    assert decoded.move_ids == (98, 45, 0, 1)
    assert party.pokemon[0].moves == ("Quick Attack", "Growl", "Pound")


@pytest.mark.parametrize("friendship", (0, 164, 255))
def test_gen4_friendship_decodes_unsigned_byte_from_block_a(friendship: int) -> None:
    record = _party_record(
        pid=0x12345678,
        species_id=179,
        evs=(0, 0, 0, 0, 0, 0),
        friendship=friendship,
    )

    decoded = decode_party_pokemon(record)
    party = decode_party(
        (1).to_bytes(4, "little") + record + bytes(PARTY_POKEMON_SIZE * 5)
    )

    assert decoded.diagnostics.checksum_valid
    assert decoded.friendship == friendship
    assert party.pokemon[0].friendship == friendship
    assert FRIENDSHIP_RECORD_OFFSET == 0x14
    assert FRIENDSHIP_BOX_DATA_OFFSET == 0x0C


@pytest.mark.parametrize(
    ("value", "expected"),
    (
        (0, "Very Low"),
        (49, "Very Low"),
        (50, "Low"),
        (99, "Low"),
        (100, "Neutral"),
        (149, "Neutral"),
        (150, "High"),
        (199, "High"),
        (200, "Very High"),
        (254, "Very High"),
        (255, "Max"),
    ),
)
def test_friendship_label_boundaries(value: int, expected: str) -> None:
    from pokemon_ev_tracker.pokemon.gen4.friendship import friendship_label

    assert friendship_label(value) == expected


def test_pokemon_stable_identity_ignores_evolution_level_evs_item_and_nickname() -> None:
    original = decode_party_pokemon(
        _party_record(
            pid=0x12345678,
            species_id=393,
            evs=(0, 0, 0, 0, 0, 0),
            level=5,
            nickname="piplup",
            held_item_id=0,
        )
    )
    evolved = decode_party_pokemon(
        _party_record(
            pid=0x12345678,
            species_id=394,
            evs=(4, 12, 0, 0, 0, 8),
            level=18,
            nickname="plip",
            held_item_id=112,
        )
    )

    assert original.stable_id == evolved.stable_id


def test_iv_bitfield_decoding_keeps_gen4_flags_separate() -> None:
    packed = (
        31
        | (0 << 5)
        | (17 << 10)
        | (14 << 15)
        | (8 << 20)
        | (24 << 25)
        | (1 << 30)
        | (1 << 31)
    )

    ivs = decode_individual_values(packed)

    assert (ivs.hp, ivs.attack, ivs.defense) == (31, 0, 17)
    assert (ivs.speed, ivs.special_attack, ivs.special_defense) == (14, 8, 24)
    assert ivs.is_egg
    assert ivs.has_nickname
    assert all(0 <= value <= 31 for value in (ivs.hp, ivs.attack, ivs.defense,
                                               ivs.speed, ivs.special_attack,
                                               ivs.special_defense))


def test_party_model_exposes_ivs_in_display_stat_order() -> None:
    record = _party_record(
        pid=0x12345678,
        species_id=183,
        evs=(0, 0, 0, 0, 0, 0),
        ivs=(31, 0, 17, 14, 8, 24),
        is_egg=True,
        has_nickname=True,
    )
    raw_party = (1).to_bytes(4, "little") + record + bytes(PARTY_POKEMON_SIZE * 5)

    pokemon = decode_party(raw_party).pokemon[0]

    assert (pokemon.hp_iv, pokemon.attack_iv, pokemon.defense_iv) == (31, 0, 17)
    assert (pokemon.speed_iv, pokemon.special_attack_iv, pokemon.special_defense_iv) == (
        14,
        8,
        24,
    )
    assert pokemon.decoded.ivs.is_egg
    assert pokemon.decoded.ivs.has_nickname


def test_nature_comes_from_pid_modulo_25_and_neutral_natures_have_no_modifiers() -> None:
    adamant = nature_from_pid(0x12345678 - (0x12345678 % 25) + 3)
    timid = nature_from_pid(10)
    neutral = nature_from_pid(12)

    assert (adamant.id, adamant.name) == (3, "Adamant")
    assert (adamant.increased_stat, adamant.decreased_stat) == (
        "attack",
        "special_attack",
    )
    assert (timid.increased_stat, timid.decreased_stat) == ("speed", "attack")
    assert neutral.name == "Serious"
    assert neutral.increased_stat is None
    assert neutral.decreased_stat is None


def test_platinum_ability_lookup_uses_actual_ability_id_and_species_slot() -> None:
    first = decode_party_pokemon(
        _party_record(
            pid=0x12345678,
            species_id=183,
            evs=(0, 0, 0, 0, 0, 0),
            ability_id=47,
        )
    )
    second = decode_party_pokemon(
        _party_record(
            pid=0x12345679,
            species_id=183,
            evs=(0, 0, 0, 0, 0, 0),
            ability_id=37,
        )
    )
    party_bytes = (2).to_bytes(4, "little") + _party_record(
        pid=0x12345678,
        species_id=183,
        evs=(0, 0, 0, 0, 0, 0),
        ability_id=47,
    ) + _party_record(
        pid=0x12345679,
        species_id=183,
        evs=(0, 0, 0, 0, 0, 0),
        ability_id=37,
    ) + bytes(PARTY_POKEMON_SIZE * 4)
    party = decode_party(party_bytes)

    assert first.ability_id == 47
    assert second.ability_id == 37
    assert [(mon.ability_slot, mon.ability_name) for mon in party.pokemon] == [
        (1, "Thick Fat"),
        (2, "Huge Power"),
    ]


def test_actual_party_stats_are_extracted_from_encrypted_tail() -> None:
    decoded = decode_party_pokemon(
        _party_record(
            pid=0x12345678,
            species_id=183,
            evs=(0, 0, 0, 0, 0, 0),
            max_hp=53,
            attack_stat=27,
            defense_stat=30,
            speed_stat=22,
            special_attack_stat=18,
            special_defense_stat=29,
        )
    )

    assert decoded.current_stats.max_hp == 53
    assert decoded.current_stats.attack == 27
    assert decoded.current_stats.defense == 30
    assert decoded.current_stats.special_attack == 18
    assert decoded.current_stats.special_defense == 29
    assert decoded.current_stats.speed == 22


def test_party_decode_maps_species_and_empty_slots() -> None:
    record = _party_record(pid=0x12345678, species_id=387, evs=(1, 2, 3, 4, 5, 6))
    raw_party = (1).to_bytes(4, "little") + record + bytes(PARTY_POKEMON_SIZE * 5)

    party = decode_party(raw_party)

    assert party.party_count == 1
    assert party.party_count_valid is True
    assert len(party.pokemon) == 1
    assert party.pokemon[0].slot == 1
    assert party.pokemon[0].species == "Turtwig"
    assert party.pokemon[0].evs["special_attack"] == 5
    assert party.pokemon[0].evs["special_defense"] == 6
    assert party.pokemon[0].evs["speed"] == 4
    assert party.pokemon[0].nickname == "Turtwig"
    assert party.pokemon[0].held_item_id == 0
    assert party.pokemon[0].held_item_name is None


def test_party_decode_exposes_held_item_id_and_name() -> None:
    record = _party_record(
        pid=0x12345678,
        species_id=179,
        evs=(0, 0, 0, 0, 0, 0),
        held_item_id=293,
    )
    raw_party = (1).to_bytes(4, "little") + record + bytes(PARTY_POKEMON_SIZE * 5)

    pokemon = decode_party(raw_party).pokemon[0]

    assert pokemon.held_item_id == 293
    assert pokemon.held_item_name == "Power Anklet"
    assert HELD_ITEM_BOX_DATA_OFFSET == 0x02
    assert HELD_ITEM_RECORD_OFFSET == 0x0A


def test_gen4_nickname_decodes_custom_name_and_preserves_case() -> None:
    decoded = decode_party_pokemon(
        _party_record(
            pid=0x12345678,
            species_id=21,
            evs=(0, 0, 0, 0, 0, 0),
            nickname="sheddy",
        )
    )

    assert decoded.nickname == "sheddy"


def test_gen4_nickname_decodes_to_the_full_field_limit_without_terminator() -> None:
    decoded = decode_party_pokemon(
        _party_record(
            pid=0x12345678,
            species_id=25,
            evs=(0, 0, 0, 0, 0, 0),
            nickname="ABCDEFGHIJK",
            nickname_terminated=False,
        )
    )

    assert decoded.nickname == "ABCDEFGHIJK"
    assert decoded.nickname_diagnostics.terminator_unit_index is None


def test_gen4_nickname_preserves_spaces_and_decodes_accented_glyphs() -> None:
    decoded = decode_party_pokemon(
        _party_record(
            pid=0x12345678,
            species_id=25,
            evs=(0, 0, 0, 0, 0, 0),
            nickname="  Poké!  ",
        )
    )

    assert decoded.nickname == "  Poké!  "


def test_default_species_name_detection_ignores_case_and_fullwidth_glyphs() -> None:
    assert nickname_is_default("SPEAROW", "Spearow")
    assert nickname_is_default("Ｓｐｅａｒｏｗ", "Spearow")
    assert not nickname_is_default("sheddy", "Spearow")


def test_default_species_nickname_remains_separate_from_species() -> None:
    record = _party_record(
        pid=0x12345678,
        species_id=21,
        evs=(0, 0, 0, 0, 0, 0),
        nickname="SPEAROW",
    )
    party = decode_party((1).to_bytes(4, "little") + record + bytes(PARTY_POKEMON_SIZE * 5))
    pokemon = party.pokemon[0]

    assert pokemon.nickname == "SPEAROW"
    assert pokemon.species == "Spearow"
    assert nickname_is_default(pokemon.nickname, pokemon.species)


def test_malformed_nickname_data_falls_back_to_species_name() -> None:
    record = _party_record(
        pid=0x12345678,
        species_id=387,
        evs=(0, 0, 0, 0, 0, 0),
        nickname_codes=(0x0300,),
    )
    decoded = decode_party_pokemon(record)
    party = decode_party((1).to_bytes(4, "little") + record + bytes(PARTY_POKEMON_SIZE * 5))

    assert decoded.nickname is None
    assert party.pokemon[0].species == "Turtwig"
    assert party.pokemon[0].nickname == "Turtwig"


def test_party_card_layout_supports_one_through_six_members() -> None:
    expected_positions = {
        1: ((0, 0),),
        2: ((0, 0), (0, 1)),
        3: ((0, 0), (0, 1), (0, 2)),
        4: ((0, 0), (0, 1), (0, 2), (1, 0)),
        5: ((0, 0), (0, 1), (0, 2), (1, 0), (1, 1)),
        6: ((0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (1, 2)),
    }

    for count, positions in expected_positions.items():
        assert party_card_positions(count) == positions


def test_invalid_checksum_is_reported_and_evs_not_marked_valid() -> None:
    record = bytearray(_party_record(pid=0x12345678, species_id=253, evs=(0, 1, 2, 3, 4, 5)))
    record[0x20] ^= 0xFF

    decoded = decode_party_pokemon(bytes(record))

    assert decoded.diagnostics.checksum_valid is False


def test_battle_stats_are_validated_separately_from_pokemon_checksum() -> None:
    record = _party_record(
        pid=0x12345678,
        species_id=16,
        evs=(0, 0, 0, 0, 0, 0),
        level=4,
        current_hp=53720,
        max_hp=43591,
    )

    decoded = decode_party_pokemon(record)

    assert decoded.diagnostics.checksum_valid
    assert not decoded.diagnostics.battle_stats_valid
    assert "Max HP 43591" in decoded.diagnostics.battle_stats_error
    assert decoded.level == 4
    assert decoded.current_hp == 53720
    assert decoded.max_hp == 43591
    assert len(decoded.diagnostics.battle_stats_raw_hex.split()) == 20
    assert len(decoded.diagnostics.battle_stats_decrypted_hex.split()) == 20


def test_impossible_party_count_stops_decoding() -> None:
    raw_party = (7).to_bytes(4, "little") + bytes(PARTY_POKEMON_SIZE * 6)

    party = decode_party(raw_party)

    assert party.party_count == 7
    assert party.party_count_valid is False
    assert party.pokemon == ()


def test_bizhawk_data_source_prefers_scanned_checksum_valid_party_candidate() -> None:
    first = _party_record(pid=0x12345678, species_id=287, evs=(0, 1, 2, 3, 4, 5))
    second = _party_record(pid=0x87654321, species_id=21, evs=(6, 7, 8, 9, 10, 11))
    raw_candidate = (2).to_bytes(4, "little") + first + second + bytes(PARTY_POKEMON_SIZE * 4)
    raw_primary = (0).to_bytes(4, "little") + bytes(PARTY_POKEMON_SIZE * 6)
    payload = SimpleNamespace(
        payload={
            "party_count": 0,
            "party_count_valid": True,
            "party_address": "0x0227E1C4",
            "raw_party_hex": raw_primary.hex(),
            "party_candidates": [
                {
                    "relative_offset": "0xD120",
                    "address": "0x0227E25C",
                    "party_count": 2,
                    "raw_party_hex": raw_candidate.hex(),
                }
            ],
        }
    )

    party = BizHawkRamDataSource()._decode_party_payload(payload)

    assert party is not None
    assert party.party_count == 2
    assert party.candidate_count == 1
    assert [pokemon.species for pokemon in party.pokemon] == ["Slakoth", "Spearow"]
    assert all(pokemon.checksum_valid for pokemon in party.pokemon)


def test_bizhawk_display_holds_last_valid_slot_during_bad_ram_sample() -> None:
    source = BizHawkRamDataSource()
    payload = SimpleNamespace(
        payload={"run_id": "test-run", "core": "NDS", "domain": "Main RAM"}
    )
    valid_raw = (1).to_bytes(4, "little") + _party_record(
        pid=0x12345678, species_id=179, evs=(1, 2, 3, 4, 5, 6), nickname="sheepy"
    ) + bytes(PARTY_POKEMON_SIZE * 5)
    valid_state = decode_party(valid_raw)

    initial_display = source._stabilize_display_party(valid_state, payload)

    assert initial_display is not None
    assert initial_display.pokemon[0].species == "Mareep"
    assert not initial_display.pokemon[0].sample_stale

    invalid_record = bytearray(
        _party_record(
            pid=0x12345678,
            species_id=500,
            evs=(100, 100, 100, 100, 100, 100),
            nickname="glitch",
        )
    )
    invalid_record[0x08] ^= 0x01
    invalid_raw = (1).to_bytes(4, "little") + invalid_record + bytes(PARTY_POKEMON_SIZE * 5)
    invalid_state = decode_party(invalid_raw)
    display_state = source._stabilize_display_party(invalid_state, payload)

    assert not invalid_state.pokemon[0].checksum_valid
    assert display_state is not None
    assert display_state.pokemon[0].species == "Mareep"
    assert display_state.pokemon[0].nickname == "sheepy"
    assert display_state.pokemon[0].decoded.diagnostics.pid == 0x12345678
    assert display_state.pokemon[0].sample_stale
    assert "slot(s) 1" in display_state.live_read_warning


def test_bizhawk_display_holds_sane_battle_stats_for_same_pid() -> None:
    source = BizHawkRamDataSource()
    payload = SimpleNamespace(payload={"run_id": "test-run"})
    valid_state = decode_party(
        (1).to_bytes(4, "little")
        + _party_record(
            pid=0x12345678,
            species_id=16,
            evs=(0, 0, 0, 0, 0, 0),
            level=6,
            current_hp=21,
            max_hp=21,
        )
        + bytes(PARTY_POKEMON_SIZE * 5)
    )
    source._stabilize_display_party(valid_state, payload)
    invalid_stats_state = decode_party(
        (1).to_bytes(4, "little")
        + _party_record(
            pid=0x12345678,
            species_id=16,
            evs=(0, 0, 0, 0, 0, 0),
            level=4,
            current_hp=53720,
            max_hp=43591,
        )
        + bytes(PARTY_POKEMON_SIZE * 5)
    )

    display_state = source._stabilize_display_party(invalid_stats_state, payload)

    assert invalid_stats_state.pokemon[0].checksum_valid
    assert not invalid_stats_state.pokemon[0].decoded.diagnostics.battle_stats_valid
    assert display_state is not None
    pokemon = display_state.pokemon[0]
    assert pokemon.species == "Pidgey"
    assert pokemon.level == 6
    assert pokemon.current_hp == 21
    assert pokemon.max_hp == 21
    assert pokemon.battle_stats_stale
    assert not pokemon.sample_stale
    assert "last sane level/HP" in display_state.live_read_warning


def test_bizhawk_display_withholds_bad_battle_stats_without_matching_pid_cache() -> None:
    source = BizHawkRamDataSource()
    payload = SimpleNamespace(payload={"run_id": "test-run"})
    invalid_stats_state = decode_party(
        (1).to_bytes(4, "little")
        + _party_record(
            pid=0x12345678,
            species_id=16,
            evs=(0, 0, 0, 0, 0, 0),
            level=4,
            current_hp=53720,
            max_hp=43591,
        )
        + bytes(PARTY_POKEMON_SIZE * 5)
    )

    display_state = source._stabilize_display_party(invalid_stats_state, payload)

    assert display_state is not None
    assert display_state.pokemon[0].level is None
    assert display_state.pokemon[0].current_hp is None
    assert display_state.pokemon[0].max_hp is None
    assert display_state.pokemon[0].battle_stats_stale
    assert "level/HP withheld" in display_state.live_read_warning


def test_bizhawk_display_omits_unverified_slot_until_valid_sample_arrives() -> None:
    source = BizHawkRamDataSource()
    payload = SimpleNamespace(payload={"run_id": "test-run"})
    invalid_record = bytearray(
        _party_record(pid=1, species_id=500, evs=(1, 2, 3, 4, 5, 6))
    )
    invalid_record[0x08] ^= 0x01
    invalid_state = decode_party(
        (1).to_bytes(4, "little") + invalid_record + bytes(PARTY_POKEMON_SIZE * 5)
    )

    display_state = source._stabilize_display_party(invalid_state, payload)

    assert display_state is not None
    assert display_state.pokemon == ()
    assert display_state.live_read_warning == "Waiting for checksum-valid RAM data in slot(s) 1."


def test_bizhawk_display_accepts_recovered_valid_sample() -> None:
    source = BizHawkRamDataSource()
    payload = SimpleNamespace(payload={"run_id": "test-run"})
    valid_state = decode_party(
        (1).to_bytes(4, "little")
        + _party_record(pid=1, species_id=179, evs=(0, 0, 0, 0, 0, 0))
        + bytes(PARTY_POKEMON_SIZE * 5)
    )
    source._stabilize_display_party(valid_state, payload)
    recovered_state = decode_party(
        (1).to_bytes(4, "little")
        + _party_record(pid=2, species_id=443, evs=(1, 0, 0, 0, 0, 0))
        + bytes(PARTY_POKEMON_SIZE * 5)
    )

    display_state = source._stabilize_display_party(recovered_state, payload)

    assert display_state is not None
    assert display_state.pokemon[0].species == "Gible"
    assert display_state.pokemon[0].decoded.diagnostics.pid == 2
    assert not display_state.pokemon[0].sample_stale
    assert display_state.live_read_warning is None


def test_platinum_main_ram_translation_documents_bizhawk_domain_offset() -> None:
    assert PLATINUM_US.main_ram_offset(0x02101D2C) == 0x00101D2C
    assert PLATINUM_US.player_party_relative_offset == 0xD088
    assert 0xD094 in PLATINUM_US.player_party_relative_offset_candidates


def test_encrypt_decrypt_roundtrip() -> None:
    pid = 0x12345678
    plain = _plain_box(species_id=253, evs=(0, 32, 0, 28, 0, 4))
    checksum = calculate_checksum(plain)

    encrypted = encrypt_box_data(plain, pid, checksum)

    assert decrypt_box_data(encrypted, pid, checksum) == plain


def _plain_box(
    species_id: int,
    evs: tuple[int, int, int, int, int, int],
    nickname_codes: tuple[int, ...] = (),
    nickname_terminated: bool = True,
    held_item_id: int = 0,
    ability_id: int = 0,
    ivs: tuple[int, int, int, int, int, int] = (0, 0, 0, 0, 0, 0),
    is_egg: bool = False,
    has_nickname: bool = False,
    friendship: int = 0,
    moves: tuple[int, int, int, int] = (0, 0, 0, 0),
) -> bytes:
    hp, attack, defense, speed, special_attack, special_defense = evs
    data = bytearray(BOX_DATA_SIZE)
    data[0x00:0x02] = species_id.to_bytes(2, "little")
    data[0x02:0x04] = held_item_id.to_bytes(2, "little")
    data[FRIENDSHIP_BOX_DATA_OFFSET] = friendship
    data[0x0D] = ability_id
    data[0x08:0x0C] = (125000).to_bytes(4, "little")
    data[0x10:0x16] = bytes((hp, attack, defense, speed, special_attack, special_defense))
    for index, move_id in enumerate(moves):
        offset = 0x20 + index * 2
        data[offset : offset + 2] = move_id.to_bytes(2, "little")
    hp_iv, attack_iv, defense_iv, speed_iv, special_attack_iv, special_defense_iv = ivs
    packed_ivs = (
        hp_iv
        | (attack_iv << 5)
        | (defense_iv << 10)
        | (speed_iv << 15)
        | (special_attack_iv << 20)
        | (special_defense_iv << 25)
        | (int(is_egg) << 30)
        | (int(has_nickname) << 31)
    )
    data[0x30:0x34] = packed_ivs.to_bytes(4, "little")
    if nickname_codes:
        encoded = b"".join(code.to_bytes(2, "little") for code in nickname_codes)
        if nickname_terminated:
            encoded += b"\xff\xff"
        data[0x40 : 0x40 + len(encoded)] = encoded
    return bytes(data)


def _party_record(
    pid: int,
    species_id: int,
    evs: tuple[int, int, int, int, int, int],
    level: int = 10,
    current_hp: int = 30,
    max_hp: int = 60,
    nickname: str | None = None,
    nickname_codes: tuple[int, ...] = (),
    nickname_terminated: bool = True,
    held_item_id: int = 0,
    ability_id: int = 0,
    ivs: tuple[int, int, int, int, int, int] = (0, 0, 0, 0, 0, 0),
    is_egg: bool = False,
    has_nickname: bool = False,
    attack_stat: int = 49,
    defense_stat: int = 49,
    speed_stat: int = 45,
    special_attack_stat: int = 65,
    special_defense_stat: int = 65,
    friendship: int = 0,
    moves: tuple[int, int, int, int] = (0, 0, 0, 0),
) -> bytes:
    if nickname is not None:
        nickname_codes = _encode_gen4_nickname(nickname)
    plain = _plain_box(
        species_id,
        evs,
        nickname_codes,
        nickname_terminated,
        held_item_id,
        ability_id,
        ivs,
        is_egg,
        has_nickname,
        friendship,
        moves,
    )
    checksum = calculate_checksum(plain)
    encrypted = encrypt_box_data(plain, pid, checksum)
    record = bytearray(PARTY_POKEMON_SIZE)
    record[0x00:0x04] = pid.to_bytes(4, "little")
    record[0x06:0x08] = checksum.to_bytes(2, "little")
    record[0x08 : 0x08 + BOX_DATA_SIZE] = encrypted
    battle_stats = bytearray(0x14)
    battle_stats[0x04] = level
    battle_stats[0x06:0x08] = current_hp.to_bytes(2, "little")
    battle_stats[0x08:0x0A] = max_hp.to_bytes(2, "little")
    battle_stats[0x0A:0x0C] = attack_stat.to_bytes(2, "little")
    battle_stats[0x0C:0x0E] = defense_stat.to_bytes(2, "little")
    battle_stats[0x0E:0x10] = speed_stat.to_bytes(2, "little")
    battle_stats[0x10:0x12] = special_attack_stat.to_bytes(2, "little")
    battle_stats[0x12:0x14] = special_defense_stat.to_bytes(2, "little")
    record[0x88:0x9C] = xor_words(bytes(battle_stats), pid)
    return bytes(record)


def _encode_gen4_nickname(nickname: str) -> tuple[int, ...]:
    codes = []
    for character in nickname:
        if "0" <= character <= "9":
            codes.append(0x121 + ord(character) - ord("0"))
        elif "A" <= character <= "Z":
            codes.append(0x12B + ord(character) - ord("A"))
        elif "a" <= character <= "z":
            codes.append(0x145 + ord(character) - ord("a"))
        elif character == " ":
            codes.append(0x1DE)
        elif character == "é":
            codes.append(0x188)
        elif character == "!":
            codes.append(0x1AB)
        else:
            raise ValueError(f"Test helper does not encode {character!r}.")
    return tuple(codes)
