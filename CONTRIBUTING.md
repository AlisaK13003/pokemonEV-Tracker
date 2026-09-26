# Contributing

## Setup and Checks

Use Python 3.12 or newer. From a clean checkout:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
pytest
ruff check .
```

Qt tests use the offscreen platform in CI. Keep tests independent of EmuHawk and redirect mutable files to pytest's `tmp_path`; tests must never write to the maintainer's real user profile.

## Directory Responsibilities

- `src/pokemon_ev_tracker/transport/`: emulator-facing local IPC.
- `src/pokemon_ev_tracker/data_sources/`: transport-to-game adapter.
- `src/pokemon_ev_tracker/games/platinum/`: Platinum RAM layout, item/species data, and decoder.
- `src/pokemon_ev_tracker/pokemon/gen4/`: reusable Generation IV record encryption and structure decoding.
- `src/pokemon_ev_tracker/core/`: game-independent EV target and change-tracking models.
- `src/pokemon_ev_tracker/ui/`: Qt tracker UI and sprite loaders.
- `src/pokemon_ev_tracker/assets/sprites/`: packaged Pokémon and held-item artwork.
- `bizhawk/ev_tracker.lua`: EmuHawk Lua reader, included in the source distribution.
- `tests/`: RAM, model, resource, and Qt tests.

## Style, Tests, and Fixtures

Keep changes scoped to the layer that owns the behavior. Run `pytest` and `ruff check .` before submitting. Add focused tests with sanitized, representative byte fixtures for memory decoding and `tmp_path` for mutable files. Never commit ROMs, save files, personal memory dumps, local logs, or generated runtime output.

Do not commit machine-specific absolute paths such as workspace or user-profile paths. Package resources must resolve from the installed package, not the process working directory.

## Adding Another Game

Add a package under `src/pokemon_ev_tracker/games/<game>/` with that game's memory layout and decoder. Keep emulator transport in `transport/`, shared tracker models in `core/`, and the UI independent of game-specific addresses. Add sanitized fixtures and tests for offsets, structure boundaries, checksums, and decoded values, then register the new game profile explicitly.
