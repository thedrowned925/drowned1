from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

import app_v13 as previous
import game_prepare as game_prepare_base
from fdm_bridge import FdmDownloader, find_fdm_database, find_fdm_executable


APP_VERSION = "0.14.0"

# v14 changes only the transport backend again. Everything after download
# (archive extraction, EXE detection, test gates, cleanup and publish) remains
# inherited from v11-v13.
game_prepare_base.ParallelDownloader = FdmDownloader


class Manager(previous.Manager):
    """Release Manager v14: FDM transport + FDM database telemetry."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(
            f"Drowned Release Manager {APP_VERSION} • FDM Download Engine + Live Telemetry"
        )
        if hasattr(self, "prep_connections"):
            self.prep_connections.clear()
            self.prep_connections.addItem("FDM tarafından yönetiliyor", 0)
            self.prep_connections.setEnabled(False)
        if hasattr(self, "prepare_button"):
            self.prepare_button.setText("FDM İLE İNDİR + ÇIKART + EXE BUL + OYUNU AÇ")
        if hasattr(self, "prep_logs"):
            fdm = find_fdm_executable()
            database = find_fdm_database()
            self.prep_logs.appendPlainText(
                "FDM motoru: " + (str(fdm) if fdm else "bulunamadı • FDM 6.x kurulu olmalı")
            )
            if database:
                self.prep_logs.appendPlainText(f"FDM telemetry DB: {database}")


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
