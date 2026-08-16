from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

import app_v3 as base
from drowned_shared.steam_artwork import SteamArtworkError, download_steam_artwork, parse_steam_app_id

APP_VERSION = "0.4.0"


class SteamArtworkWorker(QObject):
    done = Signal(object)
    error = Signal(str)

    def __init__(self, source: str, target_dir: Path):
        super().__init__()
        self.source = source
        self.target_dir = Path(target_dir)

    def run(self):
        try:
            self.done.emit(download_steam_artwork(self.source, self.target_dir))
        except Exception as exc:
            self.error.emit(str(exc))


class Manager(base.Manager):
    def __init__(self):
        self.steam_thread = None
        self.steam_worker = None
        self._steam_temp: tempfile.TemporaryDirectory | None = None
        self._steam_paths: set[str] = set()
        super().__init__()
        self.setWindowTitle(f"Drowned Release Manager {APP_VERSION}")

    def _publish_tab(self):
        widget = super()._publish_tab()
        root = widget.layout()

        card = QFrame()
        card.setObjectName("infoCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 13, 14, 13)
        layout.setSpacing(8)

        title = QLabel("SteamDB ile otomatik artwork")
        title.setStyleSheet("font-size:17px;font-weight:800;color:white")
        note = QLabel(
            "SteamDB oyun bağlantısını yapıştır. Release Manager yalnız AppID'yi çıkarır; "
            "Hero / Cover / Logo görsellerini Steam'in kendi store/CDN kaynaklarından indirir. "
            "Dosyalar sadece geçici tutulur ve başarılı yayından sonra bilgisayardan silinir."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color:#91a0b0;font-size:12px")

        row = QHBoxLayout()
        self.steamdb_url = QLineEdit()
        self.steamdb_url.setPlaceholderText("https://steamdb.info/app/620/")
        self.steam_fetch_button = QPushButton("Steam'den görselleri getir")
        self.steam_fetch_button.setObjectName("primary")
        self.steam_fetch_button.clicked.connect(self.fetch_steam_artwork)
        row.addWidget(self.steamdb_url, 1)
        row.addWidget(self.steam_fetch_button)

        self.steam_status = QLabel("SteamDB linki girilmedi.")
        self.steam_status.setWordWrap(True)
        self.steam_status.setStyleSheet("color:#708090;font-size:12px")

        layout.addWidget(title)
        layout.addWidget(note)
        layout.addLayout(row)
        layout.addWidget(self.steam_status)

        # Base order: title, subtitle, metadata form, artwork explainer, artwork row...
        root.insertWidget(3, card)
        return widget

    def _ensure_steam_temp(self) -> Path:
        if self._steam_temp is None:
            self._steam_temp = tempfile.TemporaryDirectory(prefix="drowned-steam-artwork-")
        return Path(self._steam_temp.name)

    def _cleanup_steam_temp(self, reset_previews: bool = False):
        old_paths = set(self._steam_paths)
        self._steam_paths.clear()
        if self._steam_temp is not None:
            try:
                self._steam_temp.cleanup()
            except Exception:
                try:
                    shutil.rmtree(self._steam_temp.name, ignore_errors=True)
                except Exception:
                    pass
            self._steam_temp = None

        for picker in (getattr(self, "hero", None), getattr(self, "cover", None), getattr(self, "logo", None)):
            if picker is None:
                continue
            if getattr(picker, "path", "") in old_paths:
                picker.path = ""
                if reset_previews:
                    picker.preview.clear()
                    picker.preview.setText("Steam artwork GitHub'a aktarıldı")

    @staticmethod
    def _apply_picker_path(picker, path: str):
        pix = QPixmap(path)
        if pix.isNull():
            return False
        picker.path = path
        picker.preview.clear()
        picker.preview.setPixmap(
            pix.scaled(
                max(picker.preview.width(), 300),
                max(picker.preview.height(), 135),
                Qt.KeepAspectRatioByExpanding,
                Qt.SmoothTransformation,
            )
        )
        return True

    def fetch_steam_artwork(self):
        value = self.steamdb_url.text().strip()
        try:
            app_id = parse_steam_app_id(value)
        except SteamArtworkError as exc:
            QMessageBox.warning(self, "SteamDB bağlantısı", str(exc))
            return

        if self.steam_thread is not None and self.steam_thread.isRunning():
            self.steam_status.setText("Steam artwork zaten indiriliyor…")
            return

        # Remove an earlier un-published Steam fetch before replacing it, so
        # repeated imports never build a local image cache.
        self._cleanup_steam_temp(reset_previews=False)
        target = self._ensure_steam_temp() / str(app_id)
        target.mkdir(parents=True, exist_ok=True)

        self.steam_fetch_button.setEnabled(False)
        self.steam_status.setText(f"Steam AppID {app_id} • Hero / Cover / Logo aranıyor…")

        self.steam_thread = QThread()
        self.steam_worker = SteamArtworkWorker(value, target)
        self.steam_worker.moveToThread(self.steam_thread)
        self.steam_thread.started.connect(self.steam_worker.run)
        self.steam_worker.done.connect(self._steam_artwork_done)
        self.steam_worker.error.connect(self._steam_artwork_error)
        self.steam_worker.done.connect(self.steam_thread.quit)
        self.steam_worker.error.connect(self.steam_thread.quit)
        self.steam_thread.finished.connect(self._steam_thread_finished)
        self.steam_thread.start()

    def _steam_thread_finished(self):
        self.steam_fetch_button.setEnabled(True)
        self.steam_worker = None
        self.steam_thread = None

    def _steam_artwork_done(self, result: dict):
        paths = result.get("paths") or {}
        applied = []
        for kind, picker in (("hero", self.hero), ("cover", self.cover), ("logo", self.logo)):
            path = str(paths.get(kind) or "")
            if path and self._apply_picker_path(picker, path):
                self._steam_paths.add(path)
                applied.append(kind.capitalize())

        if not self.game_title.text().strip() and result.get("name"):
            self.game_title.setText(str(result["name"]))
        if not self.description.toPlainText().strip() and result.get("description"):
            self.description.setPlainText(str(result["description"]))

        app_id = result.get("app_id")
        if applied:
            self.steam_status.setText(
                f"✓ Steam AppID {app_id} • " + ", ".join(applied) +
                " geçici olarak hazır. Yayın başarılı olunca yerel kopyalar otomatik silinecek."
            )
        else:
            self.steam_status.setText(f"Steam AppID {app_id} için uygun artwork bulunamadı.")

    def _steam_artwork_error(self, message: str):
        self._cleanup_steam_temp(reset_previews=False)
        self.steam_status.setText("Steam artwork alınamadı.")
        QMessageBox.warning(self, "Steam artwork", message)

    def on_done(self, tag):
        # base.PublishWorker only emits done after publish_project has uploaded
        # artwork to the repository, updated catalog metadata, and published the
        # Release. At this point the temporary Steam files are no longer needed.
        self._cleanup_steam_temp(reset_previews=True)
        if hasattr(self, "steam_status"):
            self.steam_status.setText(
                "✓ Artwork GitHub'a aktarıldı. Geçici yerel Steam görselleri silindi."
            )
        super().on_done(tag)

    def closeEvent(self, event):
        # Prevent abandoned imports from becoming a persistent local cache.
        self._cleanup_steam_temp(reset_previews=False)
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Drowned Release Manager")
    app.setOrganizationName("Drowned")
    app.setStyleSheet(base.STYLE)
    win = Manager()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
