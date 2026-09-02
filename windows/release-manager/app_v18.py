from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

import app_v17 as previous
import fdm_submit_v4


APP_VERSION = "0.18.0"

# v18 replaces only the FDM URL submission layer. The URL is given directly to
# fdm.exe as a process argument and the resulting job is verified through FDM's
# own database. Download telemetry, extraction, EXE/game testing, cleanup and
# publishing are inherited unchanged.
fdm_submit_v4.install()


class Manager(previous.Manager):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(
            f"Drowned Release Manager {APP_VERSION} • FDM direct URL handoff"
        )


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Drowned Release Manager")
    app.setOrganizationName("Drowned")
    app.setStyle("Fusion")

    style_module = previous
    visited = set()
    while style_module and id(style_module) not in visited:
        visited.add(id(style_module))
        if hasattr(style_module, "MODERN_STYLE"):
            app.setStyleSheet(style_module.MODERN_STYLE)
            break
        style_module = getattr(style_module, "previous", None)

    win = Manager()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
