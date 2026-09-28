from __future__ import annotations

from dataclasses import replace

import pytest

from pokemon_ev_tracker.core.nuzlocke.death_detection import (
    DeathCandidate,
    PartyHpObserver,
    PartyHpSample,
    match_death_candidate,
)
from pokemon_ev_tracker.core.nuzlocke.models import EncounterRecord, EncounterStatus
from pokemon_ev_tracker.core.nuzlocke.storage import NuzlockeStore
from pokemon_ev_tracker.games.platinum.nuzlocke import PLATINUM_NUZLOCKE_PROFILE


def _sample(stable_id: str, hp: int, *, species: str = "Gastly", nickname: str = "ghosty"):
    return PartyHpSample(
        stable_id=stable_id,
        species=species,
        nickname=nickname,
        level=14,
        current_hp=hp,
        met_location_id=0x46,
        met_location_name="Old Chateau",
        met_level=5,
        origin_game=12,
    )


def _observe(observer, members, frame, *, run_id="run-a", stream="lua-a", valid=True):
    return observer.observe(
        tuple(members),
        connected=True,
        valid_snapshot=valid,
        run_id=run_id,
        stream_identity=stream,
        frame=frame,
    )


def _caught_run(tmp_path, stable_id="pid:gastly"):
    store = NuzlockeStore(tmp_path / "runs.json")
    run = store.create_run("Platinum", PLATINUM_NUZLOCKE_PROFILE)
    row = next(item for item in PLATINUM_NUZLOCKE_PROFILE.locations if item.name == "Old Chateau")
    encounter = replace(
        run.encounters[row.location_id],
        status=EncounterStatus.CAUGHT.value,
        species="Gastly",
        nickname="ghosty",
        level=5,
        stable_id=stable_id,
        met_location_id=0x46,
        met_location_name="Old Chateau",
    )
    store.update_encounter(run.run_id, encounter)
    return store, run, encounter


@pytest.mark.parametrize("positive_hp", (10, 1))
def test_positive_to_zero_creates_one_candidate(tmp_path, positive_hp) -> None:
    observer = PartyHpObserver()
    assert not _observe(observer, (_sample("pid:a", positive_hp),), 100)

    candidates = _observe(observer, (_sample("pid:a", 0),), 101)
    assert len(candidates) == 1
    assert candidates[0].stable_id == "pid:a"
    assert candidates[0].species == "Gastly"
    assert candidates[0].nickname == "ghosty"
    assert not _observe(observer, (_sample("pid:a", 0),), 102)


def test_startup_at_zero_and_reconnect_at_zero_are_only_baselines() -> None:
    observer = PartyHpObserver()
    assert not _observe(observer, (_sample("pid:a", 0),), 100)
    assert not _observe(observer, (_sample("pid:a", 0),), 101)

    observer.observe(
        (), connected=False, valid_snapshot=False, run_id="run-a", frame=None
    )
    assert not _observe(observer, (_sample("pid:a", 0),), 102)


def test_invalid_snapshot_rebaselines_instead_of_comparing_across_gap() -> None:
    observer = PartyHpObserver()
    assert not _observe(observer, (_sample("pid:a", 12),), 10)
    assert not _observe(observer, (_sample("pid:a", 0),), 11, valid=False)
    assert not _observe(observer, (_sample("pid:a", 0),), 12)


def test_party_reorder_and_removal_do_not_create_deaths() -> None:
    observer = PartyHpObserver()
    a, b = _sample("pid:a", 12), _sample("pid:b", 8, species="Shinx", nickname="")
    assert not _observe(observer, (a, b), 10)
    assert not _observe(observer, (replace(b, current_hp=8), replace(a, current_hp=12)), 11)
    assert not _observe(observer, (a,), 12)
    assert not _observe(observer, (replace(b, current_hp=0), a), 13)


