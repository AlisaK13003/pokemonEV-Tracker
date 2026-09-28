"""Reusable party-card and responsive grid widgets."""

from __future__ import annotations

from enum import Enum

from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from pokemon_ev_tracker.ui.collapsible_section import CollapsibleSection
from pokemon_ev_tracker.ui.theme import refresh_style

EV_STAT_LABELS = (
    ("hp", "HP"),
    ("attack", "Attack"),
    ("defense", "Defense"),
    ("special_attack", "Sp. Atk"),
    ("special_defense", "Sp. Def"),
    ("speed", "Speed"),
)
PARTY_GRID_SPACING = 14


class PartyCardSize(Enum):
    SMALL = (210, 230, 240, 48, (6, 5, 6, 5), 4)
    MEDIUM = (260, 300, 320, 64, (9, 8, 9, 8), 7)
    LARGE = (320, 360, 380, 72, (12, 10, 12, 10), 9)

    @property
    def minimum_width(self) -> int:
        return self.value[0]

    @property
    def preferred_width(self) -> int:
        return self.value[1]

    @property
    def maximum_width(self) -> int:
        return self.value[2]

    @property
    def sprite_size(self) -> int:
        return self.value[3]

    @property
    def margins(self) -> tuple[int, int, int, int]:
        return self.value[4]

    @property
    def layout_spacing(self) -> int:
        return self.value[5]


CARD_MIN_WIDTH = PartyCardSize.MEDIUM.minimum_width
CARD_PREFERRED_WIDTH = PartyCardSize.MEDIUM.preferred_width
CARD_MAX_WIDTH = PartyCardSize.MEDIUM.maximum_width


def _small_bar(maximum: int, height: int = 5) -> QProgressBar:
    bar = QProgressBar()
    bar.setRange(0, maximum)
    bar.setTextVisible(False)
    bar.setFixedHeight(height)
    return bar


def _label(text: str = "", role: str | None = None) -> QLabel:
    result = QLabel(text)
    if role:
        result.setProperty("uiRole", role)
    return result


def _clear_recent_change(widget: QWidget) -> None:
    widget.setProperty("recentChange", False)
    refresh_style(widget)


