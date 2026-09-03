from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QFileDialog, QHBoxLayout, QLineEdit, QPushButton, QWidget

import app_v14 as previous
import fdm_bridge


APP_VERSION = "0.15.0"
SETTING_FDM_PATH = "automation/fdm_path"


class Manager(previous.Manager):
    """v15 adds robust custom FDM executable discovery/configuration.

    FDM can be installed anywhere (for example F:\\fdm\\fdm.exe). The selected
    path is persisted and fed to the FDM bridge before the preparation pipeline
    starts. The bridge also auto-detects a currently running fdm.exe process.
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle(
            f"Drowned Release Manager {APP_VERSION} • FDM custom path + telemetry"
        )
        self._fdm_settings = QSettings("Drowned", "Drowned Release Manager")
        self._install_fdm_path_row()
        self._load_fdm_path()

    def _install_fdm_path_row(self):
        if not hasattr(self, "prep_title"):
            return
        form = self.prep_title.parentWidget().layout()
        if form is None:
            return

        self.prep_fdm_path = QLineEdit()
        self.prep_fdm_path.setPlaceholderText(r"Otomatik algıla veya örn. F:\fdm\fdm.exe")
        self.prep_fdm_path.setClearButtonEnabled(True)
        self.prep_fdm_browse = QPushButton("FDM seç")
        self.prep_fdm_browse.clicked.connect(self._browse_fdm_executable)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.prep_fdm_path, 1)
        row.addWidget(self.prep_fdm_browse)
        holder = QWidget()
        holder.setLayout(row)

        # Place this after Steam App ID and before URL controls where possible.
        try:
            form.insertRow(2, "FDM yolu", holder)
        except Exception:
            form.addRow("FDM yolu", holder)

    def _load_fdm_path(self):
        value = str(self._fdm_settings.value(SETTING_FDM_PATH, "") or "").strip()
        if value and Path(value).is_file():
            self.prep_fdm_path.setText(value)
            fdm_bridge.set_fdm_override(value)
            return
        detected = fdm_bridge.find_fdm_executable()
        if detected:
            self.prep_fdm_path.setText(str(detected))
            fdm_bridge.set_fdm_override(str(detected))

    def _browse_fdm_executable(self):
        start = self.prep_fdm_path.text().strip() or os.environ.get("ProgramFiles", "C:\\")
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Free Download Manager executable seç",
            start,
            "Free Download Manager (fdm.exe);;Uygulamalar (*.exe);;Tüm dosyalar (*)",
        )
        if not path:
            return
        self.prep_fdm_path.setText(path)
        self._save_and_apply_fdm_path()

    def _save_and_apply_fdm_path(self) -> bool:
        raw = self.prep_fdm_path.text().strip()
        if raw:
            candidate = Path(raw).expanduser()
            if not candidate.is_file() or candidate.name.lower() != "fdm.exe":
                from PySide6.QtWidgets import QMessageBox

                QMessageBox.warning(
                    self,
                    "FDM yolu",
                    "Geçerli bir fdm.exe seç. Örnek: F:\\fdm\\fdm.exe",
                )
                return False
            resolved = str(candidate.resolve())
            self.prep_fdm_path.setText(resolved)
            self._fdm_settings.setValue(SETTING_FDM_PATH, resolved)
            fdm_bridge.set_fdm_override(resolved)
            return True

        self._fdm_settings.remove(SETTING_FDM_PATH)
        fdm_bridge.set_fdm_override(None)
        detected = fdm_bridge.find_fdm_executable()
        if detected:
            self.prep_fdm_path.setText(str(detected))
            fdm_bridge.set_fdm_override(str(detected))
            return True
        return True

    def start_preparation(self):
        if not self._save_and_apply_fdm_path():
            return
        super().start_preparation()


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