def test_two_simultaneous_faints_create_independent_candidates() -> None:
    observer = PartyHpObserver()
    first = _sample("pid:a", 12)
    second = _sample("pid:b", 8, species="Shinx", nickname="sparky")
    assert not _observe(observer, (first, second), 20)

    candidates = _observe(
        observer,
        (replace(first, current_hp=0), replace(second, current_hp=0)),
        21,
    )
    assert {candidate.stable_id for candidate in candidates} == {"pid:a", "pid:b"}


def test_run_stream_and_frame_rollback_each_rebaseline() -> None:
    observer = PartyHpObserver()
    assert not _observe(observer, (_sample("pid:a", 10),), 100)
    assert not _observe(observer, (_sample("pid:a", 0),), 5)
    assert not _observe(observer, (_sample("pid:a", 0),), 6)
    assert not _observe(observer, (_sample("pid:a", 10),), 7, run_id="run-b")
    assert len(_observe(observer, (_sample("pid:a", 0),), 8, run_id="run-b")) == 1
    assert not _observe(
        observer, (_sample("pid:a", 0),), 9, run_id="run-b", stream="lua-b"
    )
    assert not _observe(
        observer, (_sample("pid:a", 0),), 10, run_id="run-b", stream="lua-b"
    )


def test_pid_matching_disambiguates_duplicate_species_and_starter(tmp_path) -> None:
    store = NuzlockeStore(tmp_path / "runs.json")
    run = store.create_run("Platinum", PLATINUM_NUZLOCKE_PROFILE)
    locations = {item.name: item.location_id for item in PLATINUM_NUZLOCKE_PROFILE.locations}
    for row_id, stable_id, nickname in (
        (locations["Old Chateau"], "pid:a", "ghosty"),
        (locations["Route 202"], "pid:b", "ghosty"),
    ):
        store.update_encounter(
            run.run_id,
            EncounterRecord(
                row_id,
                run.encounters[row_id].location,
                "CAUGHT",
                "Gastly",
                nickname,
                5,
                stable_id=stable_id,
            ),
        )
    candidate = DeathCandidate("pid:b", "Gastly", "ghosty", 14, 0x46, "Old Chateau", 5, "now")
    assert match_death_candidate(candidate, run).location_id == locations["Route 202"]

    starter = run.encounters["platinum-starter"]
    starter_candidate = DeathCandidate("pid:starter", "Piplup", "", 5, 0x10, "Route 201", 5, "now")
    store.update_encounter(
        run.run_id,
        replace(
            starter,
            status="CAUGHT",
            species="Piplup",
            level=5,
            stable_id="pid:starter",
            met_location_id=0x10,
            met_location_name="Route 201",
        ),
    )
    assert match_death_candidate(starter_candidate, run).location_id == "platinum-starter"


def test_legacy_matching_requires_unique_species_nickname_and_met_location(tmp_path) -> None:
    store = NuzlockeStore(tmp_path / "runs.json")
    run = store.create_run("Platinum", PLATINUM_NUZLOCKE_PROFILE)
    old_chateau = next(item for item in run.encounters.values() if item.location == "Old Chateau")
    store.update_encounter(
        run.run_id,
        replace(old_chateau, status="CAUGHT", species="Gastly", nickname="ghosty", level=5),
    )
    candidate = DeathCandidate("pid:old", "Gastly", "ghosty", 14, 0x46, "Old Chateau", 5, "now")
    assert match_death_candidate(candidate, run).location_id == old_chateau.location_id

    run.encounters["legacy-extra"] = EncounterRecord(
        "legacy-extra", "Old Chateau", "CAUGHT", "Gastly", "ghosty", 5
    )
    store.save()
    assert match_death_candidate(candidate, run).ambiguous
    assert match_death_candidate(candidate, run).location_id is None


