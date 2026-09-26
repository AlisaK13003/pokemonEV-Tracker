"""Platform-appropriate writable application data paths."""

from __future__ import annotations

import os
from pathlib import Path


def app_data_directory() -> Path:
    if os.name == "nt":
        root = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    else:
        root = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return root / "PokemonEVTracker"
