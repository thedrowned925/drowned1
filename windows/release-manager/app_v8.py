from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

import app_v7 as previous

APP_VERSION = "0.8.0"


class Manager(previous.Manager):
    """Release Manager v0.8 shell for the Direct Stream backend."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Drowned Release Manager {APP_VERSION} • Direct Stream")


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Drowned Release Manager")
    app.setOrganizationName("Drowned")
    app.setStyle("Fusion")
    app.setStyleSheet(previous.previous.previous.MODERN_STYLE)
    win = Manager()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
