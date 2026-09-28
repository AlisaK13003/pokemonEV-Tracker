"""Compact display for the currently active opposing Pokémon."""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtGui import QMovie
from PySide6.QtWidgets import (
    QBoxLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from pokemon_ev_tracker.games.platinum.ev_yields import format_ev_yield_summary
from pokemon_ev_tracker.ui.sprite_loader import (
    get_animated_sprite_size,
    get_static_sprite,
    resolve_sprite_asset,
)

LOGGER = logging.getLogger(__name__)


class _OpponentCard(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setProperty("uiRole", "opponentCard")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._species_id: int | None = None
        self._asset = None
        self._movie: QMovie | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 5, 8, 6)
        layout.setSpacing(8)
        self.sprite = QLabel()
        self.sprite.setFixedSize(64, 64)
        self.sprite.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sprite.setProperty("uiRole", "sprite")
        layout.addWidget(self.sprite)

        details = QVBoxLayout()
        details.setContentsMargins(0, 0, 0, 0)
        details.setSpacing(2)
        self.name = QLabel("Not currently battling")
        self.name.setProperty("uiRole", "pokemonName")
        self.ev_yield = QLabel()
        self.ev_yield.setProperty("uiRole", "muted")
        self.ev_yield.setToolTip(
            "Base species EV yield. Held items and Pokérus can change the EVs awarded."
        )
        details.addWidget(self.name)
        details.addWidget(self.ev_yield)
        details.addStretch(1)
        layout.addLayout(details, 1)

    def set_opponent(self, pokemon) -> None:
        if pokemon is None:
            self.clear()
            return

        species_id = pokemon.species_id
        asset = resolve_sprite_asset(species_id)
        if self._species_id != species_id or self._asset != asset:
            self._set_sprite(species_id, asset)

        level = pokemon.level if pokemon.level is not None else "--"
        self.name.setText(f"{pokemon.species} • Lv. {level}")
        self.ev_yield.setText(format_ev_yield_summary(species_id))

    def clear(self) -> None:
        self._clear_sprite()
        self.name.clear()
        self.ev_yield.clear()

    def _set_sprite(self, species_id: int, asset) -> None:
        self._clear_sprite()
        if asset.kind == "animated" and asset.path is not None:
            movie = QMovie(str(asset.path), parent=self.sprite)
            if movie.isValid():
                movie.setScaledSize(get_animated_sprite_size(asset.path, 64))
                self.sprite.setMovie(movie)
                self._movie = movie
                movie.start()
            else:
                movie.deleteLater()
                self.sprite.setPixmap(get_static_sprite(species_id, 64))
        elif asset.kind == "static":
            self.sprite.setPixmap(get_static_sprite(species_id, 64))
        self._species_id = species_id
        self._asset = asset

    def _clear_sprite(self) -> None:
        if self._movie is not None:
            self._movie.stop()
            self._movie.deleteLater()
            self._movie = None
        self.sprite.clear()
        self._species_id = None
        self._asset = None


class CurrentOpponentPanel(QGroupBox):
    def __init__(self, parent=None) -> None:
        super().__init__("Currently Battling", parent)
        self.setObjectName("currentlyBattling")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 8, 5)
        layout.setSpacing(6)

        self.empty_label = QLabel("Not currently battling")
        self.empty_label.setProperty("uiRole", "emptyState")
        layout.addWidget(self.empty_label)
        self.cards = [_OpponentCard(self), _OpponentCard(self)]
        for card in self.cards:
            card.hide()
            layout.addWidget(card, 1)
        self._set_layout_direction()
        self.setMaximumHeight(58)

        # Keep the first-opponent labels available for callers and diagnostics.
        self.sprite = self.cards[0].sprite
        self.name = self.cards[0].name
        self.ev_yield = self.cards[0].ev_yield

    def set_opponent(self, pokemon) -> None:
        self.set_opponents((pokemon,) if pokemon is not None else ())

    def set_opponents(self, pokemon_list) -> None:
        opponents = tuple(pokemon_list or ())[:2]
        self._set_layout_direction()
        self.empty_label.setVisible(not opponents)
        for index, card in enumerate(self.cards):
            if index < len(opponents):
                card.set_opponent(opponents[index])
                card.show()
            else:
                card.clear()
                card.hide()
        self._update_panel_height()
        visible_cards = sum(not card.isHidden() for card in self.cards)
        content_visible = self.isVisible() and (
            all(card.isVisible() for card in self.cards[: len(opponents)])
            if opponents
            else self.empty_label.isVisible()
        )
        LOGGER.debug(
            "OpponentPanel received: %d; cards rendered: %d; layout count after render: %d; "
            "panel visible: %s; panel height: %d; content visible: %s; visible cards: %d",
            len(opponents),
            visible_cards,
            self.layout().count(),
            self.isVisible(),
            self.height(),
            content_visible,
            sum(card.isVisible() for card in self.cards),
        )

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._set_layout_direction()
        self._update_panel_height()

    def _update_panel_height(self) -> None:
        visible_cards = sum(not card.isHidden() for card in self.cards)
        if visible_cards == 0:
            self.setMaximumHeight(58)
        elif visible_cards == 2 and self.width() < 650:
            self.setMaximumHeight(220)
        else:
            self.setMaximumHeight(125)

    def _set_layout_direction(self) -> None:
        layout = self.layout()
        layout.setDirection(
            QBoxLayout.Direction.TopToBottom
            if self.width() < 650
            else QBoxLayout.Direction.LeftToRight
        )
