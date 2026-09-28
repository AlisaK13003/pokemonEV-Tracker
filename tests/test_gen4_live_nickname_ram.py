from __future__ import annotations

from pokemon_ev_tracker.games.platinum.decoder import decode_party
from pokemon_ev_tracker.pokemon.gen4.structure import PARTY_POKEMON_SIZE

# Checksum-valid party records recorded from local BizHawk frame 4451430.
_LIVE_RECORDS = (
    (
        "Spearow",
        "speary",
        """
        35e56fd20000ad81c8600261ab83035285271603a4713baecb2da75c7e37a6e0e70f574a016b14030fdad9c7772cf738
        1f9e2e2ba8a8994266cfab3ef6008e26ea02fee0ef15a263a977466ccb2819ba4fac115aba95c17dc0235de93395270c
        8f9601d6aec20be02b5863386cca54d6968162a9790577ea86ab6fb5e39f97e5c3988d86d9e7b5ad796dcfbec8b20f53
        aaf80241309eaaba1b2b0f307302b91e618d4f2db178866c8ad13168c4dea2acc6e7b28915079edaeba4abb6a9f490b7
        6ef216f8fc39b3dabdb1d11479dc7aed1fa2de324a0c49b0b6377a6090ff768a404cd60db74848e30f42cb8c
        """,
    ),
    (
        "Mareep",
        "sheepy",
        """
        bd680f150000c9170c7509571e24d4815d09b506693f1b8ee3fef168c4b74b94e29670002b53d535af96bd6b7246f255
        4e418945c881a2854240ef81c3e8c7984d8aa25f71182f886a187a95c4ffdd6e2217311f0bd3d9a0ad06ad95fd7d7594
        34d1e9d6456e332c26e0f3e06466de416b8cd6d94c5e84f2c44ea0e5ab906baf5ec6e080f196546aa7a86c53802b0567
        5f46c264383632c9a45081c423ad033ca854ae49a02b9b6f49f4da9692be81e015a8db6a38127bb64342b558a6d6b1ee
        d3c5b161bcce425ed4fcac5a2291155bc6370e80faa276414e59299a71818b7dfdd72f9ed8808cb1d7d6f449
        """,
    ),
    (
        "Gible",
        "sharky",
        """
        12ef9574000018d2bad72b8a4282ded7ecf3c27e200587e101b8699b34181a811b4b0300f13e6c51d9dc9792ab3fbfc2
        212bb3ca50943b658793fc2dd9550280c6927aec908d5df60f609a6cb2282b715c7c01ecf6e8734d29fe785072320ac3
        ce7392827bcaa47789068ae8d07f3bf906ef707caca77924bcd577027aa062bf46a6666de06ab1209acc32dac2978ea7
        ae614186e3f7f4fa773638557991e2e87ce4a8f069c0b874133c7d0508fb6650a66a1b8c60ddf1d823852ec7033831d7
        c3d1cfa4c84fa04ea3ed796133bf8de30b3abea95cfd9595832dc732c16420568328f7ce638b4847df65907d
        """,
    ),
)


def test_live_bizhawk_party_records_decode_complete_nicknames_and_diagnostics() -> None:
    records = tuple(bytes.fromhex(record_hex) for _, _, record_hex in _LIVE_RECORDS)
    raw_party = (
        len(records).to_bytes(4, "little")
        + b"".join(records)
        + bytes(PARTY_POKEMON_SIZE * (6 - len(records)))
    )
    party_address = 0x0227E1C4

    party = decode_party(raw_party, base_address=party_address)

    assert party.party_count_valid
    assert [(pokemon.species, pokemon.nickname) for pokemon in party.pokemon] == [
        (species, nickname) for species, nickname, _ in _LIVE_RECORDS
    ]
    for index, pokemon in enumerate(party.pokemon):
        diagnostics = pokemon.decoded.nickname_diagnostics
        assert pokemon.checksum_valid
        assert diagnostics.record_relative_offset == 0x48
        assert diagnostics.box_data_relative_offset == 0x40
        assert diagnostics.absolute_address == (
            party_address + 4 + index * PARTY_POKEMON_SIZE + 0x48
        )
        assert len(diagnostics.raw_bytes_hex.split()) == 0x16
        assert diagnostics.terminator_unit_index == 6
        assert diagnostics.decoded_string == pokemon.nickname
        assert diagnostics.decoded_characters[:6] == tuple(pokemon.nickname)

    assert [
        (pokemon.species, pokemon.met_location_id, pokemon.met_location_name, pokemon.met_level)
        for pokemon in party.pokemon
    ] == [
        ("Spearow", 0x11, "Route 202", 4),
        ("Mareep", 0x12, "Route 203", 5),
        ("Gible", 0x10, "Route 201", 5),
    ]
    assert all(pokemon.origin_game == 12 for pokemon in party.pokemon)
    assert all(pokemon.met_date == (26, 9, 26) for pokemon in party.pokemon)
    assert all(pokemon.egg_location_id == 0 and not pokemon.is_egg for pokemon in party.pokemon)
    assert [pokemon.stable_id for pokemon in party.pokemon] == [
        "pid:D26FE535:ot:A500:2BE1",
        "pid:150F68BD:ot:A500:2BE1",
        "pid:7495EF12:ot:A500:2BE1",
    ]
    metadata = party.pokemon[0].decoded.acquisition_metadata_diagnostics
    assert metadata.met_location_record_offset == 0x46
    assert metadata.met_location_box_data_offset == 0x3E
    assert metadata.met_level_record_offset == 0x84
    assert metadata.met_level_box_data_offset == 0x7C
    assert metadata.met_date_record_offset == 0x7B
    assert metadata.met_date_box_data_offset == 0x73
