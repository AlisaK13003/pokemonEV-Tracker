"""Decode individual Generation IV party Pokemon records."""

from __future__ import annotations

from dataclasses import dataclass

from pokemon_ev_tracker.pokemon.gen4.crypto import (
    BOX_DATA_SIZE,
    block_order,
    calculate_checksum,
    decrypt_box_data,
    shuffle_index,
    xor_words,
)

PARTY_POKEMON_SIZE = 236
POKEMON_HEADER_SIZE = 0x08
HELD_ITEM_BOX_DATA_OFFSET = 0x02
HELD_ITEM_RECORD_OFFSET = POKEMON_HEADER_SIZE + HELD_ITEM_BOX_DATA_OFFSET
# Published PKM offsets include this header; decrypt_box_data returns bytes after it.
NICKNAME_RECORD_OFFSET = 0x48
NICKNAME_BOX_DATA_OFFSET = NICKNAME_RECORD_OFFSET - POKEMON_HEADER_SIZE
NICKNAME_FIELD_SIZE = 0x16

_GEN4_INTL_CHARACTERS = (
    "\0　ぁあぃいぅうぇえぉおかがきぎ"
    "くぐけげこごさざしじすずせぜそぞ"
    "ただちぢっつづてでとどなにぬねの"
    "はばぱひびぴふぶぷへべぺほぼぽま"
    "みむめもゃやゅゆょよらりるれろわ"
    "をんァアィイゥウェエォオカガキギ"
    "クグケゲコゴサザシジスズセゼソゾ"
    "タダチヂッツヅテデトドナニヌネノ"
    "ハバパヒビピフブプヘベペホボポマ"
    "ミムメモャヤュユョヨラリルレロワ"
    "ヲン０１２３４５６７８９ＡＢＣＤ"
    "ＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴ"
    "ＵＶＷＸＹＺａｂｃｄｅｆｇｈｉｊ"
    "ｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ"
    "\uffff！？，。…・／「」『』（）♂♀"
    "＋ー×÷＝～：；．，♠♣♥♦★◎"
    "○□△◇＠♪％☀☁☂☃①②③④⑤"
    "⑥⑦円♈♉♊♋♌♍♎♏←↑↓→►"
    "＆0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    "ÀÁÂÃÄÅÆÇÈÉÊËÌÍÎÏÐÑÒÓÔÕÖ⑧ØÙÚÛÜÝÞß"
    "àáâãäåæçèéêëìíîïðñòóôõö⑨øùúûüýþÿ"
    "ŒœŞşªº⑩⑪⑫$¡¿!?,.⑬･/‘'“”„«»()♂♀+-*"
    "#=&~:;⑯⑰⑱⑲⑳⑴⑵⑶⑷⑸@⑹%⑺⑻⑼⑽⑾⑿⒀⒁⒂⒃⒄"
    " ⒅⒆⒇⒈⒉⒊⒋⒌⒍°_＿⒎⒏"
)
_GEN4_INTL_CHAR_MAP = {value: character for value, character in enumerate(_GEN4_INTL_CHARACTERS)}


@dataclass(frozen=True)
class EVs:
    hp: int
    attack: int
    defense: int
    special_attack: int
    special_defense: int
    speed: int

    @property
    def total(self) -> int:
        return (
            self.hp
            + self.attack
            + self.defense
            + self.special_attack
            + self.special_defense
            + self.speed
        )


@dataclass(frozen=True)
class PokemonDiagnostics:
    address: int | None
    pid: int
    checksum: int
    calculated_checksum: int
    checksum_valid: bool
    shuffle_index: int
    block_order: str
    sanity_bytes: str


@dataclass(frozen=True)
class NicknameDiagnostics:
    absolute_address: int | None
    record_relative_offset: int
    box_data_relative_offset: int
    raw_bytes_hex: str
    code_units: tuple[int, ...]
    decoded_characters: tuple[str | None, ...]
    terminator_unit_index: int | None
    decoded_string: str | None


