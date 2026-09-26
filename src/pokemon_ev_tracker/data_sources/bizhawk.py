"""BizHawk RAM data source diagnostics."""

from __future__ import annotations

from pokemon_ev_tracker.data_sources.base import DataSourceSnapshot, GameDataSource
from pokemon_ev_tracker.games.platinum.decoder import PartyState, valid_checksum_count
from pokemon_ev_tracker.games.platinum.profile import PLATINUM_PROFILE
from pokemon_ev_tracker.transport.bizhawk_server import BizHawkDebugServer


class BizHawkRamDataSource(GameDataSource):
    """Receives RAM-1 heartbeat messages from the EmuHawk Lua script."""

    def __init__(self, server: BizHawkDebugServer | None = None, profile=PLATINUM_PROFILE) -> None:
        self.server = server or BizHawkDebugServer()
        self.profile = profile

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
            },
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