class PartyCard(QFrame):
    card_size_changed = Signal(object)

    def __init__(self, slot: int, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("partyCard")
        self.setProperty("uiRole", "partyCard")
        self.setProperty("cardSize", "medium")
        self.setMinimumWidth(CARD_MIN_WIDTH)
        self.setMaximumWidth(CARD_MAX_WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)
        self._card_size = PartyCardSize.MEDIUM
        self._expanded_before_small: dict[str, bool] | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(9, 8, 9, 8)
        layout.setSpacing(7)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        sprite = _label(role="sprite")
        sprite.setFixedSize(64, 64)
        sprite.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sprite.setScaledContents(False)

        name = _label(role="pokemonName")
        name.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        slot_label = _label(f"SLOT {slot}", "micro")
        species_level = _label("-- • Lv. --", "pokemonMeta")
        item_icon = _label(role="sprite")
        item_icon.setFixedSize(22, 22)
        item_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        item_name = _label("No held item", "muted")
        item_name.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        item_name.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        item_row = QHBoxLayout()
        item_row.setContentsMargins(0, 0, 0, 0)
        item_row.setSpacing(6)
        item_row.addWidget(item_icon)
        item_row.addWidget(item_name, 1)
        item_hint = _label(role="micro")
        item_hint.hide()
        level_hp = _label("HP -- / --", "muted")
        checksum = _label("RAM data pending", "micro")
        checksum.setProperty("ramState", "warning")
        checksum.setWordWrap(True)

        identity = QHBoxLayout()
        identity.setContentsMargins(0, 0, 0, 0)
        identity.setSpacing(9)
        identity.addWidget(sprite, 0, Qt.AlignmentFlag.AlignTop)
        details = QVBoxLayout()
        details.setContentsMargins(0, 0, 0, 0)
        details.setSpacing(2)
        name_row = QHBoxLayout()
        name_row.setContentsMargins(0, 0, 0, 0)
        name_row.addWidget(name, 1)
        name_row.addWidget(slot_label, 0, Qt.AlignmentFlag.AlignTop)
        details.addLayout(name_row)
        details.addWidget(species_level)
        details.addLayout(item_row)
        details.addWidget(item_hint)
        details.addWidget(level_hp)
        details.addWidget(checksum)
        identity.addLayout(details, 1)
        identity.setAlignment(details, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(identity)

        training_content = QWidget(self)
        training_content.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
        )
        training_layout = QVBoxLayout(training_content)
        training_layout.setContentsMargins(0, 0, 0, 0)
        training_layout.setSpacing(4)
        training_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        ev_content = QWidget(training_content)
        ev_content.setObjectName("partyEvRows")
        ev_content.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        ev_layout = QGridLayout(ev_content)
        ev_layout.setContentsMargins(2, 1, 2, 2)
        ev_layout.setHorizontalSpacing(7)
        ev_layout.setVerticalSpacing(3)
        values, stat_names, annotations, bars, rows, timers = {}, {}, {}, {}, {}, {}
        for row, (key, label_text) in enumerate(EV_STAT_LABELS):
            row_widget = QWidget(ev_content)
            row_widget.setProperty("uiRole", "evRow")
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(4, 2, 4, 2)
            row_layout.setSpacing(5)
            stat_name = _label(label_text)
            stat_name.setMinimumWidth(48)
            annotation = _label(role="micro")
            annotation.setAlignment(Qt.AlignmentFlag.AlignRight)
            annotation.hide()
            value = _label("-- / 252")
            value.setAlignment(Qt.AlignmentFlag.AlignRight)
            value.setMinimumWidth(55)
            bar = _small_bar(252)
            row_layout.addWidget(stat_name)
            row_layout.addWidget(annotation, 1)
            row_layout.addWidget(value)
            row_layout.addWidget(bar, 1)
            ev_layout.addWidget(row_widget, row, 0)
            values[key] = value
            stat_names[key] = stat_name
            annotations[key] = annotation
            bars[key] = bar
            rows[key] = row_widget
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(lambda widget=row_widget: _clear_recent_change(widget))
            timers[key] = timer

        total = _label("Total EVs: -- / 510", "pokemonMeta")
        total_bar = _small_bar(510, 6)
        ev_section = CollapsibleSection("EVs", ev_content, expanded=True, parent=training_content)
        training_layout.addWidget(ev_section)
        training_layout.addWidget(total)
        training_layout.addWidget(total_bar)

        target_content = QWidget(training_content)
        target_content.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
        )
        target_layout = QVBoxLayout(target_content)
        target_layout.setContentsMargins(2, 1, 2, 2)
        target_layout.setSpacing(5)
        target_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        target_summary = _label("No EV target set", "small")
        target_summary.setProperty("targetSeverity", "normal")
        target_layout.addWidget(target_summary)
        controls = QHBoxLayout()
        controls.addStretch(1)
        edit_button = QPushButton("Edit Target")
        clear_button = QPushButton("Clear Target")
        clear_button.setProperty("buttonRole", "danger")
        clear_button.setEnabled(False)
        controls.addWidget(edit_button)
        controls.addWidget(clear_button)
        target_layout.addLayout(controls)
        target_section = CollapsibleSection(
            "Target", target_content, expanded=False, parent=training_content
        )
        training_layout.addWidget(target_section)
        layout.addWidget(training_content)

        stats_content = QWidget(self)
        stats_content.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
        )
        stats_layout = QVBoxLayout(stats_content)
        stats_layout.setContentsMargins(0, 0, 0, 0)
        stats_layout.setSpacing(5)
        stats_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        metadata = QWidget(stats_content)
        metadata.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        metadata_layout = QVBoxLayout(metadata)
        metadata_layout.setContentsMargins(2, 0, 2, 0)
        metadata_layout.setSpacing(3)
        nature = _label("Nature: --", "pokemonMeta")
        ability = _label("Ability: --", "muted")
        friendship = _label("Friendship: -- / 255", "muted")
        friendship_bar = _small_bar(255)
        for widget in (friendship, friendship_bar):
            metadata_layout.addWidget(widget)
        stats_layout.addWidget(nature)
        stats_layout.addWidget(ability)

        stats_table = QWidget(stats_content)
        stats_table.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        stats_grid = QGridLayout(stats_table)
        stats_grid.setContentsMargins(2, 1, 2, 2)
        stats_grid.setHorizontalSpacing(8)
        stats_grid.setVerticalSpacing(3)
        for column, title in enumerate(("Stat", "Value", "IV")):
            heading = _label(title, "muted")
            heading.setProperty("uiRole", "tableHeader")
            if column:
                heading.setAlignment(Qt.AlignmentFlag.AlignRight)
            stats_grid.addWidget(heading, 0, column)
        stat_values, iv_values, stats_names = {}, {}, {}
        for row, (key, label_text) in enumerate(EV_STAT_LABELS, start=1):
            stat_name = _label(label_text)
            stat_value = _label("--")
            stat_value.setAlignment(Qt.AlignmentFlag.AlignRight)
            iv_value = _label("--", "muted")
            iv_value.setAlignment(Qt.AlignmentFlag.AlignRight)
            stats_grid.addWidget(stat_name, row, 0)
            stats_grid.addWidget(stat_value, row, 1)
            stats_grid.addWidget(iv_value, row, 2)
            stats_grid.setColumnStretch(0, 1)
            stats_names[key] = stat_name
            stat_values[key] = stat_value
            iv_values[key] = iv_value
        stats_section = CollapsibleSection(
            "Stats / IVs", stats_table, expanded=True, parent=stats_content
        )

        moves_list = _label("No moves decoded", "muted")
        moves_list.setWordWrap(True)
        moves_list.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        moves_section = CollapsibleSection(
            "Moves", moves_list, expanded=False, parent=stats_content
        )
        friendship_section = CollapsibleSection(
            "Friendship / Details", metadata, expanded=True, parent=stats_content
        )
        stats_layout.addWidget(stats_section)
        stats_layout.addWidget(moves_section)
        stats_layout.addWidget(friendship_section)
        stats_content.hide()
        layout.addWidget(stats_content)

        self.fields: dict[str, object] = {
            "slot": slot,
            "widget": self,
            "card_size": self._card_size,
            "training_content": training_content,
            "stats_content": stats_content,
            "ev_section": ev_section,
            "target_section": target_section,
            "stats_section": stats_section,
            "moves_section": moves_section,
            "friendship_section": friendship_section,
            "sprite": sprite,
            "sprite_species_id": None,
            "sprite_size": 64,
            "sprite_loaded_size": None,
            "sprite_asset": None,
            "sprite_movie": None,
            "name": name,
            "slot_label": slot_label,
            "species_level": species_level,
            "held_item_id": None,
            "item_icon": item_icon,
            "item_name": item_name,
            "item_hint": item_hint,
            "level_hp": level_hp,
            "checksum": checksum,
            "evs": values,
            "ev_stat_names": stat_names,
            "ev_annotations": annotations,
            "ev_bars": bars,
            "ev_rows": rows,
            "highlight_timers": timers,
            "total": total,
            "total_bar": total_bar,
            "pid": None,
            "pokemon": None,
            "ev_target": None,
            "target_summary": target_summary,
            "edit_target_button": edit_button,
            "clear_target_button": clear_button,
            "nature": nature,
            "ability": ability,
            "friendship": friendship,
            "friendship_bar": friendship_bar,
            "friendship_value": None,
            "friendship_display_state": None,
            "friendship_bar_compact": None,
            "moves_heading": moves_section.toggle,
            "moves_list": moves_list,
            "moves_display_state": None,
            "stat_names": stats_names,
            "stat_values": stat_values,
            "iv_values": iv_values,
        }
        self._small_collapsible_sections = {
            "ev": ev_section,
            "target": target_section,
            "stats": stats_section,
            "moves": moves_section,
            "friendship": friendship_section,
        }
        self.hide()

    def set_display_size(self, size: PartyCardSize) -> bool:
        if self._card_size is size:
            return False

        previous_size = self._card_size
        self._card_size = size
        self.setProperty("cardSize", size.name.lower())
        self.setMinimumWidth(0)
        self.setMaximumWidth(size.maximum_width)
        self.setMinimumWidth(size.minimum_width)
        self.layout().setContentsMargins(*size.margins)
        self.layout().setSpacing(size.layout_spacing)
        self.fields["card_size"] = size
        self.fields["sprite_size"] = size.sprite_size
        self.fields["sprite"].setFixedSize(size.sprite_size, size.sprite_size)
        refresh_style(self)

        if size is PartyCardSize.SMALL and previous_size is not PartyCardSize.SMALL:
            self._expanded_before_small = {
                key: section.is_expanded
                for key, section in self._small_collapsible_sections.items()
            }
            for section in self._small_collapsible_sections.values():
                section.toggle.setChecked(False)
        elif previous_size is PartyCardSize.SMALL and self._expanded_before_small is not None:
            for key, section in self._small_collapsible_sections.items():
                section.toggle.setChecked(self._expanded_before_small[key])
            self._expanded_before_small = None

        self.updateGeometry()
        self.card_size_changed.emit(self.fields)
        return True

    def minimumSizeHint(self):
        return self.sizeHint()


