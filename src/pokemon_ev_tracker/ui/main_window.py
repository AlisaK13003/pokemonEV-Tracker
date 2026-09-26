"""Application window composing the BizHawk-backed Platinum tracker."""

from __future__ import annotations

import time
from datetime import datetime

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence, QMovie, QShortcut
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from pokemon_ev_tracker.core.ev_changes import EVChangeTracker
from pokemon_ev_tracker.core.ev_targets import EVTargetStore
from pokemon_ev_tracker.data_sources.bizhawk import BizHawkRamDataSource
from pokemon_ev_tracker.games.platinum.decoder import nickname_is_default
from pokemon_ev_tracker.games.platinum.items import get_gen4_item_hint
from pokemon_ev_tracker.games.platinum.profile import PLATINUM_PROFILE
from pokemon_ev_tracker.pokemon.gen4.structure import (
    HELD_ITEM_BOX_DATA_OFFSET,
    HELD_ITEM_RECORD_OFFSET,
)
from pokemon_ev_tracker.ui.backend_status import BackendStatusWidget
from pokemon_ev_tracker.ui.ev_change_log import EvChangeLogWidget
from pokemon_ev_tracker.ui.ev_target_dialog import EVTargetDialog
from pokemon_ev_tracker.ui.item_sprite_loader import (
    get_item_sprite,
    item_sprite_exists,
    item_sprite_path,
    item_sprite_slug,
)
from pokemon_ev_tracker.ui.party_card import SECONDARY_TEXT_COLOR, PartyCard, PartyGrid
from pokemon_ev_tracker.ui.sprite_loader import (
    get_animated_sprite_size,
    get_static_sprite,
    resolve_sprite_asset,
)


def _format_optional_hex(value: int | None) -> str:
    return f"0x{value:08X}" if value is not None else "--"