@dataclass(frozen=True)
class DecodedPokemon:
    species_id: int
    held_item_id: int
    experience: int
    evs: EVs
    level: int | None
    current_hp: int | None
    max_hp: int | None
    nickname: str | None
    nickname_diagnostics: NicknameDiagnostics
    diagnostics: PokemonDiagnostics


def decode_party_pokemon(
    data: bytes,
    address: int | None = None,
) -> DecodedPokemon:
    if len(data) < PARTY_POKEMON_SIZE:
        raise ValueError("Party Pokemon record must be 236 bytes.")

    pid = int.from_bytes(data[0x00:0x04], "little")
    checksum = int.from_bytes(data[0x06:0x08], "little")
    decrypted = decrypt_box_data(data[0x08 : 0x08 + BOX_DATA_SIZE], pid, checksum)
    calculated_checksum = calculate_checksum(decrypted)
    checksum_valid = calculated_checksum == checksum
    battle_stats = xor_words(data[0x88:0x9C], pid)

    species_id = int.from_bytes(decrypted[0x00:0x02], "little")
    held_item_id = int.from_bytes(
        decrypted[HELD_ITEM_BOX_DATA_OFFSET : HELD_ITEM_BOX_DATA_OFFSET + 2], "little"
    )
    experience = int.from_bytes(decrypted[0x08:0x0C], "little")
    evs = EVs(
        hp=decrypted[0x10],
        attack=decrypted[0x11],
        defense=decrypted[0x12],
        speed=decrypted[0x13],
        special_attack=decrypted[0x14],
        special_defense=decrypted[0x15],
    )
    nickname_raw = decrypted[
        NICKNAME_BOX_DATA_OFFSET : NICKNAME_BOX_DATA_OFFSET + NICKNAME_FIELD_SIZE
    ]
    nickname_diagnostics = _decode_nickname(nickname_raw, address)

    return DecodedPokemon(
        species_id=species_id,
        held_item_id=held_item_id,
        experience=experience,
        evs=evs,
        level=battle_stats[0x04],
        current_hp=int.from_bytes(battle_stats[0x06:0x08], "little"),
        max_hp=int.from_bytes(battle_stats[0x08:0x0A], "little"),
        nickname=nickname_diagnostics.decoded_string,
        nickname_diagnostics=nickname_diagnostics,
        diagnostics=PokemonDiagnostics(
            address=address,
            pid=pid,
            checksum=checksum,
            calculated_checksum=calculated_checksum,
            checksum_valid=checksum_valid,
            shuffle_index=shuffle_index(pid),
            block_order=block_order(pid),
            sanity_bytes=data[:16].hex(" ").upper(),
        ),
    )


def _decode_nickname(raw: bytes, record_address: int | None) -> NicknameDiagnostics:
    code_units = tuple(
        int.from_bytes(raw[index : index + 2], "little") for index in range(0, len(raw) - 1, 2)
    )
    decoded_characters: list[str | None] = []
    decoded_text: list[str] = []
    terminator_unit_index = None
    invalid = len(raw) % 2 != 0

    for index, code in enumerate(code_units):
        if terminator_unit_index is not None:
            decoded_characters.append(None)
            continue
        if code in (0xFFFF, 0x0000):
            terminator_unit_index = index
            decoded_characters.append(None)
            continue
        character = _GEN4_INTL_CHAR_MAP.get(code)
        if character is None:
            invalid = True
            decoded_characters.append(None)
            continue
        if character == "\uffff":
            decoded_characters.append(None)
            continue
        decoded_characters.append(character)
        decoded_text.append(character)

    decoded_string = "".join(decoded_text) if decoded_text and not invalid else None
    return NicknameDiagnostics(
        absolute_address=(
            record_address + NICKNAME_RECORD_OFFSET if record_address is not None else None
        ),
        record_relative_offset=NICKNAME_RECORD_OFFSET,
        box_data_relative_offset=NICKNAME_BOX_DATA_OFFSET,
        raw_bytes_hex=raw.hex(" ").upper(),
        code_units=code_units,
        decoded_characters=tuple(decoded_characters),
        terminator_unit_index=terminator_unit_index,
        decoded_string=decoded_string,
    )