class PartyGrid(QWidget):
    """Six-slot grid that reflows as its scroll viewport changes width."""

    CARD_MIN_WIDTH = CARD_MIN_WIDTH
    CARD_PREFERRED_WIDTH = CARD_PREFERRED_WIDTH
    CARD_MAX_WIDTH = CARD_MAX_WIDTH
    SMALL_CARD_PREFERRED_WIDTH = PartyCardSize.SMALL.preferred_width
    HORIZONTAL_SPACING = PARTY_GRID_SPACING
    VERTICAL_SPACING = PARTY_GRID_SPACING
    SMALL_WIDTH_LIMIT = 800
    MEDIUM_WIDTH_LIMIT = 1200

    def __init__(self, cards: dict[int, dict[str, object]], parent=None) -> None:
        super().__init__(parent)
        self.cards = cards
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Minimum)
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(self.HORIZONTAL_SPACING)
        self._grid.setVerticalSpacing(self.VERTICAL_SPACING)
        self._grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.rows: list[object] = []
        self.row_widgets: list[object] = []
        self._members = ()
        self._slots: tuple[int, ...] = ()
        self._layout_signature: tuple[tuple[int, ...], int, PartyCardSize] | None = None
        self.columns = 1
        self.compact_layout = False
        self.card_size = PartyCardSize.MEDIUM
        self._observed_viewport: QWidget | None = None

    def _available_width(self) -> int:
        ancestor = self.parentWidget()
        while ancestor is not None:
            if isinstance(ancestor, QScrollArea):
                viewport = ancestor.viewport()
                if viewport is not self._observed_viewport:
                    if self._observed_viewport is not None:
                        self._observed_viewport.removeEventFilter(self)
                    viewport.installEventFilter(self)
                    self._observed_viewport = viewport
                page_layout = ancestor.widget().layout()
                margins = page_layout.contentsMargins() if page_layout else None
                horizontal_margins = (
                    margins.left() + margins.right() if margins else 0
                )
                return max(1, viewport.width() - horizontal_margins)
            ancestor = ancestor.parentWidget()
        return max(1, self.contentsRect().width())

    def minimumSizeHint(self):
        return self._grid.sizeHint()

    def eventFilter(self, watched, event) -> bool:
        if (
            watched is self._observed_viewport
            and event.type() == QEvent.Type.Resize
        ):
            self._layout_members()
        return super().eventFilter(watched, event)

    @staticmethod
    def columns_for_width(width: int, card_size: PartyCardSize) -> int:
        return min(
            3,
            max(
                1,
                (width + PartyGrid.HORIZONTAL_SPACING)
                // (card_size.preferred_width + PartyGrid.HORIZONTAL_SPACING),
            ),
        )

    def _size_for_width(self, width: int) -> PartyCardSize:
        if self.compact_layout or width < self.SMALL_WIDTH_LIMIT:
            return PartyCardSize.SMALL
        if width < self.MEDIUM_WIDTH_LIMIT:
            return PartyCardSize.MEDIUM
        return PartyCardSize.LARGE

    def arrange(self, members) -> None:
        members = tuple(members)
        slots = tuple(member.slot for member in members)
        if slots == self._slots:
            self._members = members
            return
        self._members = members
        self._slots = slots
        active_slots = set(self._slots)
        for slot, card in self.cards.items():
            card["widget"].setVisible(slot in active_slots)
        self._layout_members()

    def set_compact_layout(self, compact: bool) -> None:
        if self.compact_layout == compact:
            return
        self.compact_layout = compact
        self._layout_members()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._layout_members()

    def _layout_members(self) -> None:
        width = self._available_width()
        count = len(self._members)
        card_size = self._size_for_width(width)
        self.card_size = card_size
        available_columns = self.columns_for_width(width, card_size)
        columns = min(max(count, 1), available_columns)
        self.columns = columns
        available_card_width = (
            width - self.HORIZONTAL_SPACING * (columns - 1)
        ) // columns
        card_width = max(
            card_size.minimum_width,
            min(card_size.maximum_width, card_size.preferred_width, available_card_width),
        )
        for member in self._members:
            widget = self.cards[member.slot]["widget"]
            widget.set_display_size(card_size)
            widget.setFixedWidth(card_width)
        signature = self._slots, columns, card_size
        if signature == self._layout_signature:
            return
        self._layout_signature = signature
        while self._grid.count():
            self._grid.takeAt(0)
        for index in range(7):
            self._grid.setColumnStretch(index, 0)
            self._grid.setRowStretch(index, 0)
        self._grid.setColumnStretch(columns, 1)
        for index, member in enumerate(self._members):
            card = self.cards[member.slot]["widget"]
            self._grid.addWidget(
                card,
                index // columns,
                index % columns,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
            )
