"""RAM snapshot analysis for manually validating Platinum map coordinates."""

from __future__ import annotations

import sys
from array import array
from dataclasses import dataclass

CAPTURE_LABELS = ("baseline", "idle", "right", "left", "down", "up")
MAX_SCAN_BYTES = 0x400000


@dataclass(frozen=True)
class CoordinateSnapshot:
    label: str
    start_offset: int
    data: bytes


@dataclass(frozen=True)
class CoordinateCandidate:
    x_offset: int
    y_offset: int
    data_type: str
    score: float
    idle_stability: float
    right_delta: int
    left_delta: int
    down_delta: int
    up_delta: int
    x_values: tuple[int, ...]
    y_values: tuple[int, ...]

    @property
    def confidence(self) -> str:
        return f"{self.score:.2f}"


@dataclass
class _CaptureAssembly:
    capture_id: str
    label: str
    start_offset: int
    length: int
    data: bytearray
    received_chunks: set[int]


class CoordinateDiscovery:
    """Collects scan events and ranks fixed Main RAM coordinate pairs."""

    def __init__(self) -> None:
        self.snapshots: dict[str, CoordinateSnapshot] = {}
        self.candidates: tuple[CoordinateCandidate, ...] = ()
        self.selected_index: int | None = None
        self._assembly: _CaptureAssembly | None = None

    @property
    def capturing(self) -> bool:
        return self._assembly is not None

    @property
    def ready_to_analyze(self) -> bool:
        return all(label in self.snapshots for label in CAPTURE_LABELS)

    def reset(self) -> None:
        self.snapshots.clear()
        self.candidates = ()
        self.selected_index = None
        self._assembly = None

    def accept_event(self, payload: dict) -> str | None:
        event_type = payload.get("type")
        if event_type == "coordinate_scan_start":
            capture_id = payload.get("capture_id")
            label = payload.get("label")
            start_offset = payload.get("start_offset")
            length = payload.get("length")
            if (
                not isinstance(capture_id, str)
                or label not in CAPTURE_LABELS
                or not isinstance(start_offset, int)
                or not isinstance(length, int)
                or not 0 < length <= MAX_SCAN_BYTES
            ):
                return "Rejected malformed coordinate snapshot header."
            self.snapshots.pop(label, None)
            self.candidates = ()
            self.selected_index = None
            self._assembly = _CaptureAssembly(
                capture_id,
                label,
                start_offset,
                length,
                bytearray(length),
                set(),
            )
            return f"Capturing {label} RAM snapshot ({length:,} bytes)..."

        assembly = self._assembly
        if assembly is None or payload.get("capture_id") != assembly.capture_id:
            return None
        if event_type == "coordinate_scan_chunk":
            offset = payload.get("chunk_offset")
            encoded = payload.get("data_hex")
            if not isinstance(offset, int) or not isinstance(encoded, str):
                return "Rejected malformed coordinate snapshot chunk."
            try:
                chunk = bytes.fromhex(encoded)
            except ValueError:
                return "Rejected malformed coordinate snapshot bytes."
            if offset < 0 or offset + len(chunk) > assembly.length or not chunk:
                return "Rejected out-of-range coordinate snapshot chunk."
            chunk_index = offset // 16384
            expected_offset = chunk_index * 16384
            expected_length = min(16384, assembly.length - expected_offset)
            if offset != expected_offset or len(chunk) != expected_length:
                return "Rejected misaligned coordinate snapshot chunk."
            if chunk_index not in assembly.received_chunks:
                assembly.data[offset : offset + len(chunk)] = chunk
                assembly.received_chunks.add(chunk_index)
            return None

        if event_type == "coordinate_scan_end":
            expected_chunks = (assembly.length + 16383) // 16384
            self._assembly = None
            if len(assembly.received_chunks) != expected_chunks:
                return (
                    f"Snapshot incomplete: received {len(assembly.received_chunks)} of "
                    f"{expected_chunks} chunks."
                )
            self.add_snapshot(
                CoordinateSnapshot(
                    assembly.label,
                    assembly.start_offset,
                    bytes(assembly.data),
                ),
                analyze=False,
            )
            return f"Captured {assembly.label} snapshot."

        if event_type == "coordinate_scan_error":
            self._assembly = None
            return str(payload.get("message") or "Coordinate snapshot failed.")
        return None

    def add_snapshot(self, snapshot: CoordinateSnapshot, *, analyze: bool = True) -> None:
        if snapshot.label not in CAPTURE_LABELS:
            raise ValueError(f"Unknown coordinate snapshot label: {snapshot.label}")
        if not snapshot.data or len(snapshot.data) > MAX_SCAN_BYTES:
            raise ValueError("Coordinate snapshots must contain 1 to 4 MiB of RAM data.")
        previous = next(iter(self.snapshots.values()), None)
        if previous and (
            snapshot.start_offset != previous.start_offset
            or len(snapshot.data) != len(previous.data)
        ):
            self.reset()
        self.snapshots[snapshot.label] = snapshot
        self.candidates = ()
        self.selected_index = None
        if analyze and self.ready_to_analyze:
            self.candidates = find_coordinate_candidates(self.snapshots)

    def analyze(self) -> tuple[CoordinateCandidate, ...]:
        self.candidates = find_coordinate_candidates(self.snapshots)
        self.selected_index = None
        return self.candidates

    def select_candidate(self, index: int | None) -> CoordinateCandidate | None:
        if index is None or not 0 <= index < len(self.candidates):
            self.selected_index = None
            return None
        self.selected_index = index
        return self.candidates[index]


