"""Party-only acquisition observation with run-scoped persisted baselines."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from pokemon_ev_tracker.core.nuzlocke.models import NuzlockeRun, PokemonAcquisitionEvent
from pokemon_ev_tracker.core.nuzlocke.storage import NuzlockeStore


@dataclass(frozen=True)
class AcquisitionCandidate:
    stable_id: str
    species_id: int
    species_name: str
    nickname: str
    level: int | None
    met_level: int | None
    met_location_id: int
    met_location_name: str | None
    egg_location_id: int
    origin_game: int
    is_egg: bool


Classifier = Callable[[AcquisitionCandidate, NuzlockeRun | None], tuple[str, str, str | None]]


class PartyAcquisitionObserver:
    def __init__(self) -> None:
        self._connected = False
        self._run_id: str | None = None
        self._baseline_ids: set[str] = set()
        self._empty_party_baseline = False

    def observe(
        self,
        candidates: tuple[AcquisitionCandidate, ...],
        *,
        connected: bool,
        valid_snapshot: bool,
        run: NuzlockeRun | None,
        store: NuzlockeStore,
        classify: Classifier,
        classify_first_party: Classifier | None = None,
    ) -> tuple[PokemonAcquisitionEvent, ...]:
        if not connected:
            self._connected = False
            self._baseline_ids.clear()
            self._run_id = run.run_id if run else None
            self._empty_party_baseline = False
            return ()
        if not valid_snapshot:
            return ()

        current = {candidate.stable_id for candidate in candidates}
        if not self._connected or (run.run_id if run else None) != self._run_id:
            if run:
                store.mark_pokemon_observed(run.run_id, sorted(current))
            self._baseline_ids = current
            self._empty_party_baseline = not current
            self._run_id = run.run_id if run else None
            self._connected = True
            return ()

        newly_seen = current - self._baseline_ids
        first_party_candidate_id = (
            next(
                (candidate.stable_id for candidate in candidates if candidate.stable_id in newly_seen),
                None,
            )
            if self._empty_party_baseline
            else None
        )
        if newly_seen:
            self._empty_party_baseline = False
        self._baseline_ids = current
        if run is None:
            return ()

        events = []
        for candidate in candidates:
            if candidate.stable_id not in newly_seen:
                continue
            if store.has_observed_pokemon(run.run_id, candidate.stable_id):
                continue
            classifier = (
                classify_first_party
                if candidate.stable_id == first_party_candidate_id and classify_first_party
                else classify
            )
            source, confidence, suggested_location_id = classifier(candidate, run)
            event = PokemonAcquisitionEvent(
                stable_id=candidate.stable_id,
                species_id=candidate.species_id,
                species_name=candidate.species_name,
                nickname=candidate.nickname,
                level=candidate.level,
                met_level=candidate.met_level,
                met_location_id=candidate.met_location_id,
                met_location_name=candidate.met_location_name,
                egg_location_id=candidate.egg_location_id,
                origin_game=candidate.origin_game,
                is_egg=candidate.is_egg,
                detected_at=datetime.now(UTC).isoformat(timespec="seconds"),
                source=source,
                confidence=confidence,
                suggested_location_id=suggested_location_id,
                suggested_location_name=(
                    run.encounters[suggested_location_id].location
                    if suggested_location_id in run.encounters
                    else None
                ),
            )
            if store.record_acquisition_event(run.run_id, event):
                events.append(event)
        return tuple(events)


def pending_acquisition_events(run: NuzlockeRun | None) -> tuple[PokemonAcquisitionEvent, ...]:
    if run is None:
        return ()
    resolved = set(run.resolved_acquisition_ids)
    return tuple(event for event in run.acquisition_events if event.stable_id not in resolved)