class MainWindow(QMainWindow):
    def __init__(
        self,
        settings,
        data_source: BizHawkRamDataSource | None = None,
        target_store: EVTargetStore | None = None,
    ) -> None:
        super().__init__()
        self.settings = settings
        self.profile = getattr(data_source, "profile", PLATINUM_PROFILE)
        self.ram_data_source = data_source or BizHawkRamDataSource(profile=self.profile)
        self.ev_target_store = target_store or EVTargetStore()
        self.compact_mode = False
        self._compact_member_count = -1
        self._party_layout_slots: tuple[int, ...] = ()
        self._ev_history_records: list[tuple[str, str]] = []
        self._pre_compact_tab_index = 0
        self._suspend_geometry_save = True
        self._changing_mode = False
        self._ev_change_tracker = EVChangeTracker()
        self._ev_history_limit = 200

        self.setWindowTitle(f"{self.profile.display_name} EV Tracker")
        self.resize(1100, 760)
        self._build_ui()
        self._geometry_save_timer = QTimer(self)
        self._geometry_save_timer.setSingleShot(True)
        self._geometry_save_timer.setInterval(450)
        self._geometry_save_timer.timeout.connect(self._save_window_state)

        saved_geometry = (
            settings.window_geometry
            if settings.compact_mode
            else settings.normal_window_geometry or settings.window_geometry
        )
        if saved_geometry is not None:
            self.setGeometry(*saved_geometry)
        self._set_compact_mode(settings.compact_mode, persist=False, initial=True)
        self._suspend_geometry_save = False

        self.ram_data_source.start()
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._refresh_ram_backend_debug)
        self.refresh_timer.setInterval(250)
        self.refresh_timer.start()
        self._refresh_ram_backend_debug()

    def _build_ui(self) -> None:
        root = QWidget(self)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(8, 7, 8, 7)
        root_layout.setSpacing(6)
        self._root_layout = root_layout

        self.tracker_title = QLabel(f"{self.profile.display_name} EV Tracker")
        self.tracker_title.setStyleSheet("font-size: 20px; font-weight: 600;")
        root_layout.addWidget(self.tracker_title)

        toolbar = QWidget()
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.setSpacing(8)
        self.compact_mode_button = QPushButton("Compact Mode")
        self.compact_mode_button.setCheckable(True)
        self.compact_mode_button.setToolTip("Toggle compact always-on-top tracker")
        self.compact_mode_button.toggled.connect(self.set_compact_mode)
        toolbar_layout.addWidget(self.compact_mode_button)
        self.backend_status = BackendStatusWidget()
        toolbar_layout.addWidget(self.backend_status, 1)
        root_layout.addWidget(toolbar)
        self.compact_status_label = self.backend_status.compact_label
        self.tracker_backend_group = self.backend_status
        self.tracker_status_labels = {
            "backend": self.backend_status.details["backend"],
            "connection": self.backend_status.details["connection"],
            "memory_domain": self.backend_status.details["domain"],
            "last_update": self.backend_status.details["last_update"],
            "frame": self.backend_status.details["frame"],
        }

        self.compact_shortcut = QShortcut(QKeySequence("Ctrl+Shift+C"), self)
        self.compact_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        self.compact_shortcut.activated.connect(self.compact_mode_button.toggle)

        self.main_tabs = QTabWidget()
        tracker_page = QWidget()
        self.tracker_layout = QVBoxLayout(tracker_page)
        self.tracker_layout.setContentsMargins(4, 4, 4, 4)
        self.tracker_layout.setSpacing(7)
        self.tracker_connection_message = QLabel("Waiting for BizHawk / EmuHawk RAM connection...")
        self.tracker_connection_message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tracker_connection_message.setMinimumHeight(34)
        self.tracker_connection_message.setStyleSheet(f"color: {SECONDARY_TEXT_COLOR};")
        self.tracker_layout.addWidget(self.tracker_connection_message)

        party_heading = QLabel("Party")
        party_heading.setStyleSheet("font-size: 16px; font-weight: 600;")
        self.tracker_layout.addWidget(party_heading)
        self.tracker_party_cards = {}
        self.party_card_widgets = {}
        for slot in range(1, 7):
            widget = PartyCard(slot, tracker_page)
            self.tracker_party_cards[slot] = widget.fields
            self.party_card_widgets[slot] = widget
            widget.fields["edit_target_button"].clicked.connect(
                lambda _checked=False, card_slot=slot: self._edit_ev_target(card_slot)
            )
            widget.fields["clear_target_button"].clicked.connect(
                lambda _checked=False, card_slot=slot: self._clear_ev_target(card_slot)
            )
        self.party_grid = PartyGrid(self.tracker_party_cards, tracker_page)
        self.tracker_party_cards_widget = self.party_grid
        self.tracker_party_card_rows = self.party_grid.rows
        self.tracker_party_card_row_widgets = self.party_grid.row_widgets
        self.tracker_layout.addWidget(self.party_grid)

        self.ev_change_log = EvChangeLogWidget(self._clear_ev_log, tracker_page)
        self.ev_change_list = self.ev_change_log.list
        self.clear_ev_log_button = self.ev_change_log.clear_button
        self.ev_history_group = self.ev_change_log
        self.tracker_layout.addWidget(self.ev_change_log)
        self.tracker_layout.addStretch(1)
        self.main_tabs.addTab(tracker_page, "Tracker")

        debug_page = QWidget()
        debug_layout = QVBoxLayout(debug_page)
        debug_layout.setContentsMargins(8, 8, 8, 8)
        self.ram_backend_labels = {}
        status_grid = QVBoxLayout()
        self.available_domains_label = QLabel("Available domains: --")
        self.available_domains_label.setWordWrap(True)
        self.ram_backend_labels["available_domains"] = self.available_domains_label
        self.ram_backend_labels.update(self.tracker_status_labels)
        for key, title in (
            ("backend", "Backend"),
            ("connection", "Connection"),
            ("memory_domain", "Memory domain"),
            ("last_update", "Last update"),
            ("frame", "Frame"),
        ):
            row = QHBoxLayout()
            row.addWidget(QLabel(title))
            row.addWidget(self.tracker_status_labels[key], 1)
            status_grid.addLayout(row)
        status_grid.addWidget(self.available_domains_label)
        debug_layout.addLayout(status_grid)
        self.ram_party_summary_label = QLabel("Party count: --")
        self.ram_party_details = QPlainTextEdit()
        self.ram_party_details.setReadOnly(True)
        self.ram_party_details.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.ram_party_details.setPlaceholderText("Waiting for party memory payload.")
        debug_layout.addWidget(self.ram_party_summary_label)
        debug_layout.addWidget(self.ram_party_details, 1)
        self.main_tabs.addTab(debug_page, "RAM Debug")
        root_layout.addWidget(self.main_tabs, 1)
        self.setCentralWidget(root)

    def set_compact_mode(self, enabled: bool) -> None:
        self._set_compact_mode(bool(enabled), persist=True)

    def _set_compact_mode(self, enabled: bool, persist: bool = True, initial: bool = False) -> None:
        if enabled == self.compact_mode and not initial:
            return
        was_visible = self.isVisible()
        self._changing_mode = True
        if enabled:
            self._pre_compact_tab_index = self.main_tabs.currentIndex()
            if not initial:
                self.settings.normal_window_geometry = self._current_window_geometry()
            self.compact_mode = True
            self.main_tabs.setTabVisible(1, False)
            self.main_tabs.setCurrentIndex(0)
            self.main_tabs.tabBar().hide()
            self.tracker_title.hide()
            self.backend_status.details_widget.hide()
            self.ev_change_list.setMaximumHeight(82)
            self._root_layout.setContentsMargins(4, 3, 4, 3)
            self._root_layout.setSpacing(3)
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
            if not initial:
                self._resize_compact_window(max(self._compact_member_count, 1))
        else:
            self.compact_mode = False
            self.main_tabs.setTabVisible(1, True)
            self.main_tabs.tabBar().show()
            self.tracker_title.show()
            self.backend_status.details_widget.show()
            self.ev_change_list.setMaximumHeight(160)
            self._root_layout.setContentsMargins(8, 7, 8, 7)
            self._root_layout.setSpacing(6)
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, False)
            self.main_tabs.setCurrentIndex(min(self._pre_compact_tab_index, 1))
            if self.settings.normal_window_geometry is not None:
                self.setGeometry(*self.settings.normal_window_geometry)
        self.compact_mode_button.setChecked(enabled)
        self.ev_change_log.render(self._ev_history_records, self.compact_mode)
        # Changing window flags hides a visible QWidget; use its state from before
        # the transition so compact mode does not make the app disappear.
        if was_visible:
            self.show()
        self._changing_mode = False
        if persist:
            self.settings.compact_mode = enabled
            self.settings.save_default()

    def _resize_compact_window(self, member_count: int) -> None:
        columns = min(max(int(member_count), 1), 3)
        width = max(320, 250 * columns + 24)
        rows = 1 if member_count <= 3 else 2
        height = 120 + rows * 300
        self.resize(width, height)

    def _current_window_geometry(self) -> tuple[int, int, int, int]:
        geometry = self.geometry()
        return geometry.x(), geometry.y(), geometry.width(), geometry.height()

    def _save_window_state(self) -> None:
        if self._suspend_geometry_save:
            return
        geometry = self._current_window_geometry()
        self.settings.window_geometry = geometry
        if not self.compact_mode:
            self.settings.normal_window_geometry = geometry
        self.settings.compact_mode = self.compact_mode
        self.settings.save_default()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if not self._suspend_geometry_save and not self._changing_mode:
            self._geometry_save_timer.start()

    def moveEvent(self, event) -> None:
        super().moveEvent(event)
        if not self._suspend_geometry_save and not self._changing_mode:
            self._geometry_save_timer.start()

    def _refresh_ram_backend_debug(self) -> None:
        snapshot = self.ram_data_source.snapshot()
        heartbeat = snapshot.details.get("heartbeat")
        party_state = snapshot.details.get("party_state")
        party_payload = snapshot.details.get("party_payload")
        age = max(0.0, time.monotonic() - heartbeat.received_at) if heartbeat else None
        self.backend_status.set_connection(
            snapshot.backend_name, snapshot.connected, heartbeat, age
        )
        domains = heartbeat.payload.get("domains", []) if heartbeat else []
        self.available_domains_label.setText(
            "Available domains: " + (", ".join(map(str, domains)) if domains else "--")
        )
        self._refresh_ram_party_debug(party_state, party_payload)
        self._refresh_tracker_party(snapshot.connected, party_state)
        if snapshot.connected:
            self._record_ev_changes(party_state)

    def _refresh_tracker_party(self, connected: bool, party_state) -> None:
        members = ()
        if (
            connected
            and party_state is not None
            and party_state.party_count_valid
            and not (party_state.error and not party_state.pokemon)
        ):
            members = tuple(party_state.pokemon)
        previous_count = self._compact_member_count
        self._compact_member_count = len(members)
        member_count = len(members)
        if self.compact_mode and previous_count != member_count:
            QTimer.singleShot(0, lambda: self._resize_compact_window(max(member_count, 1)))

        active_slots = {pokemon.slot for pokemon in members}
        for slot, card in self.tracker_party_cards.items():
            if slot not in active_slots:
                card["widget"].hide()
                card["pid"] = None
                card["pokemon"] = None
                if card["sprite_species_id"] is not None:
                    self._clear_tracker_card_sprite(card)
        self.party_grid.arrange(members)

        message = None
        if not connected:
            message = "Waiting for BizHawk / EmuHawk RAM connection..."
        elif party_state is None:
            message = "Waiting for party RAM data..."
        elif not party_state.party_count_valid:
            message = party_state.error or "Waiting for valid party RAM data..."
        elif party_state.error and not party_state.pokemon:
            message = party_state.error
        elif not members:
            message = "No Pokémon in party."
        if message is not None:
            self.tracker_connection_message.setText(message)
            self.tracker_connection_message.show()
            self.party_grid.hide()
            return

        self.tracker_connection_message.hide()
        self.party_grid.show()
        for pokemon in members:
            card = self.tracker_party_cards[pokemon.slot]
            card["pid"] = pokemon.decoded.diagnostics.pid
            card["pokemon"] = pokemon
            self._refresh_tracker_card_sprite(card, pokemon.species_id)
            if nickname_is_default(pokemon.nickname, pokemon.species):
                card["name"].hide()
            else:
                card["name"].setText(pokemon.nickname)
                card["name"].show()
            card["species_level"].setText(
                f"{pokemon.species} • Lv. {pokemon.level if pokemon.level is not None else '--'}"
            )
            self._refresh_tracker_held_item(card, pokemon)
            card["level_hp"].setText(
                f"HP {pokemon.current_hp if pokemon.current_hp is not None else '--'} / "
                f"{pokemon.max_hp if pokemon.max_hp is not None else '--'}"
            )
            card["checksum"].setText(
                "✓ RAM data valid" if pokemon.checksum_valid else "Warning: RAM checksum invalid"
            )
            card["checksum"].setStyleSheet(
                "font-size: 9px; color: #79b58e;"
                if pokemon.checksum_valid
                else "font-size: 10px; color: #d18888; font-weight: 600;"
            )
            for stat, label in card["evs"].items():
                value = pokemon.evs[stat]
                label.setText(f"{value} / 252" if pokemon.checksum_valid else "-- / 252")
                card["ev_bars"][stat].setValue(
                    max(0, min(252, value)) if pokemon.checksum_valid else 0
                )
            total = pokemon.ev_total if pokemon.checksum_valid else None
            card["total"].setText(f"Total EVs: {total if total is not None else '--'} / 510")
            card["total_bar"].setValue(max(0, min(510, total)) if total is not None else 0)
            self._refresh_tracker_target_display(card, pokemon)
            card["widget"].show()

    def _refresh_tracker_target_display(self, card: dict[str, object], pokemon) -> None:
        pid = pokemon.decoded.diagnostics.pid
        target = self.ev_target_store.get(pid)
        card["ev_target"] = target
        card["clear_target_button"].setEnabled(target is not None)
        summary = card["target_summary"]
        if target is None:
            summary.setText("No EV target set")
            summary.setStyleSheet(f"font-size: 10px; color: {SECONDARY_TEXT_COLOR};")
            for stat in card["evs"]:
                card["ev_annotations"][stat].clear()
                card["ev_annotations"][stat].hide()
                card["ev_bars"][stat].setRange(0, 252)
                card["ev_bars"][stat].show()
            return

        if not pokemon.checksum_valid:
            summary.setText("Target progress unavailable: checksum invalid")
            summary.setStyleSheet("font-size: 10px; color: #d18888;")
            return

        progress = target.progress(pokemon.evs)
        summary.setText(
            "Target complete"
            if progress.complete
            else f"{progress.remaining} EVs remaining"
            if getattr(self, "compact_mode", False)
            else f"Target progress: {progress.achieved} / {progress.target_total}"
            f" • {progress.remaining} EVs remaining"
        )
        summary.setStyleSheet(
            f"font-size: 10px; color: {'#d18888' if progress.overshoots else SECONDARY_TEXT_COLOR};"
        )
        for stat, label in card["evs"].items():
            annotation = card["ev_annotations"][stat]
            bar = card["ev_bars"][stat]
            stat_target = target.as_mapping()[stat]
            current = pokemon.evs[stat]
            if stat_target == 0:
                label.setText(str(current) if current == 0 else f"{current} / 0")
                if current > 0:
                    annotation.setText(f"+{current} over target")
                    annotation.setStyleSheet("font-size: 9px; color: #d18888;")
                    annotation.show()
                else:
                    annotation.hide()
                bar.hide()
            else:
                label.setText(f"{current} / {stat_target}")
                annotation.setText(
                    f"+{current - stat_target} over target"
                    if current > stat_target
                    else f"{stat_target - current} remaining"
                )
                annotation.setStyleSheet(
                    "font-size: 9px; color: #d18888;"
                    if current > stat_target
                    else f"font-size: 9px; color: {SECONDARY_TEXT_COLOR};"
                )
                annotation.show()
                bar.setRange(0, stat_target)
                bar.setValue(max(0, min(stat_target, current)))
                bar.show()

    def _edit_ev_target(self, slot: int) -> None:
        card = self.tracker_party_cards.get(slot)
        if card is None or card["pid"] is None or card["pokemon"] is None:
            return
        pokemon, pid = card["pokemon"], card["pid"]
        title = (
            pokemon.species
            if nickname_is_default(pokemon.nickname, pokemon.species)
            else f"{pokemon.nickname} ({pokemon.species})"
        )
        dialog = EVTargetDialog(title, self.ev_target_store.get(pid), self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            self.ev_target_store.set(pid, dialog.target())
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "Could not save EV target", str(error))
            return
        self._refresh_tracker_target_display(card, pokemon)

    def _clear_ev_target(self, slot: int) -> None:
        card = self.tracker_party_cards.get(slot)
        if card is None or card["pid"] is None or card["pokemon"] is None:
            return
        try:
            self.ev_target_store.clear(card["pid"])
        except OSError as error:
            QMessageBox.warning(self, "Could not clear EV target", str(error))
            return
        self._refresh_tracker_target_display(card, card["pokemon"])

    @staticmethod
    def _refresh_tracker_held_item(card: dict[str, object], pokemon) -> bool:
        item_id = pokemon.held_item_id
        if card["held_item_id"] == item_id:
            return False
        card["held_item_id"] = item_id
        icon, name, hint_label = card["item_icon"], card["item_name"], card["item_hint"]
        if pokemon.held_item_name is None:
            icon.clear()
            name.setText("No held item")
            name.setStyleSheet(f"color: {SECONDARY_TEXT_COLOR};")
            hint_label.clear()
            hint_label.hide()
            return True
        icon.setPixmap(get_item_sprite(pokemon.held_item_name, 22))
        name.setText(pokemon.held_item_name)
        name.setStyleSheet("color: #e0e4e9;")
        hint = get_gen4_item_hint(item_id)
        hint_label.setText(hint or "")
        hint_label.setVisible(bool(hint))
        return True

    @staticmethod
    def _refresh_tracker_card_sprite(card: dict[str, object], species_id: int) -> bool:
        size = card["sprite_size"]
        asset = resolve_sprite_asset(species_id)
        if (
            card["sprite_species_id"] == species_id
            and card["sprite_loaded_size"] == size
            and card["sprite_asset"] == asset
        ):
            return False
        MainWindow._clear_tracker_card_sprite(card)
        sprite = card["sprite"]
        sprite.setFixedSize(size, size)
        if asset.kind == "animated" and asset.path is not None:
            movie = QMovie(str(asset.path))
            movie.setParent(sprite)
            if movie.isValid():
                movie.setScaledSize(get_animated_sprite_size(asset.path, size))
                sprite.setMovie(movie)
                card["sprite_movie"] = movie
                movie.start()
            else:
                movie.deleteLater()
                sprite.setPixmap(get_static_sprite(species_id, size))
        elif asset.kind == "static":
            sprite.setPixmap(get_static_sprite(species_id, size))
        card["sprite_species_id"] = species_id
        card["sprite_loaded_size"] = size
        card["sprite_asset"] = asset
        return True

    @staticmethod
    def _clear_tracker_card_sprite(card: dict[str, object]) -> None:
        movie = card["sprite_movie"]
        if movie is not None:
            movie.stop()
            movie.deleteLater()
            card["sprite_movie"] = None
        card["sprite"].clear()
        card["sprite_species_id"] = None
        card["sprite_loaded_size"] = None
        card["sprite_asset"] = None

    def _record_ev_changes(self, party_state) -> None:
        changes = self._ev_change_tracker.observe(party_state)
        if not changes:
            return
        timestamp = datetime.now().astimezone().strftime("%H:%M:%S")
        labels = {
            "hp": "HP",
            "attack": "Attack",
            "defense": "Defense",
            "special_attack": "Special Attack",
            "special_defense": "Special Defense",
            "speed": "Speed",
        }
        for change in changes:
            name = (
                change.species
                if nickname_is_default(change.nickname, change.species)
                else f"{change.nickname} ({change.species})"
            )
            stat_name = labels.get(change.stat, change.stat)
            full = (
                f"{timestamp}  {name:<24} {stat_name:<15} "
                f"{change.before:>3} -> {change.after:<3}  {change.delta:+d}"
            )
            self._ev_history_records.append((full, f"{change.delta:+d} {stat_name}"))
            self._highlight_ev_change(change.slot, change.stat)
        del self._ev_history_records[: -self._ev_history_limit]
        self._render_ev_history()

    def _highlight_ev_change(self, slot: int, stat: str) -> None:
        card = self.tracker_party_cards.get(slot)
        if card is None:
            return
        row = card["ev_rows"].get(stat)
        timer = card["highlight_timers"].get(stat)
        if row is not None and timer is not None:
            row.setStyleSheet("background-color: palette(alternate-base); border-radius: 3px;")
            timer.start(1500)

    def _render_ev_history(self) -> None:
        self.ev_change_log.render(self._ev_history_records, self.compact_mode)

    def _clear_ev_log(self) -> None:
        self._ev_history_records.clear()
        self._render_ev_history()

    def _refresh_ram_party_debug(self, party_state, party_payload) -> None:
        if party_state is None:
            self.ram_party_summary_label.setText("Party count: --")
            self.ram_party_details.setPlainText("Waiting for party memory payload.")
            return
        count = str(party_state.party_count) if party_state.party_count is not None else "--"
        self.ram_party_summary_label.setText(
            f"Party count: {count} ({'valid' if party_state.party_count_valid else 'invalid'})"
        )
        lines = []
        if party_payload is not None:
            payload = party_payload.payload
            lines.extend(
                (
                    f"Source: {party_payload.source}",
                    f"Frame: {payload.get('frame', '--')}",
                    f"Domain: {payload.get('domain', '--')}",
                    f"Pointer address: {payload.get('pointer_address', '--')}",
                    f"Pointer offset: {payload.get('pointer_offset', '--')}",
                    f"Pointer value: {payload.get('pointer_value', '--')}",
                    f"Party relative offset: {payload.get('party_relative_offset', '--')}",
                    f"Party address: {payload.get('party_address', '--')}",
                    f"Party offset: {payload.get('party_offset', '--')}",
                    f"Party records address: {payload.get('party_records_address', '--')}",
                    f"Party records offset: {payload.get('party_records_offset', '--')}",
                    "Offset candidates:",
                    *(f"  {candidate}" for candidate in payload.get("party_offset_candidates", [])),
                    "",
                )
            )
        if party_state.error:
            lines.append(
                f"{'Note' if party_state.party_count_valid else 'Error'}: {party_state.error}"
            )
        if party_state.candidate_count:
            lines.append(f"Scanned non-empty candidates: {party_state.candidate_count}")
        for pokemon in party_state.pokemon:
            diag = pokemon.decoded.diagnostics
            nickname = pokemon.decoded.nickname_diagnostics
            terminator = nickname.terminator_unit_index
            terminator_label = (
                f"unit {terminator} (field byte +0x{terminator * 2:02X})"
                if terminator is not None
                else "not present; decoded to field end"
            )
            lines.extend(
                (
                    f"Slot {pokemon.slot} - {pokemon.species}",
                    f"Address: {_format_optional_hex(diag.address)}",
                    f"PID: 0x{diag.pid:08X}",
                    (
                        f"Checksum: {'VALID' if pokemon.checksum_valid else 'INVALID'} "
                        f"(stored 0x{diag.checksum:04X}, calculated 0x{diag.calculated_checksum:04X})"
                    ),
                    f"Permutation: {diag.block_order} (index {diag.shuffle_index})",
                    f"Species ID: {pokemon.species_id}",
                    f"Held item ID: {pokemon.held_item_id}",
                    f"Held item name: {pokemon.held_item_name or 'None'}",
                    f"Held item sprite slug: {item_sprite_slug(pokemon.held_item_name) or '--'}",
                    f"Held item sprite path: {item_sprite_path(pokemon.held_item_name) or '--'}",
                    f"Held item sprite exists: {str(item_sprite_exists(pokemon.held_item_name)).lower()}",
                    f"Held item decrypted box-data offset: 0x{HELD_ITEM_BOX_DATA_OFFSET:02X}",
                    f"Held item party-record layout offset: 0x{HELD_ITEM_RECORD_OFFSET:02X}",
                    f"Nickname absolute address: {_format_optional_hex(nickname.absolute_address)}",
                    f"Nickname record-relative offset: 0x{nickname.record_relative_offset:02X}",
                    f"Nickname decrypted box-data offset: 0x{nickname.box_data_relative_offset:02X}",
                    f"Nickname raw bytes: {nickname.raw_bytes_hex}",
                    f"Nickname code units: {[f'0x{unit:04X}' for unit in nickname.code_units]}",
                    f"Nickname terminator: {terminator_label}",
                    f"Nickname decoded string: {nickname.decoded_string!r}",
                    f"Nickname final: {pokemon.nickname!r}",
                    f"Level: {pokemon.level if pokemon.level is not None else '--'}",
                    (
                        f"Current HP: {pokemon.current_hp if pokemon.current_hp is not None else '--'} / "
                        f"{pokemon.max_hp if pokemon.max_hp is not None else '--'}"
                    ),
                )
            )
            if pokemon.checksum_valid:
                lines.extend(
                    (
                        *(f"{stat}: {value}" for stat, value in pokemon.evs.items()),
                        f"Total EVs: {pokemon.ev_total}",
                        "",
                    )
                )
            else:
                lines.extend(("EVs withheld because checksum is invalid", ""))
        if not party_state.pokemon and not party_state.error:
            lines.append("No occupied party slots reported.")
        text = "\n".join(lines)
        if text != self.ram_party_details.toPlainText():
            self.ram_party_details.setPlainText(text)

    def closeEvent(self, event) -> None:
        self.refresh_timer.stop()
        self.ram_data_source.stop()
        self._save_window_state()
        super().closeEvent(event)
