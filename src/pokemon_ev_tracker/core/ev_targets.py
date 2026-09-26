"""Validated EV spreads and local PID-keyed target persistence."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path

from pokemon_ev_tracker.config.paths import app_data_directory

EV_STAT_KEYS = (
    "hp",
    "attack",
    "defense",
    "special_attack",
    "special_defense",
    "speed",
)
DEFAULT_EV_TARGETS_PATH = app_data_directory() / "ev_targets.json"
LEGACY_EV_TARGETS_PATH = Path(__file__).resolve().parents[3] / "data" / "ev_targets.json"


@dataclass(frozen=True)
class EVTargetProgress:
    target_total: int
    achieved: int
    remaining: int
    complete: bool
    overshoots: Mapping[str, int]


@dataclass(frozen=True)
class EVTarget:
    hp_target: int = 0
    attack_target: int = 0
    defense_target: int = 0
    special_attack_target: int = 0
    special_defense_target: int = 0
    speed_target: int = 0

    def __post_init__(self) -> None:
        values = self.as_mapping()
        for stat, value in values.items():
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"{stat} target must be an integer.")  # noqa: TRY004
            if not 0 <= value <= 252:
                raise ValueError(f"{stat} target must be between 0 and 252.")
        if self.total > 510:
            raise ValueError("Total EV target cannot exceed 510.")

    @property
    def total(self) -> int:
        return sum(self.as_mapping().values())

    def as_mapping(self) -> dict[str, int]:
        return {stat: getattr(self, f"{stat}_target") for stat in EV_STAT_KEYS}

    def progress(self, current_evs: Mapping[str, int]) -> EVTargetProgress:
        targets = self.as_mapping()
        current = {stat: int(current_evs.get(stat, 0)) for stat in EV_STAT_KEYS}
        overshoots = {
            stat: current[stat] - targets[stat]
            for stat in EV_STAT_KEYS
            if current[stat] > targets[stat]
        }
        return EVTargetProgress(
            target_total=self.total,
            achieved=sum(min(max(current[stat], 0), targets[stat]) for stat in EV_STAT_KEYS),
            remaining=sum(max(targets[stat] - current[stat], 0) for stat in EV_STAT_KEYS),
            complete=all(current[stat] >= targets[stat] for stat in EV_STAT_KEYS),
            overshoots=overshoots,
        )


class EVTargetStore:
    """Persist EV targets by 32-bit Pokémon personality value, never by slot."""

    def __init__(self, path: Path | None = None) -> None:
        use_default = path is None
        self.path = Path(path) if path is not None else DEFAULT_EV_TARGETS_PATH
        self._targets: dict[int, EVTarget] = {}
        if self.path.is_file():
            self._load(self.path)
        elif (
            use_default and LEGACY_EV_TARGETS_PATH.is_file() and self._load(LEGACY_EV_TARGETS_PATH)
        ):
            try:
                self._save()
                LEGACY_EV_TARGETS_PATH.unlink(missing_ok=True)
            except OSError:
                pass

    def get(self, pid: int) -> EVTarget | None:
        return self._targets.get(_normalize_pid(pid))

    def set(self, pid: int, target: EVTarget) -> None:
        if not isinstance(target, EVTarget):
            raise TypeError("target must be an EVTarget instance.")
        normalized_pid = _normalize_pid(pid)
        previous = self._targets.get(normalized_pid)
        self._targets[normalized_pid] = target
        try:
            self._save()
        except OSError:
            if previous is None:
                del self._targets[normalized_pid]
            else:
                self._targets[normalized_pid] = previous
            raise

    def clear(self, pid: int) -> bool:
        normalized_pid = _normalize_pid(pid)
        if normalized_pid not in self._targets:
            return False
        previous = self._targets.pop(normalized_pid)
        try:
            self._save()
        except OSError:
            self._targets[normalized_pid] = previous
            raise
        return True

    def _load(self, source: Path) -> bool:
        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        if not isinstance(payload, dict):
            return False

        for pid_key, values in payload.items():
            try:
                pid = int(str(pid_key), 16)
                if not isinstance(values, dict):
                    continue
                target = EVTarget(
                    **{f"{stat}_target": values[f"{stat}_target"] for stat in EV_STAT_KEYS}
                )
            except (KeyError, TypeError, ValueError):
                continue
            if 0 <= pid <= 0xFFFFFFFF:
                self._targets[pid] = target
        return True

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {f"{pid:08X}": asdict(target) for pid, target in sorted(self._targets.items())}
        temporary_path = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        temporary_path.replace(self.path)


def _normalize_pid(pid: int) -> int:
    if isinstance(pid, bool) or not isinstance(pid, int) or not 0 <= pid <= 0xFFFFFFFF:
        raise ValueError("PID must be an unsigned 32-bit integer.")
    return pid
