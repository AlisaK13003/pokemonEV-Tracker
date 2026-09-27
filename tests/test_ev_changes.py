from __future__ import annotations

from types import SimpleNamespace

from pokemon_ev_tracker.core.ev_changes import EVChangeTracker


def _member(pid: int, slot: int, evs: dict[str, int], valid: bool = True):
    return SimpleNamespace(
        slot=slot,
        species="Mareep",
        nickname="sheepy",
        checksum_valid=valid,
        evs=evs,
        decoded=SimpleNamespace(diagnostics=SimpleNamespace(pid=pid)),
    )


def _party(*members):
    return SimpleNamespace(party_count_valid=True, pokemon=members)


def test_ev_change_tracker_uses_pid_identity_and_reports_actual_deltas() -> None:
    tracker = EVChangeTracker()
    initial = {
        "hp": 0,
        "attack": 0,
        "defense": 0,
        "special_attack": 0,
        "special_defense": 0,
        "speed": 0,
    }
    updated = {**initial, "attack": 4, "speed": 1}

    assert tracker.observe(_party(_member(0x1234, 1, initial))) == ()
    changes = tracker.observe(_party(_member(0x1234, 3, updated)))

    assert [(item.stat, item.before, item.after, item.delta) for item in changes] == [
        ("attack", 0, 4, 4),
        ("speed", 0, 1, 1),
    ]
    assert all(item.slot == 3 for item in changes)


def test_ev_change_tracker_skips_invalid_checksums_and_invalid_party_state() -> None:
    tracker = EVChangeTracker()
    evs = {
        "hp": 0,
        "attack": 0,
        "defense": 0,
        "special_attack": 0,
        "special_defense": 0,
        "speed": 0,
    }

    assert tracker.observe(_party(_member(1, 1, evs, valid=False))) == ()
    assert tracker.observe(SimpleNamespace(party_count_valid=False, pokemon=())) == ()


def test_ev_change_tracker_skips_stale_display_samples() -> None:
    tracker = EVChangeTracker()
    initial = {"hp": 0, "attack": 0, "defense": 0, "special_attack": 0, "special_defense": 0, "speed": 0}
    changed = {**initial, "attack": 5}
    valid = _member(1, 1, initial)
    stale = _member(1, 1, changed)
    stale.sample_stale = True

    assert tracker.observe(_party(valid)) == ()
    assert tracker.observe(_party(stale)) == ()
    assert [change.delta for change in tracker.observe(_party(_member(1, 1, changed)))] == [5]
