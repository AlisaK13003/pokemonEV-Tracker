"""EV change history list with compact and full-detail rendering."""

from __future__ import annotations

from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QHBoxLayout, QLabel, QListWidget, QPushButton, QVBoxLayout, QWidget


class EvChangeLogWidget(QWidget):
    def __init__(self, clear_callback, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("evChangeLog")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 8, 4, 4)
        layout.setSpacing(5)
        heading = QHBoxLayout()
        self.heading = QLabel("EV Change Log")
        self.heading.setProperty("uiRole", "sectionHeading")
        heading.addWidget(self.heading)
        heading.addStretch(1)
        self.clear_button = QPushButton("Clear Log")
        self.clear_button.setProperty("buttonRole", "danger")
        self.clear_button.clicked.connect(clear_callback)
        heading.addWidget(self.clear_button)
        layout.addLayout(heading)
        self.list = QListWidget()
        self.list.setObjectName("evChangeHistory")
        self.list.setUniformItemSizes(True)
        self.list.setMinimumHeight(150)
        self.list.setMaximumHeight(230)
        self.list.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.list.addItem("No EV changes recorded.")
        layout.addWidget(self.list)

    def render(self, records: list[tuple[str, str]], compact: bool) -> None:
        self.list.clear()
        visible = records[-4:] if compact else records
        if not visible:
            self.list.addItem("No EV changes recorded.")
        else:
            for full_text, compact_text in visible:
                self.list.addItem(compact_text if compact else full_text)
        self.list.scrollToBottom()
