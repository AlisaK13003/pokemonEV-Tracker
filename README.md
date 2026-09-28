# Pokémon Platinum EV Tracker

A real-time Pokémon Platinum EV tracker that reads party data directly from BizHawk/EmuHawk Nintendo DS memory. It displays decoded party records and actual EV values; it does not infer EVs from battles or screenshots.

## Features

- Live party species, nicknames, levels, HP, held items, and EV values
- Per-Pokémon EV change history and configurable PID-keyed EV targets
- Animated sprites with static Platinum sprites as fallback, plus held-item icons
- Compact always-on-top mode for use beside EmuHawk
- RAM diagnostics for the BizHawk connection and decoded party records
- Nuzlocke run tracking with advisory party-acquisition suggestions; automatic detection requires the Pokémon to appear in the party, so captures sent directly to PC boxes are not detected

## Screenshots

Screenshots are not included yet.

## Supported Games

| Game | Emulator | Status |
| --- | --- | --- |
| Pokémon Platinum | BizHawk / EmuHawk | Supported |

## Architecture

EmuHawk/BizHawk -> Lua RAM reader -> localhost TCP or temporary-file transport -> Python Platinum decoder -> common tracker models -> PySide6 UI.

The Lua reader enumerates memory domains at runtime and does not assume an NDS RAM domain name. The app has no cloud service or runtime API dependency.

## Requirements

- Windows 10 or later
- Python 3.12+
- BizHawk/EmuHawk with a Nintendo DS core
- Your own legally obtained Pokémon Platinum game copy

ROMs, save files, and emulator binaries are not included. You must supply your own game copy and emulator.

## License and Third-Party Assets

Original project source code is licensed under the MIT License in [LICENSE](LICENSE). Bundled sprites and item artwork are third-party assets with separate ownership and terms; they are not licensed under this project's MIT License. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for source attribution and rights details. This unofficial project is not affiliated with Pokémon; Nintendo, The Pokémon Company, Game Freak, and other rights holders retain their respective trademarks and artwork.

## Installation

```powershell
git clone https://github.com/AlisaK13003/pokemonEV-Tracker.git
cd pokemonEV-Tracker
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
```

Contributors can install the test, lint, and build tools with:

```powershell
python -m pip install -e ".[dev]"
```

## Running

1. Launch EmuHawk and load your Pokémon Platinum game with the Nintendo DS core.
2. Open **Tools → Lua Console**.
3. Load `bizhawk/ev_tracker.lua` from the repository checkout and start the script.
4. Launch the tracker with `pokemon-ev-tracker` or `python -m pokemon_ev_tracker`.
5. Wait for **BizHawk RAM • CONNECTED** and the decoded party to appear.

The app stores settings and EV targets in `%LOCALAPPDATA%\PokemonEVTracker` on Windows. The Lua fallback transport file is written to the system temporary directory, outside the checkout. Both TCP and file communication remain local to the machine.

## Development

```powershell
python -m pip install -e ".[dev]"
pytest
ruff check .
python -m build
```

See [CONTRIBUTING.md](CONTRIBUTING.md) and [docs/architecture.md](docs/architecture.md).

## Adding Another Game

Future game integrations belong under `src/pokemon_ev_tracker/games/<game>/`, for example `games/emerald/` or `games/firered/`. Keep each game's RAM layout and decoder separate from the reusable tracker core and UI; these game integrations are not currently implemented.

## Credits

- Bundled Pokémon and item sprite assets are attributed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). The upstream rights statement and its limitations are documented there.
- Generation IV structure and Platinum memory research: [pret/pokeplatinum](https://github.com/pret/pokeplatinum).
