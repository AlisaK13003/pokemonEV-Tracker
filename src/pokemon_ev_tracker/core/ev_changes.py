"""PID-keyed EV delta detection independent of emulator and game UI."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EVChange:
    pid: int
    slot: int
    species: str
    nickname: str
    stat: str
    before: int
    after: int

    @property
    def delta(self) -> int:
        return self.after - self.before


class EVChangeTracker:
    """Emit actual decoded EV changes while keeping identity attached to PID."""

    def __init__(self) -> None:
        self._previous: dict[int, dict[str, int]] = {}

    def observe(self, party_state) -> tuple[EVChange, ...]:
        if party_state is None or not party_state.party_count_valid:
            return ()
        changes = []
        for pokemon in party_state.pokemon:
            if not pokemon.checksum_valid or getattr(pokemon, "sample_stale", False):
                continue
            pid = pokemon.decoded.diagnostics.pid
            current = dict(pokemon.evs)
            previous = self._previous.get(pid)
            if previous is not None:
                for stat, after in current.items():
                    before = previous.get(stat, after)
                    if before != after:
                        changes.append(
                            EVChange(
                                pid,
                                pokemon.slot,
                                pokemon.species,
                                pokemon.nickname,
                                stat,
                                before,
                                after,
                            )
                        )
            self._previous[pid] = current
        return tuple(changes)
