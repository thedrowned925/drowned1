from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

import app_v4 as base
from drowned_shared.util import safe_windows_dir_name

APP_VERSION = "0.4.1"


class Launcher(base.Launcher):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Drowned Launcher {APP_VERSION}")

    def install_current_game(self):
        if not self.current_game:
            return

        game = self.current_game
        channel = self.current_channel
        data = (game.get("channels") or {}).get(channel) or {}
        display_title = str(game.get("title") or "Game")

        folder = QFileDialog.getExistingDirectory(
            self,
            f"{display_title} için kurulum klasörü",
        )
        if not folder:
            return

        manifest_url = data.get("manifest_url", "")
        if data.get("manifest_path"):
            manifest_url = base.raw_repo_url(
                self.owner,
                self.repo,
                self.branch,
                data["manifest_path"],
            )
        if not manifest_url:
            QMessageBox.critical(
                self,
                "Manifest hatası",
                "Bu yayın için manifest adresi bulunamadı.",
            )
            return

        safe_name = safe_windows_dir_name(
            display_title,
            fallback=str(game.get("id") or "Game"),
        )
        target = Path(folder) / safe_name

        self.progress.setValue(0)
        self.progress_text.setText("Hazırlanıyor")
        self.status.setText(f"{display_title} indiriliyor")
        self.logs.clear()
        self.logs.show()
        self.logs.appendPlainText(f"Kurulum klasörü: {target}")
        if safe_name != display_title:
            self.logs.appendPlainText(
                f"Windows için klasör adı güvenli hale getirildi: {safe_name}"
            )
        self.install_button.setEnabled(False)
        self.install_button.setText("İNDİRİLİYOR…")

        task = base.InstallTask(manifest_url, target)
        task.signals.progress.connect(self.install_progress)
        task.signals.log.connect(self.logs.appendPlainText)
        task.signals.done.connect(self.install_done)
        task.signals.error.connect(self.install_error)
        self.pool.start(task)


def main():
    base.install_exception_hook()
    app = QApplication(sys.argv)
    app.setApplicationName("Drowned Launcher")
    app.setOrganizationName("Drowned")
    app.setStyleSheet(base.STYLE)
    win = Launcher()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
