"""Encounter locations and important-fight caps for Pokémon Platinum."""

from pokemon_ev_tracker.core.nuzlocke.models import (
    EncounterLocation,
    LevelCap,
    NuzlockeGameProfile,
)

_LEGACY_LOCATION_NAMES = (
    "Twinleaf Town", "Route 201", "Lake Verity", "Sandgem Town", "Route 202",
    "Jubilife City", "Route 204", "Ravaged Path", "Route 203", "Oreburgh Gate",
    "Oreburgh City", "Oreburgh Mine", "Route 207", "Mt. Coronet", "Eterna Forest",
    "Route 205", "Valley Windworks", "Fuego Ironworks", "Floaroma Town", "Floaroma Meadow",
    "Route 206", "Wayward Cave", "Wayward Cave (Basement)", "Route 208", "Hearthome City",
    "Amity Square",
    "Route 209", "Lost Tower", "Solaceon Town", "Solaceon Ruins", "Route 210",
    "Route 215", "Veilstone City", "Route 214", "Maniac Tunnel", "Valor Lakefront",
    "Lake Valor", "Pastoria City", "Route 213", "Route 212",
    "Celestic Town", "Route 211", "Lake Acuity", "Acuity Lakefront", "Snowpoint City",
    "Route 216", "Route 217", "Snowpoint Temple", "Iron Island", "Canalave City",
    "Route 218", "Route 219", "Route 220", "Route 221", "Route 222",
    "Sunyshore City", "Route 223", "Victory Road", "Pokémon League", "Route 224",
    "Spring Path", "Sendoff Spring", "Turnback Cave", "Route 225", "Survival Area",
    "Route 226", "Route 227", "Stark Mountain", "Route 228", "Route 229",
    "Resort Area", "Route 230", "Fullmoon Island", "Newmoon Island", "Flower Paradise",
    "Great Marsh", "Old Chateau", "Trophy Garden", "Distortion World", "Spear Pillar",
)

_ELIGIBLE_LOCATION_NAMES = (
    "Twinleaf Town", "Route 201", "Lake Verity", "Route 202", "Route 204",
    "Ravaged Path", "Route 203", "Oreburgh Gate", "Oreburgh Mine", "Route 207",
    "Mt. Coronet", "Eterna Forest", "Route 205", "Eterna City", "Valley Windworks",
    "Fuego Ironworks", "Floaroma Meadow", "Route 206", "Wayward Cave", "Route 208",
    "Route 209", "Solaceon Ruins", "Route 210", "Route 215", "Route 214",
    "Ruin Maniac Cave", "Maniac Tunnel", "Valor Lakefront", "Lake Valor", "Pastoria City",
    "Route 213", "Route 212", "Celestic Town", "Route 211", "Lake Acuity",
    "Acuity Lakefront", "Route 216", "Route 217", "Snowpoint Temple", "Iron Island",
    "Canalave City", "Route 218", "Route 219", "Route 220", "Route 221", "Route 222",
    "Sunyshore City", "Route 223", "Victory Road", "Pokémon League", "Route 224",
    "Spring Path", "Sendoff Spring", "Turnback Cave", "Route 225", "Route 226",
    "Route 227", "Stark Mountain", "Route 228", "Route 229", "Resort Area", "Route 230",
    "Great Marsh", "Old Chateau", "Trophy Garden",
)
_LEGACY_LOCATION_IDS = {
    name: f"platinum-{index + 1:03d}" for index, name in enumerate(_LEGACY_LOCATION_NAMES)
}
_ADDITIONAL_LOCATION_IDS = {
    "Eterna City": "platinum-081",
    "Ruin Maniac Cave": "platinum-082",
}

PLATINUM_NUZLOCKE_LOCATIONS = (
    EncounterLocation(location_id="platinum-starter", name="Starter", order=0),
    *(
        EncounterLocation(
            location_id=_LEGACY_LOCATION_IDS.get(name) or _ADDITIONAL_LOCATION_IDS[name],
            name=name,
            order=index + 1,
        )
        for index, name in enumerate(_ELIGIBLE_LOCATION_NAMES)
    ),
)

PLATINUM_RETIRED_DEFAULT_LOCATIONS = tuple(
    EncounterLocation(
        location_id=_LEGACY_LOCATION_IDS[name],
        name=name,
        order=index + 1,
    )
    for index, name in enumerate(_LEGACY_LOCATION_NAMES)
    if name not in _ELIGIBLE_LOCATION_NAMES
)

PLATINUM_LOCATIONS = PLATINUM_NUZLOCKE_LOCATIONS

_FIGHTS = (
    ("Roark", "Gym Leader", 14),
    ("Mars - Valley Windworks", "Galactic Boss", 16),
    ("Gardenia", "Gym Leader", 22),
    ("Jupiter - Eterna Building", "Galactic Boss", 22),
    ("Fantina", "Gym Leader", 26),
    ("Maylene", "Gym Leader", 32),
    ("Crasher Wake", "Gym Leader", 30),
    ("Cyrus - Veilstone HQ", "Galactic Boss", 40),
    ("Byron", "Gym Leader", 41),
    ("Mars & Jupiter - Spear Pillar", "Galactic Boss", 45),
    ("Cyrus - Distortion World", "Galactic Boss", 46),
    ("Candice", "Gym Leader", 42),
    ("Volkner", "Gym Leader", 50),
    ("Barry - Victory Road", "Rival", 53),
    ("Aaron", "Elite Four", 57),
    ("Bertha", "Elite Four", 59),
    ("Flint", "Elite Four", 61),
    ("Lucian", "Elite Four", 63),
    ("Cynthia", "Champion", 66),
)

PLATINUM_LEVEL_CAPS = tuple(
    LevelCap(
        cap_id=f"platinum-fight-{index + 1:02d}",
        name=name,
        category=category,
        order=index,
        level_cap=level,
    )
    for index, (name, category, level) in enumerate(_FIGHTS)
)

PLATINUM_NUZLOCKE_PROFILE = NuzlockeGameProfile(
    game_id="pokemon-platinum",
    display_name="Pokémon Platinum",
    locations=PLATINUM_NUZLOCKE_LOCATIONS,
    level_caps=PLATINUM_LEVEL_CAPS,
)
