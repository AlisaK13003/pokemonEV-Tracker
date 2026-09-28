from __future__ import annotations

from pokemon_ev_tracker.games.platinum.coordinate_discovery import (
    CAPTURE_LABELS,
    CoordinateDiscovery,
    CoordinateSnapshot,
    find_coordinate_candidates,
)


def _snapshots(*, unstable_x: bool = False, add_counter: bool = False):
    start = 0x200
    states = {
        "baseline": (40, 12),
        "idle": (41 if unstable_x else 40, 12),
        "right": (41, 12),
        "left": (40, 12),
        "down": (40, 13),
        "up": (40, 12),
    }
    snapshots = {}
    for label in CAPTURE_LABELS:
        data = bytearray(64)
        x, y = states[label]
        data[0x20:0x22] = x.to_bytes(2, "little")
        data[0x22:0x24] = y.to_bytes(2, "little")
        if add_counter:
            counter = 100 + CAPTURE_LABELS.index(label)
            data[0x28:0x2A] = counter.to_bytes(2, "little")
        snapshots[label] = CoordinateSnapshot(label, start, bytes(data))
    return snapshots


def test_snapshot_capture_assembles_chunks_and_completes_snapshot() -> None:
    discovery = CoordinateDiscovery()
    ram = bytes(range(64))

    assert "Capturing baseline" in discovery.accept_event(
        {
            "type": "coordinate_scan_start",
            "capture_id": "sample-1",
            "label": "baseline",
            "start_offset": 0x200,
            "length": len(ram),
        }
    )
    assert discovery.accept_event(
        {
            "type": "coordinate_scan_chunk",
            "capture_id": "sample-1",
            "chunk_offset": 0,
            "data_hex": ram.hex(),
        }
    ) is None
    assert "Captured baseline" in discovery.accept_event(
        {"type": "coordinate_scan_end", "capture_id": "sample-1"}
    )
    assert discovery.snapshots["baseline"].data == ram


def test_stable_axis_moves_rank_the_expected_coordinate_pair() -> None:
    candidates = find_coordinate_candidates(_snapshots())

    assert candidates
    best = candidates[0]
    assert (best.x_offset, best.y_offset) == (0x220, 0x222)
    assert best.data_type == "u16"
    assert (best.right_delta, best.left_delta) == (1, -1)
    assert (best.down_delta, best.up_delta) == (1, -1)
    assert best.idle_stability == 1.0
    assert best.score >= 0.95


def test_idle_drift_is_rejected() -> None:
    assert find_coordinate_candidates(_snapshots(unstable_x=True)) == ()


def test_unrelated_monotonic_counter_is_rejected() -> None:
    candidates = find_coordinate_candidates(_snapshots(add_counter=True))

    assert candidates
    assert all(candidate.x_offset != 0x228 for candidate in candidates)
    assert all(candidate.y_offset != 0x228 for candidate in candidates)


def test_candidate_selection_and_opposite_direction_returns() -> None:
    discovery = CoordinateDiscovery()
    for snapshot in _snapshots().values():
        discovery.add_snapshot(snapshot)

    candidate = discovery.select_candidate(0)

    assert candidate is discovery.candidates[0]
    assert candidate.x_values[2] - candidate.x_values[0] == 1
    assert candidate.x_values[3] == candidate.x_values[0]
    assert candidate.y_values[4] - candidate.y_values[0] == 1
    assert candidate.y_values[5] == candidate.y_values[0]
    assert discovery.select_candidate(100) is None


def test_signed_coordinate_values_are_supported() -> None:
    snapshots = _snapshots()
    signed_states = {
        "baseline": (-8, -3),
        "idle": (-8, -3),
        "right": (-7, -3),
        "left": (-8, -3),
        "down": (-8, -2),
        "up": (-8, -3),
    }
    for label, snapshot in snapshots.items():
        data = bytearray(snapshot.data)
        x, y = signed_states[label]
        data[0x20:0x22] = x.to_bytes(2, "little", signed=True)
        data[0x22:0x24] = y.to_bytes(2, "little", signed=True)
        snapshots[label] = CoordinateSnapshot(label, snapshot.start_offset, bytes(data))

    candidates = find_coordinate_candidates(snapshots)

    assert candidates[0].data_type == "s16"
    assert candidates[0].x_values[0] == -8
    assert candidates[0].y_values[0] == -3


def test_fixed_point_tile_deltas_larger_than_one_are_supported() -> None:
    snapshots = _snapshots()
    for label, snapshot in snapshots.items():
        data = bytearray(snapshot.data)
        x, y = {
            "baseline": (0x1000, 0x2000),
            "idle": (0x1000, 0x2000),
            "right": (0x2000, 0x2000),
            "left": (0x1000, 0x2000),
            "down": (0x1000, 0x3000),
            "up": (0x1000, 0x2000),
        }[label]
        data[0x20:0x22] = x.to_bytes(2, "little")
        data[0x22:0x24] = y.to_bytes(2, "little")
        snapshots[label] = CoordinateSnapshot(label, snapshot.start_offset, bytes(data))

    candidates = find_coordinate_candidates(snapshots)

    assert candidates
    assert candidates[0].right_delta == 0x1000
    assert candidates[0].down_delta == 0x1000


def test_scan_range_change_discards_incompatible_prior_samples() -> None:
    discovery = CoordinateDiscovery()
    for snapshot in _snapshots().values():
        discovery.add_snapshot(snapshot)

    discovery.add_snapshot(CoordinateSnapshot("baseline", 0x400, bytes(64)))

    assert set(discovery.snapshots) == {"baseline"}
    assert discovery.candidates == ()
