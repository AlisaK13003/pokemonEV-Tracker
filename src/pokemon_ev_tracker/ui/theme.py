"""Central soft Pokédex theme for the PySide6 desktop interface."""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

COLORS = {
    "canvas": "#1c2225",
    "surface": "#242c30",
    "surface_raised": "#2b3439",
    "surface_card": "#303a3f",
    "surface_hover": "#38454a",
    "surface_input": "#1e2528",
    "border": "#465258",
    "border_soft": "#394449",
    "border_strong": "#58666b",
    "text": "#e8ece8",
    "text_secondary": "#bac5c2",
    "text_muted": "#91a09f",
    "text_dim": "#778685",
    "accent": "#91b9a4",
    "accent_hover": "#a2c9b3",
    "accent_deep": "#3d594d",
    "accent_border": "#668875",
    "accent_hover_surface": "#496b59",
    "success": "#91c19e",
    "warning": "#e3bd79",
    "danger": "#d9918e",
    "danger_surface": "#4b3435",
    "danger_border": "#725052",
    "danger_hover": "#5a3b3d",
    "recent_change": "#3b5145",
    "recent_change_border": "#4e6c5a",
    "nature_up": "#dfa0a0",
    "nature_down": "#91b6d1",
    "selection": "#40584c",
    "selection_text": "#f2f6f2",
    "progress_track": "#20282b",
    "table_alt": "#2a3337",
    "status_caught": "#365143",
    "status_caught_border": "#567663",
    "status_failed": "#493536",
    "status_failed_border": "#705052",
    "status_dead": "#503638",
    "status_dead_border": "#795052",
    "status_skipped": "#353e42",
    "status_dupes": "#3b4142",
}

METRICS = {
    "radius_small": "4px",
    "radius_medium": "6px",
    "radius_card": "8px",
    "control_padding": "6px 10px",
}

_TOKENS = {**COLORS, **METRICS}

