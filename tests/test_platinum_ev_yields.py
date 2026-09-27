from pokemon_ev_tracker.games.platinum.ev_yields import format_ev_yield, get_ev_yield


def test_ev_yield_data_includes_known_platinum_species() -> None:
    assert get_ev_yield(16) == {
        "hp": 0,
        "attack": 0,
        "defense": 0,
        "special_attack": 0,
        "special_defense": 0,
        "speed": 1,
    }
    assert format_ev_yield(16) == "EV yield: +1 Speed"
    assert format_ev_yield(179) == "EV yield: +1 Sp. Atk"


def test_ev_yield_unknown_species_is_handled_cleanly() -> None:
    assert get_ev_yield(0) is None
    assert get_ev_yield("not-a-species") is None
    assert format_ev_yield(0) == "EV yield unavailable"