def test_record_death_preserves_encounter_and_persists_ram_provenance(tmp_path) -> None:
    store, run, encounter = _caught_run(tmp_path)
    candidate = DeathCandidate("pid:gastly", "Gastly", "ghosty", 14, 0x46, "Old Chateau", 5, "2026-09-27T12:00:00+00:00")

    assert store.record_ram_death(run.run_id, candidate, encounter.location_id)
    assert not store.record_ram_death(run.run_id, candidate, encounter.location_id)
    dead = run.encounters[encounter.location_id]
    assert dead.status == "DEAD"
    assert (dead.species, dead.nickname, dead.level, dead.stable_id) == (
        "Gastly", "ghosty", 5, "pid:gastly"
    )
    assert len(run.deaths) == 1
    death = run.deaths[0]
    assert (death.level_at_death, death.location_or_fight, death.encounter_location_id) == (
        14, "Unknown", encounter.location_id
    )
    assert (death.stable_id, death.detection_source) == ("pid:gastly", "RAM_AUTO")
    reloaded = NuzlockeStore(store.path).active_run
    assert reloaded is not None
    assert reloaded.deaths[0].detection_source == "RAM_AUTO"
    assert reloaded.encounters[encounter.location_id].stable_id == "pid:gastly"


def test_dead_status_is_not_reversed_by_positive_hp_and_requires_a_new_edge(tmp_path) -> None:
    store, run, encounter = _caught_run(tmp_path)
    observer = PartyHpObserver()
    assert not _observe(observer, (_sample("pid:gastly", 10),), 100)
    candidate = _observe(observer, (_sample("pid:gastly", 0),), 101)[0]
    assert store.record_ram_death(run.run_id, candidate, encounter.location_id)

    assert not _observe(observer, (_sample("pid:gastly", 20),), 102)
    assert run.encounters[encounter.location_id].status == "DEAD"
    store.update_encounter(
        run.run_id,
        replace(run.encounters[encounter.location_id], status="CAUGHT"),
    )
    assert not _observe(observer, (_sample("pid:gastly", 20),), 103)
    next_candidate = _observe(observer, (_sample("pid:gastly", 0),), 104)
    assert len(next_candidate) == 1
    assert store.record_ram_death(run.run_id, next_candidate[0], encounter.location_id)
    assert len(run.deaths) == 1


def test_ignored_or_unlinked_candidate_does_not_consume_an_encounter(tmp_path) -> None:
    store, run, encounter = _caught_run(tmp_path)
    candidate = DeathCandidate("pid:unknown", "Pikachu", "sparky", 8, 0x46, "Old Chateau", 5, "now")
    assert match_death_candidate(candidate, run).location_id is None
    assert run.encounters[encounter.location_id].status == "CAUGHT"
    assert run.deaths == []

    assert store.record_ram_death(run.run_id, candidate, None)
    assert run.deaths[0].encounter_location_id is None
    assert run.encounters[encounter.location_id].status == "CAUGHT"


def test_unlinked_candidate_can_be_explicitly_linked_to_starter(tmp_path) -> None:
    store = NuzlockeStore(tmp_path / "runs.json")
    run = store.create_run("Platinum", PLATINUM_NUZLOCKE_PROFILE)
    candidate = DeathCandidate("pid:starter", "Piplup", "", 5, 0x10, "Route 201", 5, "now")

    assert store.record_ram_death(run.run_id, candidate, "platinum-starter")
    starter = run.encounters["platinum-starter"]
    assert (starter.status, starter.species, starter.stable_id) == (
        "DEAD", "Piplup", "pid:starter"
    )
    assert run.deaths[0].encounter_location_id == "platinum-starter"


def test_auto_confirm_setting_persists_and_defaults_off(tmp_path) -> None:
    path = tmp_path / "runs.json"
    store = NuzlockeStore(path)
    run = store.create_run("Platinum", PLATINUM_NUZLOCKE_PROFILE)
    assert not run.automatically_confirm_deaths
    store.set_automatically_confirm_deaths(run.run_id, True)

    loaded = NuzlockeStore(path).active_run
    assert loaded is not None and loaded.automatically_confirm_deaths
