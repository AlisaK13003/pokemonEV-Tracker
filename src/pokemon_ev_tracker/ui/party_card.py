"""Reusable compact party-card and six-slot grid widgets."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from pokemon_ev_tracker.ui.party_layout import party_card_positions

EV_STAT_LABELS = (
    ("hp", "HP"),
    ("attack", "Attack"),
    ("defense", "Defense"),
    ("special_attack", "Sp. Atk"),
    ("special_defense", "Sp. Def"),
    ("speed", "Speed"),
)
EV_STAT_LABEL_COLOR = "#d7dce2"
SECONDARY_TEXT_COLOR = "#b9c2cc"


class PartyCard(QGroupBox):
    def __init__(self, slot: int, parent=None) -> None:
        super().__init__(f"Slot {slot}", parent)
        self.setMinimumWidth(230)
        self.setMaximumWidth(390)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 7, 8, 7)
        layout.setSpacing(2)

        sprite = QLabel()
        sprite.setFixedSize(64, 64)
        sprite.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sprite.setScaledContents(False)
        sprite.setStyleSheet("background: palette(alternate-base); border-radius: 3px;")

        name = QLabel()
        name.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        name.setStyleSheet("font-size: 14px; font-weight: 600; color: #f0f2f5;")
        species_level = QLabel("-- • Lv. --")
        species_level.setStyleSheet("color: #d7dce2; font-weight: 600;")
        item_icon = QLabel()
        item_icon.setFixedSize(22, 22)
        item_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        item_icon.setStyleSheet("background: palette(alternate-base); border-radius: 2px;")
        item_name = QLabel("No held item")
        item_name.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        item_name.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        item_name.setStyleSheet(f"color: {SECONDARY_TEXT_COLOR};")
        item_row = QHBoxLayout()
        item_row.setContentsMargins(0, 0, 0, 0)
        item_row.setSpacing(5)
        item_row.addWidget(item_icon)
        item_row.addWidget(item_name, 1)
        item_hint = QLabel()
        item_hint.setStyleSheet("font-size: 9px; color: #b9c2cc;")
        item_hint.hide()
        level_hp = QLabel("HP -- / --")
        level_hp.setStyleSheet("color: #b9c2cc;")
        checksum = QLabel("RAM data pending")
        checksum.setStyleSheet("font-size: 9px; color: #b9c2cc;")
        checksum.setWordWrap(True)

        identity = QHBoxLayout()
        identity.setContentsMargins(0, 0, 0, 0)
        identity.setSpacing(7)
        identity.addWidget(sprite, 0, Qt.AlignmentFlag.AlignTop)
        details = QVBoxLayout()
        details.setContentsMargins(0, 0, 0, 0)
        details.setSpacing(1)
        details.addWidget(name)
        details.addWidget(species_level)
        details.addLayout(item_row)
        details.addWidget(item_hint)
        details.addWidget(level_hp)
        details.addWidget(checksum)
        identity.addLayout(details, 1)
        layout.addLayout(identity)

        training_content = QWidget(self)
        training_layout = QVBoxLayout(training_content)
        training_layout.setContentsMargins(0, 2, 0, 0)
        training_layout.setSpacing(2)
        ev_layout = QGridLayout()
        ev_layout.setContentsMargins(0, 2, 0, 0)
        ev_layout.setHorizontalSpacing(5)
        ev_layout.setVerticalSpacing(1)
        values, stat_names, annotations, bars, rows, timers = {}, {}, {}, {}, {}, {}
        for row, (key, label_text) in enumerate(EV_STAT_LABELS):
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(2, 0, 2, 0)
            row_layout.setSpacing(4)
            stat_name = QLabel(label_text)
            stat_name.setMinimumWidth(48)
            stat_name.setStyleSheet(f"color: {EV_STAT_LABEL_COLOR};")
            annotation = QLabel()
            annotation.setAlignment(Qt.AlignmentFlag.AlignRight)
            annotation.setStyleSheet("font-size: 9px; color: #b9c2cc;")
            annotation.hide()
            value = QLabel("-- / 252")
            value.setAlignment(Qt.AlignmentFlag.AlignRight)
            value.setMinimumWidth(55)
            bar = QProgressBar()
            bar.setRange(0, 252)
            bar.setTextVisible(False)
            bar.setFixedHeight(5)
            bar.setStyleSheet(
                "QProgressBar { border: 0; background: palette(alternate-base); }"
                "QProgressBar::chunk { background: palette(highlight); }"
            )
            row_layout.addWidget(stat_name)
            row_layout.addWidget(annotation, 1)
            row_layout.addWidget(value)
            row_layout.addWidget(bar, 1)
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(lambda widget=row_widget: widget.setStyleSheet(""))
            ev_layout.addWidget(row_widget, row, 0)
            values[key] = value
            stat_names[key] = stat_name
            annotations[key] = annotation
            bars[key] = bar
            rows[key] = row_widget
            timers[key] = timer
        training_layout.addLayout(ev_layout)

        total = QLabel("Total EVs: -- / 510")
        total.setStyleSheet("font-weight: 600; color: #d7dce2;")
        training_layout.addWidget(total)
        total_bar = QProgressBar()
        total_bar.setRange(0, 510)
        total_bar.setTextVisible(False)
        total_bar.setFixedHeight(6)
        total_bar.setStyleSheet(
            "QProgressBar { border: 0; background: palette(alternate-base); }"
            "QProgressBar::chunk { background: palette(highlight); }"
        )
        training_layout.addWidget(total_bar)
        target_summary = QLabel("No EV target set")
        target_summary.setStyleSheet(f"font-size: 10px; color: {SECONDARY_TEXT_COLOR};")
        training_layout.addWidget(target_summary)
        controls = QHBoxLayout()
        controls.addStretch(1)
        edit_button = QPushButton("Edit Target")
        clear_button = QPushButton("Clear Target")
        clear_button.setEnabled(False)
        controls.addWidget(edit_button)
        controls.addWidget(clear_button)
        training_layout.addLayout(controls)
        layout.addWidget(training_content)

        stats_content = QWidget(self)
        stats_layout = QVBoxLayout(stats_content)
        stats_layout.setContentsMargins(2, 3, 2, 0)
        stats_layout.setSpacing(2)
        nature = QLabel("Nature: --")
        nature.setStyleSheet("color: #d7dce2; font-weight: 600;")
        ability = QLabel("Ability: --")
        ability.setStyleSheet("color: #d7dce2;")
        friendship = QLabel("Friendship: -- / 255")
        friendship.setStyleSheet(f"color: {SECONDARY_TEXT_COLOR};")
        friendship_bar = QProgressBar()
        friendship_bar.setRange(0, 255)
        friendship_bar.setTextVisible(False)
        friendship_bar.setFixedHeight(5)
        friendship_bar.setStyleSheet(
            "QProgressBar { border: 0; background: palette(alternate-base); }"
            "QProgressBar::chunk { background: palette(highlight); }"
        )
        stats_layout.addWidget(nature)
        stats_layout.addWidget(ability)
        stats_layout.addWidget(friendship)
        stats_layout.addWidget(friendship_bar)
        moves_heading = QLabel("Moves")
        moves_heading.setStyleSheet("font-weight: 600; color: #d7dce2;")
        moves_list = QLabel("No moves decoded")
        moves_list.setWordWrap(True)
        moves_list.setStyleSheet(f"color: {SECONDARY_TEXT_COLOR};")
        stats_layout.addWidget(moves_heading)
        stats_layout.addWidget(moves_list)
        stats_grid = QGridLayout()
        stats_grid.setContentsMargins(0, 2, 0, 0)
        stats_grid.setHorizontalSpacing(7)
        stats_grid.setVerticalSpacing(1)
        stats_grid.addWidget(QLabel("Stat"), 0, 0)
        stats_grid.addWidget(QLabel("Value"), 0, 1, Qt.AlignmentFlag.AlignRight)
        stats_grid.addWidget(QLabel("IV"), 0, 2, Qt.AlignmentFlag.AlignRight)
        stat_values, iv_values, stat_names = {}, {}, {}
        for row, (key, label_text) in enumerate(EV_STAT_LABELS, start=1):
            stat_name = QLabel(label_text)
            stat_name.setStyleSheet(f"color: {EV_STAT_LABEL_COLOR};")
            stat_value = QLabel("--")
            stat_value.setAlignment(Qt.AlignmentFlag.AlignRight)
            iv_value = QLabel("--")
            iv_value.setAlignment(Qt.AlignmentFlag.AlignRight)
            iv_value.setStyleSheet(f"color: {SECONDARY_TEXT_COLOR};")
            stats_grid.addWidget(stat_name, row, 0)
            stats_grid.addWidget(stat_value, row, 1)
            stats_grid.addWidget(iv_value, row, 2)
            stat_names[key] = stat_name
            stat_values[key] = stat_value
            iv_values[key] = iv_value
        stats_layout.addLayout(stats_grid)
        stats_layout.addStretch(1)
        stats_content.hide()
        layout.addWidget(stats_content)

        self.fields: dict[str, object] = {
            "slot": slot,
            "widget": self,
            "training_content": training_content,
            "stats_content": stats_content,
            "sprite": sprite,
            "sprite_species_id": None,
            "sprite_size": 64,
            "sprite_loaded_size": None,
            "sprite_asset": None,
            "sprite_movie": None,
            "name": name,
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
            "moves_heading": moves_heading,
            "moves_list": moves_list,
            "moves_display_state": None,
            "stat_names": stat_names,
            "stat_values": stat_values,
            "iv_values": iv_values,
        }
        self.hide()


class PartyGrid(QWidget):
    def __init__(self, cards: dict[int, dict[str, object]], parent=None) -> None:
        super().__init__(parent)
        self.cards = cards
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(6)
        self.rows = []
        self.row_widgets = []
        for _ in range(2):
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(7)
            self.layout.addWidget(row_widget)
            self.rows.append(row_layout)
            self.row_widgets.append(row_widget)
        self._slots: tuple[int, ...] = ()

    def arrange(self, members) -> None:
        slots = tuple(member.slot for member in members)
        if slots == self._slots:
            return
        for row in self.rows:
            while row.count():
                item = row.takeAt(0)
                if item.widget() is not None:
                    item.widget().setParent(None)
        positions = party_card_positions(len(members))
        for row_index, row_widget in enumerate(self.row_widgets):
            row_widget.setVisible(any(row == row_index for row, _ in positions))
        for member, (row, _column) in zip(members, positions):
            self.rows[row].addWidget(self.cards[member.slot]["widget"])
        for row in self.rows:
            row.addStretch(1)
        self._slots = slots
