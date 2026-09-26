"""Registered Pokémon Platinum memory/decoder profile."""

from pokemon_ev_tracker.games.base import GameProfile
from pokemon_ev_tracker.games.platinum.decoder import decode_party
from pokemon_ev_tracker.games.platinum.memory import PLATINUM_US

PLATINUM_PROFILE = GameProfile(
    game_id="pokemon-platinum",
    display_name="Pokémon Platinum",
    supported_emulators=("BizHawk / EmuHawk",),
    supported_cores=("Nintendo DS", "NDS"),
    memory_profile=PLATINUM_US,
    party_decoder=decode_party,
)
