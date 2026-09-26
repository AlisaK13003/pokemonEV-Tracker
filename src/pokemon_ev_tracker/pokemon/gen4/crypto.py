"""Generation IV Pokemon encryption helpers."""

from __future__ import annotations

BLOCK_SIZE = 32
BOX_DATA_SIZE = 128

BLOCK_ORDERS: tuple[str, ...] = (
    "ABCD",
    "ABDC",
    "ACBD",
    "ACDB",
    "ADBC",
    "ADCB",
    "BACD",
    "BADC",
    "BCAD",
    "BCDA",
    "BDAC",
    "BDCA",
    "CABD",
    "CADB",
    "CBAD",
    "CBDA",
    "CDAB",
    "CDBA",
    "DABC",
    "DACB",
    "DBAC",
    "DBCA",
    "DCAB",
    "DCBA",
)


def prng(seed: int):
    """Yield Gen IV upper-16-bit PRNG outputs."""

    value = seed & 0xFFFFFFFF
    while True:
        value = (0x41C64E6D * value + 0x6073) & 0xFFFFFFFF
        yield (value >> 16) & 0xFFFF


def shuffle_index(pid: int) -> int:
    return ((pid & 0x3E000) >> 13) % 24


def block_order(pid: int) -> str:
    return BLOCK_ORDERS[shuffle_index(pid)]


def xor_words(data: bytes, seed: int) -> bytes:
    if len(data) % 2 != 0:
        raise ValueError("Gen IV encrypted data must contain whole 16-bit words.")
    output = bytearray()
    rng = prng(seed)
    for index in range(0, len(data), 2):
        word = int.from_bytes(data[index : index + 2], "little")
        output.extend((word ^ next(rng)).to_bytes(2, "little"))
    return bytes(output)


def unshuffle_blocks(shuffled: bytes, pid: int) -> bytes:
    if len(shuffled) != BOX_DATA_SIZE:
        raise ValueError("Gen IV boxed data must be 128 bytes.")
    blocks = [shuffled[index : index + BLOCK_SIZE] for index in range(0, BOX_DATA_SIZE, BLOCK_SIZE)]
    unshuffled: list[bytes | None] = [None, None, None, None]
    for encrypted_index, block_name in enumerate(block_order(pid)):
        source_index = ord(block_name) - ord("A")
        unshuffled[source_index] = blocks[encrypted_index]
    if any(block is None for block in unshuffled):
        raise ValueError("Could not unshuffle Gen IV blocks.")
    return b"".join(block for block in unshuffled if block is not None)


def shuffle_blocks(unshuffled: bytes, pid: int) -> bytes:
    if len(unshuffled) != BOX_DATA_SIZE:
        raise ValueError("Gen IV boxed data must be 128 bytes.")
    blocks = {
        name: unshuffled[index * BLOCK_SIZE : (index + 1) * BLOCK_SIZE]
        for index, name in enumerate("ABCD")
    }
    return b"".join(blocks[name] for name in block_order(pid))


def decrypt_box_data(encrypted: bytes, pid: int, checksum: int) -> bytes:
    return unshuffle_blocks(xor_words(encrypted, checksum), pid)


def encrypt_box_data(unencrypted: bytes, pid: int, checksum: int) -> bytes:
    return xor_words(shuffle_blocks(unencrypted, pid), checksum)


def calculate_checksum(unencrypted: bytes) -> int:
    if len(unencrypted) != BOX_DATA_SIZE:
        raise ValueError("Gen IV checksum data must be 128 bytes.")
    total = 0
    for index in range(0, len(unencrypted), 2):
        total += int.from_bytes(unencrypted[index : index + 2], "little")
    return total & 0xFFFF
