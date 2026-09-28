"""Platinum met-location IDs and their Nuzlocke encounter normalization."""

from __future__ import annotations

from pokemon_ev_tracker.core.nuzlocke.models import NuzlockeGameProfile

PLATINUM_MET_LOCATION_NAMES = {
    0x0001: "Twinleaf Town",
    0x0002: "Sandgem Town",
    0x0003: "Floaroma Town",
    0x0004: "Solaceon Town",
    0x0005: "Celestic Town",
    0x0006: "Jubilife City",
    0x0007: "Canalave City",
    0x0008: "Oreburgh City",
    0x0009: "Eterna City",
    0x000A: "Hearthome City",
    0x000B: "Pastoria City",
    0x000C: "Veilstone City",
    0x000D: "Sunyshore City",
    0x000E: "Snowpoint City",
    0x000F: "Pokémon League",
    **{0x10 + index: f"Route {201 + index}" for index in range(30)},
    0x2E: "Oreburgh Mine",
    0x2F: "Valley Windworks",
    0x30: "Eterna Forest",
    0x31: "Fuego Ironworks",
    0x32: "Mt. Coronet",
    0x33: "Spear Pillar",
    0x34: "Great Marsh",
    0x35: "Solaceon Ruins",
    0x36: "Victory Road",
    0x37: "Pal Park",
    0x38: "Amity Square",
    0x39: "Ravaged Path",
    0x3A: "Floaroma Meadow",
    0x3B: "Oreburgh Gate",
    0x3C: "Fullmoon Island",
    0x3D: "Sendoff Spring",
    0x3E: "Turnback Cave",
    0x3F: "Flower Paradise",
    0x40: "Snowpoint Temple",
    0x41: "Wayward Cave",
    0x42: "Ruin Maniac Cave",
    0x43: "Maniac Tunnel",
    0x44: "Trophy Garden",
    0x45: "Iron Island",
    0x46: "Old Chateau",
    0x47: "Galactic HQ",
    0x48: "Verity Lakefront",
    0x49: "Valor Lakefront",
    0x4A: "Acuity Lakefront",
    0x4B: "Spring Path",
    0x4C: "Lake Verity",
    0x4D: "Lake Valor",
    0x4E: "Lake Acuity",
    0x4F: "Newmoon Island",
    0x50: "Battle Tower",
    0x51: "Fight Area",
    0x52: "Survival Area",
    0x53: "Resort Area",
    0x54: "Stark Mountain",
    0x55: "Seabreak Path",
    0x56: "Hall of Origin",
    0x57: "Verity Cavern",
    0x58: "Valor Cavern",
    0x59: "Acuity Cavern",
    0x5A: "Jubilife TV",
    0x5B: "Pokétch Company",
    0x5C: "GTS",
    0x5D: "Trainers' School",
    0x5E: "Mining Museum",
    0x5F: "Flower Shop",
    0x60: "Cycle Shop",
    0x61: "Contest Hall",
    0x62: "Poffin House",
    0x63: "Foreign Building",
    0x64: "Pokémon Day Care",
    0x65: "Veilstone Store",
    0x66: "Game Corner",
    0x67: "Canalave Library",
    0x68: "Vista Lighthouse",
    0x69: "Sunyshore Market",
    0x6A: "Pokémon Mansion",
    0x6B: "Footstep House",
    0x6C: "Café",
    0x6D: "Grand Lake",
    0x6E: "Restaurant",
    0x6F: "Battle Park",
    0x70: "Battle Frontier",
    0x71: "Battle Factory",
    0x72: "Battle Castle",
    0x73: "Battle Arcade",
    0x74: "Battle Hall",
    0x75: "Distortion World",
    0x76: "Global Terminal",
    0x77: "Villa",
    0x78: "Battleground",
    0x79: "Rotom's Room",
    0x7A: "T.G. Eterna Building",
    0x7B: "Iron Ruins",
    0x7C: "Iceberg Ruins",
    0x7D: "Rock Peak Ruins",
}