_STYLESHEET = """
QMainWindow, QWidget {
    background-color: $canvas;
    color: $text;
    font-family: "Segoe UI", "Noto Sans", sans-serif;
    font-size: 9pt;
}
QMainWindow { background-color: $canvas; }
QWidget#appRoot, QWidget#trackerPage, QWidget#ramDebugPage { background: $canvas; }
QWidget#applicationToolbar {
    background: $surface;
    border: 1px solid $border_soft;
    border-radius: $radius_card;
}
QLabel { background: transparent; }
QLabel#applicationTitle {
    color: $text;
    font-size: 16pt;
    font-weight: 650;
}
QLabel[uiRole="sectionHeading"] {
    color: $accent;
    font-size: 11pt;
    font-weight: 650;
    padding: 2px 0;
}
QLabel[uiRole="pokemonName"] {
    color: $text;
    font-size: 10pt;
    font-weight: 650;
}
QLabel[uiRole="pokemonMeta"] { color: $text_secondary; font-weight: 600; }
QLabel[uiRole="muted"] { color: $text_secondary; }
QLabel[uiRole="small"] { color: $text_secondary; font-size: 8pt; }
QLabel[uiRole="micro"] { color: $text_muted; font-size: 7.5pt; }
QLabel[uiRole="heldItem"] { color: $text; }
QLabel[uiRole="tableHeader"] { color: $text_muted; font-size: 8pt; font-weight: 650; }
QLabel[uiRole="emptyState"] { color: $text_muted; font-style: italic; padding: 5px; }
QLabel[uiRole="sprite"] {
    background: $surface_raised;
    border: 1px solid $border_soft;
    border-radius: $radius_medium;
}

QTabWidget::pane {
    background: $canvas;
    border: 1px solid $border_soft;
    border-radius: $radius_card;
    top: -1px;
}
QTabBar::tab {
    background: $surface;
    color: $text_secondary;
    border: 1px solid $border_soft;
    border-bottom: 2px solid transparent;
    padding: 7px 14px;
    margin-right: 4px;
    border-top-left-radius: $radius_medium;
    border-top-right-radius: $radius_medium;
}
QTabBar::tab:selected {
    background: $surface_raised;
    color: $text;
    border-bottom-color: $accent;
}
QTabBar::tab:hover:!selected { background: $surface_hover; color: $text; }
QTabBar::tab:disabled { color: $text_dim; }

QPushButton, QToolButton {
    background: $surface_raised;
    color: $text;
    border: 1px solid $border;
    border-radius: $radius_medium;
    padding: $control_padding;
    font-weight: 550;
}
QPushButton:hover, QToolButton:hover {
    background: $surface_hover;
    border-color: $border_strong;
}
QPushButton:pressed, QToolButton:pressed {
    background: $surface;
    border-color: $accent_border;
}
QPushButton:disabled, QToolButton:disabled {
    color: $text_dim;
    background: $surface;
    border-color: $border_soft;
}
QPushButton:default, QPushButton[buttonRole="primary"] {
    background: $accent_deep;
    border-color: $accent_border;
    color: $text;
}
QPushButton:default:hover, QPushButton[buttonRole="primary"]:hover {
    background: $accent_hover_surface;
    border-color: $accent;
}
QPushButton[buttonRole="danger"] {
    background: $danger_surface;
    border-color: $danger_border;
}
QPushButton[buttonRole="danger"]:hover {
    background: $danger_hover;
    border-color: $danger;
}
QPushButton[buttonRole="segmented"] { border-radius: $radius_small; }
QPushButton[buttonRole="segmented"]:checked {
    background: $accent_deep;
    border-color: $accent_border;
    color: $text;
}
QPushButton[buttonRole="compactToggle"]:checked {
    background: $accent_deep;
    border-color: $accent_border;
}

QGroupBox {
    background: $surface;
    border: 1px solid $border_soft;
    border-radius: $radius_card;
    margin-top: 12px;
    padding: 10px 8px 7px;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 1px 6px;
    color: $text_secondary;
    background: $surface;
}
QGroupBox#currentlyBattling { background: $surface; border-color: $border; }
QGroupBox#nextLevelCap { background: $surface_raised; }

QFrame#partyCard, QWidget[uiRole="opponentCard"] {
    background: $surface_card;
    border: 1px solid $border;
    border-radius: $radius_card;
}
QFrame#partyCard:hover { border-color: $border_strong; }
QWidget[uiRole="evRow"] {
    background: $surface_raised;
    border: 1px solid transparent;
    border-radius: $radius_small;
}
QWidget[recentChange="true"] {
    background: $recent_change;
    border: 1px solid $recent_change_border;
    border-radius: $radius_small;
}
QFrame#partyCard[cardSize="small"] { border-color: $border_soft; }
QFrame#partyCard[cardSize="large"] { border-color: $border_strong; }
QWidget#friendshipWalk {
    background: $surface;
    border: 1px solid $border_soft;
    border-radius: $radius_card;
    padding: 3px;
}
QWidget#evChangeLog {
    background: $surface;
    border: 1px solid $border_soft;
    border-radius: $radius_card;
}
QListWidget#evChangeHistory {
    background: $surface_input;
    alternate-background-color: $table_alt;
    border: 1px solid $border_soft;
    border-radius: $radius_medium;
    padding: 5px;
}
QListWidget#evChangeHistory::item { padding: 4px 6px; border-radius: $radius_small; }
QListWidget#evChangeHistory::item:selected {
    background: $selection;
    color: $selection_text;
}

QToolButton#sectionToggle {
    background: transparent;
    color: $text_secondary;
    border: 1px solid transparent;
    border-left: 2px solid transparent;
    border-radius: $radius_small;
    padding: 5px 7px;
    text-align: left;
    font-weight: 600;
}
QToolButton#sectionToggle:hover {
    background: $surface_raised;
    color: $text;
}
QToolButton#sectionToggle:checked {
    background: $surface_raised;
    color: $accent_hover;
    border-left-color: $accent;
}

QLabel[natureRole="up"] { color: $nature_up; font-weight: 600; }
QLabel[natureRole="down"] { color: $nature_down; font-weight: 600; }
QLabel[natureRole="neutral"] { color: $text_secondary; }
QLabel[targetSeverity="warning"] { color: $danger; font-weight: 600; }
QLabel[targetSeverity="normal"] { color: $text_secondary; }
QLabel[ramState="valid"] { color: $success; }
QLabel[ramState="warning"] { color: $warning; }
QLabel[ramState="invalid"] { color: $danger; font-weight: 600; }
QLabel[statusRole="warning"] { color: $warning; }
QLabel[statusRole="error"] { color: $danger; }
QLabel[statusRole="connected"] { color: $success; }
QLabel[statusRole="info"] { color: $text_secondary; }
QLabel[walkState="active"] { color: $success; font-weight: 600; }
QLabel[walkState="pending"], QLabel[walkState="paused"] { color: $warning; font-weight: 600; }
QLabel[connectionState="connected"] { color: $success; font-weight: 600; }
QLabel[connectionState="disconnected"] { color: $danger; font-weight: 600; }

QProgressBar {
    background: $progress_track;
    border: 1px solid $border_soft;
    border-radius: 4px;
    min-height: 5px;
    max-height: 10px;
}
QProgressBar::chunk { background: $accent; border-radius: 3px; }

QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox {
    background: $surface_input;
    color: $text;
    border: 1px solid $border;
    border-radius: $radius_small;
    padding: 5px 7px;
    selection-background-color: $selection;
    selection-color: $selection_text;
}
QLineEdit:hover, QTextEdit:hover, QPlainTextEdit:hover, QComboBox:hover, QSpinBox:hover {
    border-color: $border_strong;
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus {
    border-color: $accent_border;
}
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView {
    background: $surface_raised;
    color: $text;
    border: 1px solid $border;
    selection-background-color: $selection;
}
QCheckBox { spacing: 7px; color: $text_secondary; }
QCheckBox::indicator {
    width: 15px;
    height: 15px;
    background: $surface_input;
    border: 1px solid $border_strong;
    border-radius: 4px;
}
QCheckBox::indicator:checked { background: $accent_deep; border-color: $accent; }

QTableWidget {
    background: $surface_input;
    alternate-background-color: $table_alt;
    color: $text;
    gridline-color: $border_soft;
    border: 1px solid $border_soft;
    border-radius: $radius_medium;
    selection-background-color: $selection;
    selection-color: $selection_text;
    outline: 0;
}
QTableWidget::item { padding: 4px 6px; border: none; }
QTableWidget::item:hover { background: $surface_hover; }
QHeaderView::section {
    background: $surface_raised;
    color: $text_secondary;
    border: none;
    border-right: 1px solid $border_soft;
    border-bottom: 1px solid $border;
    padding: 7px 8px;
    font-weight: 650;
}
QTableCornerButton::section { background: $surface_raised; border: none; }

QScrollArea { border: none; background: transparent; }
QScrollBar:vertical { background: $canvas; width: 10px; margin: 2px; }
QScrollBar::handle:vertical {
    background: $border_strong;
    min-height: 26px;
    border-radius: 4px;
}
QScrollBar::handle:vertical:hover { background: $text_muted; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { background: $canvas; height: 10px; margin: 2px; }
QScrollBar::handle:horizontal {
    background: $border_strong;
    min-width: 26px;
    border-radius: 4px;
}
QScrollBar::handle:horizontal:hover { background: $text_muted; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

QStatusBar#statusBar {
    background: $surface;
    color: $text_secondary;
    border-top: 1px solid $border_soft;
}
QStatusBar::item { border: none; }
QLabel#nuzlockeEmpty { color: $text_muted; padding: 24px; }
QLabel[nuzlockeRole="capTitle"] { color: $text; font-size: 12pt; font-weight: 650; }
QLabel[nuzlockeRole="muted"] { color: $text_muted; font-size: 8pt; }
QLabel[nuzlockeRole="warning"] { color: $warning; }
QLabel[nuzlockeRole="summary"] { color: $text_secondary; }
QComboBox[encounterStatus="CAUGHT"] {
    background: $status_caught;
    border-color: $status_caught_border;
}
QComboBox[encounterStatus="FAILED"] {
    background: $status_failed;
    border-color: $status_failed_border;
}
QComboBox[encounterStatus="DEAD"] {
    background: $status_dead;
    border-color: $status_dead_border;
}
QComboBox[encounterStatus="SKIPPED"] { background: $status_skipped; }
QComboBox[encounterStatus="DUPES"] { background: $status_dupes; }
"""

APP_STYLESHEET = _STYLESHEET
for _token, _value in sorted(_TOKENS.items(), key=lambda item: len(item[0]), reverse=True):
    APP_STYLESHEET = APP_STYLESHEET.replace(f"${_token}", _value)


def apply_theme(widget: QWidget) -> None:
    widget.setStyleSheet(APP_STYLESHEET)


def refresh_style(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)
