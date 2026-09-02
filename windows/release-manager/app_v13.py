from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

import app_v12 as previous
import game_prepare as game_prepare_base
from game_download_v2 import ProgressiveParallelDownloader


APP_VERSION = "0.13.0"

# app_v11 imported prepare_game as a function, but that function resolves its
# ParallelDownloader global from the game_prepare module at call time. Replacing
# only that downloader keeps extraction, EXE detection, test flow, cleanup and
# publishing exactly as they were in v12.
game_prepare_base.ParallelDownloader = ProgressiveParallelDownloader


class Manager(previous.Manager):
    """v13 changes only the automated download transport.

    The default is tuned for a 1 Gbit connection: 16 concurrent HTTP Range
    workers. The visible .part file is progressive and is never preallocated to
    the final archive size.
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle(
            f"Drowned Release Manager {APP_VERSION} • Progressive 1 Gbit Download"
        )

        # 16 parallel Range requests is a good default for a 1 Gbit residential
        # connection without being as aggressive as 24/32 against host limits.
        if hasattr(self, "prep_connections"):
            index = self.prep_connections.findData(16)
            if index >= 0:
                self.prep_connections.setItemText(index, "1 Gbit önerilen (16)")
                self.prep_connections.setCurrentIndex(index)


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
