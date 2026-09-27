"""BizHawk RAM data source diagnostics."""

from __future__ import annotations

import logging
import time
from dataclasses import replace

from pokemon_ev_tracker.data_sources.base import DataSourceSnapshot, GameDataSource
from pokemon_ev_tracker.games.platinum.battle import (
    BattleBattler,
    active_enemy_battlers,
    decode_battle_battlers,
)
from pokemon_ev_tracker.games.platinum.decoder import PartyState, valid_checksum_count
from pokemon_ev_tracker.games.platinum.profile import PLATINUM_PROFILE
from pokemon_ev_tracker.transport.bizhawk_server import BizHawkDebugServer

LOGGER = logging.getLogger(__name__)


class BizHawkRamDataSource(GameDataSource):
    """Receives RAM-1 heartbeat messages from the EmuHawk Lua script."""

    def __init__(self, server: BizHawkDebugServer | None = None, profile=PLATINUM_PROFILE) -> None:
        self.server = server or BizHawkDebugServer()
        self.profile = profile
        self._display_stream_identity = None
        self._last_good_party_by_pid = {}
        self._battle_payload_cache = object()
        self._battle_battlers_cache: tuple[BattleBattler, ...] = ()

    @property
    def backend_name(self) -> str:
        return "BizHawk RAM"

    def start(self) -> None:
        self.server.start()

    def stop(self) -> None:
        self.server.stop()

    def snapshot(self) -> DataSourceSnapshot:
        heartbeat = self.server.latest_heartbeat()
        party_payload = self.server.latest_party_payload()
        party_state = self._decode_party_payload(party_payload)
        display_party_state = self._stabilize_display_party(party_state, party_payload)
        battle_battlers = self._decode_battle_battlers(party_payload)
        party_payload_fresh = self._party_payload_is_fresh(party_payload)
        active_enemies = (
            active_enemy_battlers(battle_battlers)
            if party_payload_fresh
            else ()
        )
        enemy_summary = ", ".join(
            f"{battler.species} Lv{battler.level}" for battler in active_enemies
        ) or "(none)"
        active_record_indices = [
            battler.battler_index for battler in battle_battlers if battler.active
        ]
        LOGGER.debug(
            "active_enemy_battlers produced: %d - %s; party payload fresh: %s; "
            "individually active battler indices: %s",
            len(active_enemies),
            enemy_summary,
            party_payload_fresh,
            active_record_indices,
        )
        return DataSourceSnapshot(
            backend_name=self.backend_name,
            connected=self.server.is_connected(),
            details={
                "host": self.server.host,
                "port": self.server.port,
                "fallback_file": str(self.server.fallback_file),
                "heartbeat": heartbeat,
                "party_payload": party_payload,
                "party_state": party_state,
                "display_party_state": display_party_state,
                "battle_battlers": battle_battlers,
                "active_enemy_battlers": active_enemies,
            },
        )

    def _party_payload_is_fresh(self, party_payload) -> bool:
        if party_payload is None:
            return False
        received_at = getattr(party_payload, "received_at", None)
        if not isinstance(received_at, (int, float)):
            return False
        stale_after = getattr(self.server, "stale_after_seconds", 5.0)
        return max(0.0, time.monotonic() - received_at) <= stale_after

    def _decode_battle_battlers(self, party_payload) -> tuple[BattleBattler, ...]:
        if party_payload is self._battle_payload_cache:
            return self._battle_battlers_cache
        self._battle_payload_cache = party_payload
        payload = party_payload.payload if party_payload is not None else {}
        raw_records = {
            index: payload.get(f"battle_battler_{index}_raw_hex")
            for index in range(4)
        }
        self._battle_battlers_cache = decode_battle_battlers(
            raw_records,
            payload.get("pointer_value"),
            self.profile.memory_profile,
        )
        return self._battle_battlers_cache

    def _stabilize_display_party(self, party_state: PartyState | None, party_payload) -> PartyState | None:
        if party_state is None:
            return None

        payload = party_payload.payload if party_payload is not None else {}
        stream_identity = tuple(
            payload.get(key) for key in ("run_id", "core", "domain", "pointer_value")
        )
        if stream_identity != self._display_stream_identity:
            self._display_stream_identity = stream_identity
            self._last_good_party_by_pid.clear()

        if not party_state.party_count_valid or party_state.party_count is None:
            return party_state

        checksummed_pids = {
            pokemon.decoded.diagnostics.pid
            for pokemon in party_state.pokemon
            if pokemon.checksum_valid
        }
        if all(pokemon.checksum_valid for pokemon in party_state.pokemon):
            self._last_good_party_by_pid = {
                pid: pokemon
                for pid, pokemon in self._last_good_party_by_pid.items()
                if pid in checksummed_pids
            }

        display_members = []
        invalid_slots = []
        stale_slots = []
        invalid_battle_slots = []
        stale_battle_slots = []
        for pokemon in party_state.pokemon:
            pid = pokemon.decoded.diagnostics.pid
            previous = self._last_good_party_by_pid.get(pid)
            if not pokemon.checksum_valid:
                invalid_slots.append(pokemon.slot)
                if previous is not None:
                    display_members.append(
                        replace(previous, slot=pokemon.slot, sample_stale=True)
                    )
                    stale_slots.append(pokemon.slot)
                continue

            current = replace(pokemon, sample_stale=False, battle_stats_stale=False)
            if not pokemon.decoded.diagnostics.battle_stats_valid:
                invalid_battle_slots.append(pokemon.slot)
                has_sane_previous = (
                    previous is not None
                    and previous.level is not None
                    and previous.current_hp is not None
                    and previous.max_hp is not None
                    and previous.current_stats is not None
                )
                if has_sane_previous:
                    current = replace(
                        current,
                        level=previous.level,
                        current_hp=previous.current_hp,
                        max_hp=previous.max_hp,
                        current_stats=previous.current_stats,
                        battle_stats_stale=True,
                    )
                    stale_battle_slots.append(pokemon.slot)
                else:
                    current = replace(
                        current,
                        level=None,
                        current_hp=None,
                        max_hp=None,
                        current_stats=None,
                        battle_stats_stale=True,
                    )
                self._last_good_party_by_pid[pid] = current
            else:
                self._last_good_party_by_pid[pid] = current
            display_members.append(current)

        warnings = []
        if invalid_slots:
            slots = ", ".join(str(slot) for slot in invalid_slots)
            if stale_slots:
                warnings.append(
                    f"RAM checksum failed for slot(s) {slots}; showing the last valid matching-PID sample."
                )
            else:
                warnings.append(f"Waiting for checksum-valid RAM data in slot(s) {slots}.")
        if invalid_battle_slots:
            slots = ", ".join(str(slot) for slot in invalid_battle_slots)
            if stale_battle_slots:
                warnings.append(
                    f"Battle stats failed validation in slot(s) {slots}; keeping last sane level/HP and stats."
                )
            else:
                warnings.append(
                    f"Battle stats failed validation in slot(s) {slots}; level/HP withheld."
                )

        return replace(
            party_state,
            pokemon=tuple(display_members),
            live_read_warning=" ".join(warnings) or None,
        )

    def _decode_party_payload(self, party_payload) -> PartyState | None:
        if party_payload is None:
            return None
        payload = party_payload.payload
        raw_hex = payload.get("raw_party_hex")
        decoded_primary = None
        if isinstance(raw_hex, str) and raw_hex:
            decoded_primary = self._decode_raw_party(
                raw_hex,
                _parse_hex_int(payload.get("party_address")),
                payload.get("party_count"),
            )

        decoded_candidates = []
        for candidate in payload.get("party_candidates", []):
            if not isinstance(candidate, dict):
                continue
            candidate_raw = candidate.get("raw_party_hex")
            if not isinstance(candidate_raw, str) or not candidate_raw:
                continue
            decoded = self._decode_raw_party(
                candidate_raw,
                _parse_hex_int(candidate.get("address")),
                candidate.get("party_count"),
            )
            if decoded is not None:
                decoded_candidates.append((candidate, decoded))

        best = self._best_candidate(decoded_candidates)
        if best is not None:
            candidate, party = best
            verified = PartyState(
                party.party_count,
                party.party_count_valid,
                party.pokemon,
                error=(
                    f"Selected scanned candidate at relative offset "
                    f"{candidate.get('relative_offset')} with "
                    f"{valid_checksum_count(party)} valid checksum slot(s)."
                ),
                candidate_count=len(decoded_candidates),
            )
            return verified
        if decoded_primary is not None:
            return PartyState(
                decoded_primary.party_count,
                decoded_primary.party_count_valid,
                decoded_primary.pokemon,
                decoded_primary.error,
                candidate_count=len(decoded_candidates),
            )
        if decoded_candidates:
            candidate, party = decoded_candidates[0]
            return PartyState(
                party.party_count,
                False,
                (),
                error=(
                    f"Scanned {len(decoded_candidates)} non-empty candidate(s), "
                    "but none had valid Pokemon checksums."
                ),
                candidate_count=len(decoded_candidates),
            )
        return decoded_primary

    def _decode_raw_party(
        self,
        raw_hex: str,
        base_address: int | None,
        fallback_count,
    ) -> PartyState | None:
        try:
            raw_party = bytes.fromhex(raw_hex)
        except ValueError as exc:
            return PartyState(None, False, (), f"Invalid raw party hex: {exc}")
        try:
            return self.profile.party_decoder(raw_party, base_address=base_address)
        except ValueError as exc:
            return PartyState(fallback_count, False, (), str(exc))

    def _best_candidate(
        self, candidates: list[tuple[dict, PartyState]]
    ) -> tuple[dict, PartyState] | None:
        viable = [
            (candidate, party)
            for candidate, party in candidates
            if party.party_count_valid
            and party.party_count
            and valid_checksum_count(party) == party.party_count
        ]
        if not viable:
            return None
        return max(
            viable,
            key=lambda item: (
                valid_checksum_count(item[1]),
                item[1].party_count or 0,
            ),
        )


def _parse_hex_int(value) -> int | None:
    if not isinstance(value, str):
        return None
    try:
        return int(value, 16)
    except ValueError:
        return None
