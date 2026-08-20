from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication, QFileDialog, QLabel

import app_v8 as previous
from drowned_shared.chunking import ChunkBuilder
from drowned_shared.constants import CHUNK_SIZE_MIB, MAX_DATA_ASSETS, MAX_RELEASE_DATA_BYTES
from drowned_shared.turbo_upload import choose_upload_plan
from drowned_shared.util import format_bytes

APP_VERSION = "0.9.0"


class Manager(previous.Manager):
    """Release Manager v0.9 shell for Balanced Direct Stream uploads."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Drowned Release Manager {APP_VERSION} • Balanced Direct Stream")

        # The original publish page labels the protocol with one fixed chunk
        # size. v0.9 is adaptive, so replace that subtitle without changing the
        # rest of the inherited responsive UI.
        for label in self.findChildren(QLabel):
            text = label.text()
            if "RAR/ZIP yok" in text and "streaming chunk" in text:
                label.setText(
                    f"RAR/ZIP yok • Balanced Direct Stream • 64 MiB–{CHUNK_SIZE_MIB} MiB adaptif chunk • "
                    "40–64 stream • yayın tamamlanana kadar Release draft kalır"
                )
                break

    def pick_source(self):
        path = QFileDialog.getExistingDirectory(self, "Kaynak klasörü")
        if not path:
            return

        self.source.setText(path)
        probe = ChunkBuilder(Path(path))
        plan = choose_upload_plan(probe.total_size)
        chunk_count = int(plan["chunk_count"])
        workers = int(plan["workers"])
        waves = int(plan["waves"])
        chunk_size = int(plan["chunk_size"])
        status = "✓ Tek Release'e sığıyor" if chunk_count <= MAX_DATA_ASSETS else "⚠ Tek Release'e sığmıyor"

        wave_text = "tek dalga" if waves == 1 else f"{waves} tam dalga"
        self.plan.setText(
            f"<b>{status}</b><br>"
            f"Kaynak: {format_bytes(probe.total_size)} • Chunk: {chunk_count}/{MAX_DATA_ASSETS} • "
            f"Hedef chunk: {format_bytes(chunk_size)}<br>"
            f"Balanced plan: <b>{workers} paralel stream × {wave_text}</b> • "
            f"Maksimum chunk: {CHUNK_SIZE_MIB} MiB • Temp BIN: 0 B<br>"
            f"Tek Release veri tavanı: {format_bytes(MAX_RELEASE_DATA_BYTES)}"
        )


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Drowned Release Manager")
    app.setOrganizationName("Drowned")
    app.setStyle("Fusion")
    app.setStyleSheet(previous.previous.previous.previous.MODERN_STYLE)
    win = Manager()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
