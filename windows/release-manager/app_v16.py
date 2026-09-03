from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

import app_v15 as previous
import fdm_ui_v2


APP_VERSION = "0.16.0"

# v16 changes only how a URL is submitted to FDM and how the destination dialog
# is handled. Download telemetry, extraction, EXE detection, game test, cleanup
# and publishing stay on the existing v15/v14 pipeline.
fdm_ui_v2.install()


class Manager(previous.Manager):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(
            f"Drowned Release Manager {APP_VERSION} • FDM Add Download fixed"
        )
        if hasattr(self, "prep_connections"):
            self.prep_connections.setToolTip(
                "FDM bağlantı/segment ayarlarını kendi yönetir. Release Manager bu değeri zorlamaz."
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
