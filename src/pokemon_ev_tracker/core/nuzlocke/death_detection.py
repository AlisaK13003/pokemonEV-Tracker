"""Game-neutral party HP transition detection for Nuzlocke runs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from pokemon_ev_tracker.core.nuzlocke.models import EncounterRecord, NuzlockeRun


@dataclass(frozen=True)
class PartyHpSample:
    stable_id: str
    species: str
    nickname: str
    level: int | None
    current_hp: int
    met_location_id: int
    met_location_name: str | None
    met_level: int | None = None
    origin_game: int = 0


@dataclass(frozen=True)
class DeathCandidate:
    stable_id: str
    species: str
    nickname: str
    level: int | None
    met_location_id: int
    met_location_name: str | None
    met_level: int | None
    detected_at: str


@dataclass(frozen=True)
class EncounterMatch:
    location_id: str | None
    ambiguous: bool = False


class PartyHpObserver:
    """Detects positive-to-zero HP transitions without relying on party slots."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._baseline: dict[str, PartyHpSample] = {}
        self._baseline_ready = False
        self._run_id: str | None = None
        self._stream_identity = None
        self._last_frame: int | None = None

    def observe(
        self,
        members: tuple[PartyHpSample, ...],
        *,
        connected: bool,
        valid_snapshot: bool,
        run_id: str | None,
        stream_identity=None,
        frame: int | None = None,
    ) -> tuple[DeathCandidate, ...]:
        if not connected:
            self.reset()
            return ()

        stream_changed = (
            run_id != self._run_id or stream_identity != self._stream_identity
        )
        frame_rolled_back = (
            frame is not None
            and self._last_frame is not None
            and frame < self._last_frame
        )
        if stream_changed or frame_rolled_back:
            self._baseline = {}
            self._baseline_ready = False
            self._run_id = run_id
            self._stream_identity = stream_identity

        if not valid_snapshot:
            self._baseline = {}
            self._baseline_ready = False
            self._last_frame = frame
            self._run_id = run_id
            self._stream_identity = stream_identity
            return ()

        current = {
            member.stable_id: member
            for member in members
            if member.stable_id and _valid_hp(member.current_hp)
        }
        self._last_frame = frame
        self._run_id = run_id
        self._stream_identity = stream_identity
        if not self._baseline_ready:
            self._baseline = current
            self._baseline_ready = True
            return ()

        now = datetime.now(UTC).isoformat(timespec="seconds")
        candidates = tuple(
            DeathCandidate(
                stable_id=member.stable_id,
                species=member.species,
                nickname=member.nickname,
                level=member.level,
                met_location_id=member.met_location_id,
                met_location_name=member.met_location_name,
                met_level=member.met_level,
                detected_at=now,
            )
            for stable_id, member in current.items()
            if (previous := self._baseline.get(stable_id)) is not None
            and previous.current_hp > 0
            and member.current_hp == 0
        )
        # Replacing the whole baseline also forgets boxed/deposited members.
        self._baseline = current
        return candidates


def match_death_candidate(candidate: DeathCandidate, run: NuzlockeRun) -> EncounterMatch:
    """Match by persisted identity, then by conservative legacy fields."""
    exact = [
        encounter
        for encounter in run.encounters.values()
        if encounter.stable_id == candidate.stable_id
    ]
    if len(exact) == 1:
        return EncounterMatch(exact[0].location_id)
    if len(exact) > 1:
        return EncounterMatch(None, ambiguous=True)

    event = next(
        (item for item in run.acquisition_events if item.stable_id == candidate.stable_id),
        None,
    )
    if event and event.suggested_location_id:
        suggested = run.encounters.get(event.suggested_location_id)
        if (
            suggested
            and suggested.species.casefold() == event.species_name.casefold()
            and (suggested.nickname or suggested.species).strip().casefold()
            == (event.nickname or event.species_name).strip().casefold()
        ):
            return EncounterMatch(suggested.location_id)

    matches = [
        encounter
        for encounter in run.encounters.values()
        if _same_pokemon(candidate, encounter) and _same_met_location(candidate, encounter)
    ]
    if len(matches) == 1:
        return EncounterMatch(matches[0].location_id)
    return EncounterMatch(None, ambiguous=len(matches) > 1)


def _valid_hp(value: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _same_pokemon(candidate: DeathCandidate, encounter: EncounterRecord) -> bool:
    if not encounter.species or encounter.species.casefold() != candidate.species.casefold():
        return False
    encounter_nickname = (encounter.nickname or encounter.species).strip().casefold()
    candidate_nickname = (candidate.nickname or candidate.species).strip().casefold()
    return encounter_nickname == candidate_nickname


def _same_met_location(candidate: DeathCandidate, encounter: EncounterRecord) -> bool:
    if encounter.met_location_id is not None:
        return encounter.met_location_id == candidate.met_location_id
    if encounter.met_location_name:
        return _normalize(encounter.met_location_name) == _normalize(
            candidate.met_location_name or ""
        )
    return bool(candidate.met_location_name) and _normalize(encounter.location) == _normalize(
        candidate.met_location_name
    )


def _normalize(value: str) -> str:
    return " ".join(value.casefold().split())
