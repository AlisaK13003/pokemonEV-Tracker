"""Compact live BizHawk status and detailed RAM diagnostic fields."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QLabel, QVBoxLayout, QWidget


class BackendStatusWidget(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.compact_label = QLabel("BizHawk RAM • DISCONNECTED")
        self.compact_label.setStyleSheet("font-size: 10px; color: #d18888; font-weight: 600;")
        layout.addWidget(self.compact_label)
        self.details = {}
        self.details_widget = QWidget()
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        for row, (key, caption, initial) in enumerate(
            (
                ("backend", "Backend", "BizHawk RAM"),
                ("connection", "Connection", "DISCONNECTED"),
                ("domain", "Memory domain", "--"),
                ("last_update", "Last update", "Never"),
                ("frame", "Frame", "--"),
            )
        ):
            value = QLabel(initial)
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.details[key] = value
            if key in {"domain", "last_update", "frame"}:
                grid.addWidget(QLabel(caption), row, 0)
                grid.addWidget(value, row, 1)
        self.details_widget.setLayout(grid)
        layout.addWidget(self.details_widget)

    def set_connection(self, backend: str, connected: bool, heartbeat, age: float | None) -> None:
        status = "CONNECTED" if connected else "DISCONNECTED"
        color = "#69d29b" if connected else "#e17b7b"
        self.compact_label.setText(f"{backend} • {status}")
        self.compact_label.setStyleSheet(f"font-size: 10px; color: {color}; font-weight: 600;")
        self.details["backend"].setText(backend)
        self.details["connection"].setText(status)
        self.details["connection"].setStyleSheet(f"color: {color}; font-weight: 600;")
        payload = heartbeat.payload if heartbeat is not None else {}
        self.details["domain"].setText(str(payload.get("active_domain") or "--"))
        self.details["frame"].setText(str(payload.get("frame", "--")))
        self.details["last_update"].setText(
            f"{age:.1f}s ago via {heartbeat.source}"
            if heartbeat is not None and age is not None
            else "Waiting for heartbeat"
            if connected
            else "Never"
        )
