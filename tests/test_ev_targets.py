from __future__ import annotations

from pathlib import Path

import pytest

from pokemon_ev_tracker.core.ev_targets import EVTarget, EVTargetStore


@pytest.fixture
def target_file(tmp_path: Path) -> Path:
    return tmp_path / "ev_targets.json"


def test_valid_target_spread_and_total() -> None:
    target = EVTarget(
        hp_target=4,
        attack_target=252,
        speed_target=252,
    )

    assert target.total == 508
    assert target.as_mapping() == {
        "hp": 4,
        "attack": 252,
        "defense": 0,
        "special_attack": 0,
        "special_defense": 0,
        "speed": 252,
    }


def test_target_total_over_510_is_rejected() -> None:
    with pytest.raises(ValueError, match="cannot exceed 510"):
        EVTarget(hp_target=252, attack_target=252, defense_target=7)


def test_per_stat_target_over_252_is_rejected() -> None:
    with pytest.raises(ValueError, match="between 0 and 252"):
        EVTarget(attack_target=253)


def test_targets_persist_by_pid(target_file: Path) -> None:
    path = target_file
    store = EVTargetStore(path)
    target = EVTarget(attack_target=252, speed_target=252)

    store.set(0x1234ABCD, target)
    restored = EVTargetStore(path)

    assert restored.get(0x1234ABCD) == target
    assert "1234ABCD" in path.read_text(encoding="utf-8")


def test_party_reorder_keeps_targets_attached_to_pid(target_file: Path) -> None:
    store = EVTargetStore(target_file)
    targets = {
        0x00000021: EVTarget(attack_target=252),
        0x00000179: EVTarget(hp_target=252),
    }
    for pid, target in targets.items():
        store.set(pid, target)

    reordered_party_pids = (0x00000179, 0x00000021)

    assert [store.get(pid) for pid in reordered_party_pids] == [
        targets[0x00000179],
        targets[0x00000021],
    ]


def test_evolution_with_same_pid_keeps_existing_target(target_file: Path) -> None:
    store = EVTargetStore(target_file)
    pid = 0xAABBCCDD
    target = EVTarget(speed_target=252)
    store.set(pid, target)

    species_before_evolution = "Gible"
    species_after_evolution = "Gabite"

    assert species_before_evolution != species_after_evolution
    assert store.get(pid) == target


def test_target_progress_reports_remaining_and_overshoot() -> None:
    target = EVTarget(attack_target=252, speed_target=252)

    progress = target.progress({"attack": 253, "speed": 157})

    assert progress.achieved == 409
    assert progress.remaining == 95
    assert progress.overshoots == {"attack": 1}
    assert progress.complete is False


def test_target_progress_detects_completion() -> None:
    target = EVTarget(hp_target=4, attack_target=252, speed_target=252)

    progress = target.progress({"hp": 4, "attack": 252, "speed": 252})

    assert progress.complete is True
    assert progress.remaining == 0
    assert progress.achieved == 508


def test_clear_target_removes_only_that_pid_and_persists(target_file: Path) -> None:
    path = target_file
    store = EVTargetStore(path)
    store.set(1, EVTarget(attack_target=252))
    store.set(2, EVTarget(speed_target=252))

    assert store.clear(1) is True
    assert store.clear(1) is False
    restored = EVTargetStore(path)
    assert restored.get(1) is None
    assert restored.get(2) == EVTarget(speed_target=252)