_WILD_MET_LOCATION_IDS = frozenset(
    {
        0x01,  # Twinleaf Town: fishing and surfing
        0x05,  # Celestic Town: fishing and surfing
        0x07,  # Canalave City: surfing
        0x09,  # Eterna City: fishing and surfing
        0x0B,  # Pastoria City: fishing and surfing
        0x0D,  # Sunyshore City: surfing
        0x0F,  # Pokémon League: fishing and surfing
        *range(0x10, 0x2E),
        0x2E,
        0x2F,
        0x30,
        0x31,
        0x32,
        0x34,
        0x35,
        0x36,
        0x39,
        0x3A,
        0x3B,
        0x3D,
        0x3E,
        0x40,
        0x41,
        0x42,
        0x43,
        0x45,
        0x46,
        0x48,
        0x49,
        0x4A,
        0x4B,
        0x4C,
        0x4D,
        0x4E,
        0x54,
        0x53,
    }
)
_STATIC_EVENT_LOCATION_IDS = frozenset(
    {0x33, 0x3C, 0x3F, 0x4F, 0x55, 0x56, 0x57, 0x58, 0x59, 0x75}
)
_GIFT_ONLY_LOCATION_IDS = frozenset({0x08, 0x0A, 0x5E})

_STARTER_SPECIES_IDS = frozenset({387, 388, 389, 390, 391, 392, 393, 394, 395})
_PLATINUM_ORIGIN_GAME = 12
_STARTER_ROW_ID = "platinum-starter"


def platinum_met_location_name(location_id: int) -> str | None:
    return PLATINUM_MET_LOCATION_NAMES.get(location_id)


def platinum_nuzlocke_location_id(location_id: int, profile: NuzlockeGameProfile) -> str | None:
    met_name = platinum_met_location_name(location_id)
    if met_name is None:
        return None
    normalized = _normalize_location_name(met_name)
    aliases = {
        "oreburgh gate 1f": "oreburgh gate",
        "oreburgh gate b1f": "oreburgh gate",
        "wayward cave basement": "wayward cave (basement)",
        "mt coronet summit": "spear pillar",
    }
    normalized = aliases.get(normalized, normalized)
    return next(
        (
            location.location_id
            for location in profile.locations
            if _normalize_location_name(location.name) == normalized
        ),
        None,
    )


def classify_platinum_acquisition(
    candidate, run=None, *, first_party_member: bool = False
) -> tuple[str, str, str | None]:
    """Return source, confidence, and suggested run-location ID."""
    if candidate.is_egg or candidate.egg_location_id:
        return "EGG", "HIGH", None
    if candidate.origin_game and candidate.origin_game != _PLATINUM_ORIGIN_GAME:
        return "TRADE", "MEDIUM", None

    profile = _profile_from_run(run)
    if profile is None:
        return "UNKNOWN", "LOW", None

    location_id = platinum_nuzlocke_location_id(candidate.met_location_id, profile)
    starter = run.encounters.get(_STARTER_ROW_ID) if run is not None else None
    starter_unassigned = run is not None and (
        starter is None or _encounter_is_unused(starter)
    )
    if first_party_member and starter_unassigned:
        return "STARTER", "HIGH", _STARTER_ROW_ID
    if candidate.met_location_id == 0x10 and starter_unassigned:
        if (
            starter is not None
            and candidate.species_id in _STARTER_SPECIES_IDS
            and candidate.met_level == 5
            and candidate.origin_game == _PLATINUM_ORIGIN_GAME
        ):
            return "STARTER", "MEDIUM", _STARTER_ROW_ID
        return "UNKNOWN", "MEDIUM", location_id
    if candidate.met_location_id in _STATIC_EVENT_LOCATION_IDS:
        return "STATIC", "MEDIUM", None
    if candidate.met_location_id in _GIFT_ONLY_LOCATION_IDS:
        return "GIFT", "MEDIUM", None
    if candidate.met_location_id in _WILD_MET_LOCATION_IDS and location_id is not None:
        return "WILD", "HIGH", location_id
    return "UNKNOWN", "LOW", None


def _profile_from_run(run):
    # Kept lazy to avoid coupling the generic acquisition model to a game profile.
    from pokemon_ev_tracker.games.platinum.nuzlocke import PLATINUM_NUZLOCKE_PROFILE

    if run is None or run.game == PLATINUM_NUZLOCKE_PROFILE.game_id:
        return PLATINUM_NUZLOCKE_PROFILE
    return None


def _encounter_is_unused(encounter) -> bool:
    return encounter.status == "NOT_ENCOUNTERED" and not encounter.species


def _normalize_location_name(name: str) -> str:
    return " ".join(name.casefold().replace("pokémon", "pokemon").split())
