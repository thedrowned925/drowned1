from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QBoxLayout,
    QFrame,
    QLayout,
    QScrollArea,
    QSizePolicy,
)

import app_v6 as previous

APP_VERSION = "0.7.0"


class Manager(previous.Manager):
    """Responsive shell for the v0.6 Release Manager.

    No publishing, chunking, Steam artwork, deletion or telemetry behaviour is
    changed here. This class only changes how the existing publish page is laid
    out when the window is shorter/narrower than the full content.
    """

    def __init__(self):
        self._publish_content = None
        self._artwork_row = None
        self._extras_row = None
        super().__init__()
        self.setWindowTitle(f"Drowned Release Manager {APP_VERSION}")
        self.resize(1280, 860)
        self.setMinimumSize(860, 620)

    @staticmethod
    def _layout_containing(layout, widgets):
        wanted = set(widgets)
        if layout is None:
            return None
        direct = {
            layout.itemAt(i).widget()
            for i in range(layout.count())
            if layout.itemAt(i) is not None and layout.itemAt(i).widget() is not None
        }
        if wanted.issubset(direct):
            return layout
        for i in range(layout.count()):
            item = layout.itemAt(i)
            child = item.layout() if item is not None else None
            found = Manager._layout_containing(child, widgets)
            if found is not None:
                return found
            widget = item.widget() if item is not None else None
            if widget is not None and widget.layout() is not None:
                found = Manager._layout_containing(widget.layout(), widgets)
                if found is not None:
                    return found
        return None

    def _publish_tab(self):
        content = super()._publish_tab()
        self._publish_content = content

        root = content.layout()
        root.setContentsMargins(14, 14, 14, 26)
        root.setSpacing(12)
        # This is the key difference from the old page: the layout keeps its
        # natural minimum height instead of compressing every card/table to fit
        # into one viewport. QScrollArea handles the overflow vertically.
        root.setSizeConstraint(QLayout.SetMinimumSize)

        content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        # Give the live telemetry enough height to actually show its rows. The
        # v0.6 panel used a fixed 235 px table which became visually crushed by
        # the non-scrollable parent page.
        self.upload_monitor.table.setMinimumHeight(300)
        self.upload_monitor.table.setMaximumHeight(360)
        self.logs.setMinimumHeight(155)
        self.logs.setMaximumHeight(220)

        # Keep the wide desktop composition, but allow the two multi-card rows
        # to stack when the viewport gets narrow.
        self._artwork_row = self._layout_containing(
            root,
            (self.hero, self.cover, self.logo),
        )
        self._extras_row = self._layout_containing(
            root,
            (self.icon, self.trailer_panel),
        )

        scroll = QScrollArea()
        scroll.setObjectName("publishScroll")
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setAlignment(Qt.AlignTop)
        scroll.setWidget(content)

        # Avoid the thick default frame/viewport treatment; the page should
        # still look like the existing Steam-style surface.
        scroll.setStyleSheet(
            "QScrollArea#publishScroll { border: 0; background: #1b2838; }"
            "QScrollArea#publishScroll > QWidget > QWidget { background: #1b2838; }"
            "QScrollBar:vertical { background:#16202d; width:12px; margin:0; }"
            "QScrollBar::handle:vertical { background:#34516c; min-height:42px; }"
            "QScrollBar::handle:vertical:hover { background:#4a7396; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }"
            "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background:transparent; }"
        )

        self._apply_responsive_layout(1280)
        return scroll

    def _apply_responsive_layout(self, width: int):
        narrow = width < 1040
        very_narrow = width < 900

        if isinstance(self._artwork_row, QBoxLayout):
            self._artwork_row.setDirection(
                QBoxLayout.TopToBottom if narrow else QBoxLayout.LeftToRight
            )
            self._artwork_row.setSpacing(10 if narrow else 12)

        if isinstance(self._extras_row, QBoxLayout):
            self._extras_row.setDirection(
                QBoxLayout.TopToBottom if very_narrow else QBoxLayout.LeftToRight
            )
            self._extras_row.setSpacing(10 if very_narrow else 12)

        if self._publish_content is not None:
            # Prevent giant empty previews in stacked mode while still leaving
            # enough room to see the artwork clearly.
            preview_height = 145 if narrow else 135
            for picker in (self.hero, self.cover, self.logo):
                picker.preview.setMinimumHeight(preview_height)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_responsive_layout(event.size().width())


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Drowned Release Manager")
    app.setOrganizationName("Drowned")
    app.setStyle("Fusion")
    app.setStyleSheet(previous.previous.MODERN_STYLE)
    win = Manager()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