def _word_values(snapshots: tuple[CoordinateSnapshot, ...], word_type: str) -> list[array]:
    values = []
    for snapshot in snapshots:
        words = array("H")
        words.frombytes(snapshot.data[: len(snapshot.data) & ~1])
        if sys.byteorder != "little":
            words.byteswap()
        if word_type == "s16":
            words = array("i", (value - 0x10000 if value & 0x8000 else value for value in words))
        values.append(words)
    return values


def _axis_score(base: int, delta: int) -> float:
    magnitude = abs(delta)
    plausibility = 0.04 if abs(base) <= 2048 else 0.02 if abs(base) <= 8192 else 0.0
    step_score = 0.04 if magnitude == 1 else 0.03 if magnitude <= 16 else 0.01
    return min(1.0, 0.91 + plausibility + step_score)


def find_coordinate_candidates(
    snapshots: dict[str, CoordinateSnapshot], limit: int = 10
) -> tuple[CoordinateCandidate, ...]:
    """Find u16/s16 pairs matching stable, axis-only moves and exact returns."""
    if not all(label in snapshots for label in CAPTURE_LABELS):
        return ()
    ordered = tuple(snapshots[label] for label in CAPTURE_LABELS)
    if any(
        item.start_offset != ordered[0].start_offset
        or len(item.data) != len(ordered[0].data)
        for item in ordered[1:]
    ):
        return ()

    ranked: dict[tuple[int, int], CoordinateCandidate] = {}
    for word_type in ("u16", "s16"):
        values = _word_values(ordered, word_type)
        baseline, idle, right, left, down, up = values
        x_axes: list[tuple[int, int, int, tuple[int, ...], float]] = []
        y_axes: list[tuple[int, int, int, tuple[int, ...], float]] = []
        for index in range(len(baseline)):
            base = baseline[index]
            if idle[index] != base or up[index] != base:
                continue
            if right[index] != base and left[index] == base and down[index] == base:
                delta = right[index] - base
                if 0 < abs(delta) <= 0x4000:
                    trajectory = tuple(sample[index] for sample in values)
                    x_axes.append((index, base, delta, trajectory, _axis_score(base, delta)))
            elif right[index] == base and left[index] == base and down[index] != base:
                delta = down[index] - base
                if 0 < abs(delta) <= 0x4000:
                    trajectory = tuple(sample[index] for sample in values)
                    y_axes.append((index, base, delta, trajectory, _axis_score(base, delta)))

        for x_index, _x_base, dx, x_values, x_score in x_axes:
            for y_index, _y_base, dy, y_values, y_score in y_axes:
                if x_index == y_index:
                    continue
                x_offset = ordered[0].start_offset + x_index * 2
                y_offset = ordered[0].start_offset + y_index * 2
                pair_bonus = 0.01 if abs(x_offset - y_offset) <= 0x1000 else 0.0
                score = min(0.99, (x_score + y_score) / 2 + pair_bonus)
                candidate = CoordinateCandidate(
                    x_offset=x_offset,
                    y_offset=y_offset,
                    data_type=word_type,
                    score=score,
                    idle_stability=1.0,
                    right_delta=dx,
                    left_delta=-dx,
                    down_delta=dy,
                    up_delta=-dy,
                    x_values=x_values,
                    y_values=y_values,
                )
                key = (x_offset, y_offset)
                existing = ranked.get(key)
                if existing is None or candidate.score > existing.score:
                    ranked[key] = candidate

    return tuple(
        sorted(ranked.values(), key=lambda candidate: candidate.score, reverse=True)[:limit]
    )
