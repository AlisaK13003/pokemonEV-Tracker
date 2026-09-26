from __future__ import annotations

from types import SimpleNamespace

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
from pokemon_ev_tracker.pokemon.gen4.structure import (
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
) -> bytes:
    hp, attack, defense, speed, special_attack, special_defense = evs
    data = bytearray(BOX_DATA_SIZE)
    data[0x00:0x02] = species_id.to_bytes(2, "little")
    data[0x02:0x04] = held_item_id.to_bytes(2, "little")
    data[0x08:0x0C] = (125000).to_bytes(4, "little")
    data[0x10:0x16] = bytes((hp, attack, defense, speed, special_attack, special_defense))
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
) -> bytes:
    if nickname is not None:
        nickname_codes = _encode_gen4_nickname(nickname)
    plain = _plain_box(
        species_id,
        evs,
        nickname_codes,
        nickname_terminated,
        held_item_id,
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
