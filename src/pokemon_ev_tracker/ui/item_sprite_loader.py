"""Resolve and cache held-item icons for Tracker party cards."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap

ITEM_SPRITE_DIRECTORY = Path(__file__).resolve().parents[1] / "assets" / "sprites" / "items"
_ITEM_SLUG_OVERRIDES = {
    "brightpowder": "bright-powder",
    "deepseascale": "deep-sea-scale",
    "deepseatooth": "deep-sea-tooth",
    "exp. share": "exp-share",
    "king's rock": "kings-rock",
    "nevermelt ice": "never-melt-ice",
    "parlyz heal": "paralyze-heal",
    "s.s. ticket": "ss-ticket",
    "thunderstone": "thunder-stone",
    "up-grade": "up-grade",
    "upgrade": "up-grade",
    "x special": "x-sp-atk",
}
# Platinum TM icons in the local PokeAPI set are grouped by move type rather
# than by machine number. This order is TM01 through TM92 in Generation IV.
_GEN4_TM_TYPES = [
    "fighting",
    "dragon",
    "water",
    "psychic",
    "normal",
    "poison",
    "ice",
    "fighting",
    "grass",
    "normal",
    "fire",
    "dark",
    "ice",
    "ice",
    "normal",
    "psychic",
    "normal",
    "water",
    "grass",
    "normal",
    "normal",
    "grass",
    "steel",
    "electric",
    "electric",
    "ground",
    "normal",
    "ground",
    "psychic",
    "ghost",
    "fighting",
    "normal",
    "psychic",
    "electric",
    "fire",
    "poison",
    "rock",
    "fire",
    "rock",
    "flying",
    "dark",
    "normal",
    "normal",
    "psychic",
    "normal",
    "dark",
    "steel",
    "psychic",
    "dark",
    "fire",
    "flying",
    "fighting",
    "grass",
    "normal",
    "water",
    "dark",
    "electric",
    "normal",
    "dragon",
    "fighting",
    "fire",
    "bug",
    "dark",
    "normal",
    "ghost",
    "dark",
    "normal",
    "normal",
    "rock",
    "normal",
    "rock",
    "ice",
    "electric",
    "steel",
    "normal",
    "rock",
    "normal",
    "normal",
    "dark",
    "rock",
    "bug",
    "normal",
    "normal",
    "poison",
    "psychic",
    "grass",
    "normal",
    "flying",
    "bug",
    "normal",
    "steel",
    "psychic",
]
_HM_ICON_SLUGS = {
    1: "hm01",
    2: "hm02",
    3: "hm03",
    4: "hm04",
    5: "hm05",
    6: "hm06",
    7: "hm07",
    # The source set has no hm08.png; use the available Normal-type HM icon.
    8: "hm-normal",
}
_ITEM_SPRITE_CACHE: dict[tuple[str | None, int], QPixmap] = {}
_ITEM_SPRITE_EXISTS_CACHE: dict[str | None, bool] = {}


def _machine_sprite_slug(normalized: str) -> str | None:
    match = re.fullmatch(r"(tm|hm)\s*0*(\d{1,2})", normalized)
    if match is None:
        return None
    machine, number_text = match.groups()
    number = int(number_text)
    if machine == "tm" and 1 <= number <= len(_GEN4_TM_TYPES):
        return f"tm-{_GEN4_TM_TYPES[number - 1]}"
    if machine == "hm":
        return _HM_ICON_SLUGS.get(number)
    return None


def item_sprite_slug(item_name: str | None) -> str | None:
    if not item_name:
        return None
    normalized = unicodedata.normalize("NFKD", item_name)
    normalized = normalized.encode("ascii", "ignore").decode("ascii").casefold().strip()
    if not normalized:
        return None
    if normalized in _ITEM_SLUG_OVERRIDES:
        return _ITEM_SLUG_OVERRIDES[normalized]
    machine_slug = _machine_sprite_slug(normalized)
    if machine_slug is not None:
        return machine_slug
    return re.sub(r"[^a-z0-9]+", "-", normalized).strip("-") or None


def item_sprite_path(item_name: str | None) -> Path | None:
    slug = item_sprite_slug(item_name)
    return ITEM_SPRITE_DIRECTORY / f"{slug}.png" if slug else None


def item_sprite_exists(item_name: str | None) -> bool:
    slug = item_sprite_slug(item_name)
    if slug not in _ITEM_SPRITE_EXISTS_CACHE:
        path = ITEM_SPRITE_DIRECTORY / f"{slug}.png" if slug else None
        _ITEM_SPRITE_EXISTS_CACHE[slug] = bool(path and path.is_file())
    return _ITEM_SPRITE_EXISTS_CACHE[slug]


def get_item_sprite(item_name: str | None, size: int = 22) -> QPixmap:
    try:
        normalized_size = int(size)
    except (TypeError, ValueError):
        return QPixmap()
    slug = item_sprite_slug(item_name)
    key = (slug, normalized_size)
    if key in _ITEM_SPRITE_CACHE:
        return _ITEM_SPRITE_CACHE[key]

    pixmap = (
        QPixmap(str(ITEM_SPRITE_DIRECTORY / f"{slug}.png"))
        if slug is not None and normalized_size > 0 and item_sprite_exists(item_name)
        else QPixmap()
    )
    if not pixmap.isNull():
        pixmap = pixmap.scaled(
            normalized_size,
            normalized_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )
    _ITEM_SPRITE_CACHE[key] = pixmap
    return pixmap


def clear_item_sprite_cache() -> None:
    _ITEM_SPRITE_CACHE.clear()
    _ITEM_SPRITE_EXISTS_CACHE.clear()
