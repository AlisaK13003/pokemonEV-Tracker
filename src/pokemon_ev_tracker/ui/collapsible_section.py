"""Small session-only collapsible section used by dense tracker cards."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QSizePolicy, QToolButton, QVBoxLayout, QWidget


class CollapsibleSection(QWidget):
    def __init__(
        self,
        title: str,
        content: QWidget,
        *,
        expanded: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("collapsibleSection")
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        self.content = content
        self.content.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
        )
        self.toggle = QToolButton(self)
        self.toggle.setObjectName("sectionToggle")
        self.toggle.setText(title)
        self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle.setArrowType(
            Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow
        )
        self.toggle.setCheckable(True)
        self.toggle.setChecked(expanded)
        self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle.toggled.connect(self._set_expanded)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 1, 0, 1)
        layout.setSpacing(2)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self.toggle)
        layout.addWidget(content)
        self._set_expanded(expanded)

    @property
    def is_expanded(self) -> bool:
        return self.toggle.isChecked()

    def minimumSizeHint(self):
        return self.layout().sizeHint()

    def _set_expanded(self, expanded: bool) -> None:
        self.toggle.setArrowType(
            Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow
        )
        self.content.setVisible(expanded)
        self.layout().invalidate()
        self.updateGeometry()
        parent = self.parentWidget()
        while parent is not None:
            parent.updateGeometry()
            if parent.layout() is not None:
                parent.layout().invalidate()
            parent = parent.parentWidget()
