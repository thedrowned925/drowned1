from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Signal
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

import app_v4 as base
import app_v5 as previous
from drowned_shared.install import fetch_json, repair_manifest
from drowned_shared.util import atomic_json, format_bytes, safe_windows_dir_name

APP_VERSION = "0.5.0"
REGISTRY_SCHEMA = 1


def registry_path() -> Path:
    return base.app_data_dir() / "installed_games.json"


def load_registry() -> dict:
    path = registry_path()
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if value.get("schema_version") == REGISTRY_SCHEMA and isinstance(value.get("games"), dict):
            return value
    except Exception:
        pass
    return {"schema_version": REGISTRY_SCHEMA, "games": {}}


def save_registry(value: dict) -> None:
    atomic_json(registry_path(), value)


def installation_key(owner: str, repo: str, game: dict, channel: str) -> str:
    return "|".join(
        [
            owner.lower(),
            repo.lower(),
            str(game.get("id") or "").lower(),
            str(game.get("platform") or "").lower(),
            channel.lower(),
        ]
    )


class RepairSignals(QObject):
    progress = Signal(int, str)
    log = Signal(str)
    done = Signal(object)
    error = Signal(str)


class RepairTask(QRunnable):
    def __init__(self, manifest_url: str, target: Path):
        super().__init__()
        self.manifest_url = manifest_url
        self.target = Path(target)
        self.signals = RepairSignals()

    def run(self):
        try:
            manifest = None
            last_error = None
            for delay in (0.0, 0.7, 1.5, 3.0):
                if delay:
                    time.sleep(delay)
                try:
                    manifest = fetch_json(base.cache_bust(self.manifest_url))
                    break
                except Exception as exc:
                    last_error = exc
            if manifest is None:
                raise RuntimeError(f"Manifest alınamadı: {last_error}")

            def report(done: int, total: int):
                percent = int(done * 100 / max(total, 1))
                self.signals.progress.emit(
                    max(0, min(percent, 100)),
                    f"{format_bytes(done)} / {format_bytes(total)}",
                )

            result = repair_manifest(
                manifest,
                self.target,
                progress=report,
                log=self.signals.log.emit,
                cancelled=lambda: False,
            )
            self.signals.done.emit(result)
        except Exception as exc:
            self.signals.error.emit(str(exc))


class Launcher(previous.Launcher):
    def __init__(self):
        self.install_registry = load_registry()
        self._active_install_context = None
        self._active_repair_key = None
        super().__init__()
        self.setWindowTitle(f"Drowned Launcher {APP_VERSION}")
        self.verify_button.clicked.connect(self.verify_current_game)

    def _key(self, game: dict, channel: str) -> str:
        return installation_key(self.owner, self.repo, game, channel)

    def _record(self, game: dict | None = None, channel: str | None = None) -> dict | None:
        game = game or self.current_game
        channel = channel or self.current_channel
        if not game:
            return None
        return self.install_registry.get("games", {}).get(self._key(game, channel))

    def _record_path_exists(self, record: dict | None) -> bool:
        if not record:
            return False
        try:
            return Path(record.get("install_path", "")).is_dir()
        except Exception:
            return False

    def _manifest_url(self, data: dict, owner: str | None = None, repo: str | None = None, branch: str | None = None) -> str:
        if data.get("manifest_path"):
            return base.raw_repo_url(
                owner or self.owner,
                repo or self.repo,
                branch or self.branch,
                data["manifest_path"],
            )
        return str(data.get("manifest_url") or "")

    def render_library(self):
        super().render_library()
        if not hasattr(self, "library"):
            return
        for row in range(self.library.count()):
            item = self.library.item(row)
            payload = item.data(base.Qt.UserRole)
            if not payload:
                continue
            game, channel = payload
            record = self._record(game, channel)
            if record and self._record_path_exists(record):
                text = item.text()
                if not text.startswith("● "):
                    item.setText("● " + text)

    def library_selection_changed(self, current, previous_item):
        super().library_selection_changed(current, previous_item)
        self.update_install_state_ui()

    def update_install_state_ui(self):
        if not self.current_game:
            return
        data = (self.current_game.get("channels") or {}).get(self.current_channel) or {}
        record = self._record()
        if record and self._record_path_exists(record):
            installed_tag = str(record.get("tag") or "")
            current_tag = str(data.get("tag") or "")
            installed_version = str(record.get("version") or "?")
            self.verify_button.setEnabled(True)
            if installed_tag and installed_tag == current_tag:
                self.install_button.setText("YÜKLÜ")
                self.install_button.setEnabled(False)
                self.status.setText(
                    f"Kurulu • v{installed_version} • {record.get('install_path')}"
                )
            else:
                self.install_button.setText("GÜNCELLE")
                self.install_button.setEnabled(True)
                self.status.setText(
                    f"Güncelleme mevcut • kurulu v{installed_version} → v{data.get('version','?')}"
                )
        elif record:
            self.verify_button.setEnabled(False)
            self.install_button.setText("YENİDEN YÜKLE")
            self.install_button.setEnabled(True)
            self.status.setText(
                f"Kayıtlı kurulum yolu bulunamadı: {record.get('install_path','?')}"
            )
        else:
            self.verify_button.setEnabled(False)
            self.install_button.setText("YÜKLE")
            self.install_button.setEnabled(True)

    def install_current_game(self):
        if not self.current_game:
            return

        game = self.current_game
        channel = self.current_channel
        data = (game.get("channels") or {}).get(channel) or {}
        display_title = str(game.get("title") or "Game")
        record = self._record(game, channel)

        manifest_url = self._manifest_url(data)
        if not manifest_url:
            QMessageBox.critical(
                self,
                "Manifest hatası",
                "Bu yayın için manifest adresi bulunamadı.",
            )
            return

        if record and self._record_path_exists(record):
            target = Path(record["install_path"])
        else:
            folder = QFileDialog.getExistingDirectory(
                self,
                f"{display_title} için kurulum klasörü",
            )
            if not folder:
                return
            safe_name = safe_windows_dir_name(
                display_title,
                fallback=str(game.get("id") or "Game"),
            )
            target = Path(folder) / safe_name

        self._active_install_context = {
            "key": self._key(game, channel),
            "title": display_title,
            "game_id": str(game.get("id") or ""),
            "platform": str(game.get("platform") or ""),
            "channel": channel,
            "version": str(data.get("version") or ""),
            "tag": str(data.get("tag") or ""),
            "manifest_url": manifest_url,
            "manifest_path": str(data.get("manifest_path") or ""),
            "owner": self.owner,
            "repo": self.repo,
            "branch": self.branch,
            "install_path": str(target),
        }

        self.progress.setValue(0)
        self.progress_text.setText("Hazırlanıyor")
        self.status.setText(f"{display_title} indiriliyor / doğrulanıyor")
        self.logs.clear()
        self.logs.show()
        self.logs.appendPlainText(f"Kurulum klasörü: {target}")
        if (target / ".drowned" / "state.json").exists():
            self.logs.appendPlainText(
                "Mevcut Drowned kurulumu bulundu; eksik/bozuk veriler kontrol edilecek."
            )
        self.install_button.setEnabled(False)
        self.verify_button.setEnabled(False)
        self.install_button.setText("İŞLENİYOR…")

        task = base.InstallTask(manifest_url, target)
        task.signals.progress.connect(self.install_progress)
        task.signals.log.connect(self.logs.appendPlainText)
        task.signals.done.connect(self.install_done)
        task.signals.error.connect(self.install_error)
        self.pool.start(task)

    def install_done(self):
        context = self._active_install_context
        if context:
            record = dict(context)
            record["installed_at"] = datetime.now(timezone.utc).isoformat()
            record["verified_at"] = record["installed_at"]
            self.install_registry.setdefault("games", {})[context["key"]] = record
            save_registry(self.install_registry)

        self.progress.setValue(100)
        self.progress_text.setText("%100 • doğrulandı")
        self.status.setText("Kurulum tamamlandı ve kaydedildi")
        self.install_button.setEnabled(True)
        self._active_install_context = None
        self.render_library()
        self.update_install_state_ui()
        QMessageBox.information(
            self,
            "Tamamlandı",
            "Kurulum ve SHA-256 doğrulaması tamamlandı.\n\n"
            "Bu oyun artık Launcher yeniden açıldığında da kurulu olarak hatırlanacak.",
        )

    def install_error(self, message: str):
        self._active_install_context = None
        super().install_error(message)
        self.update_install_state_ui()

    def verify_current_game(self):
        if not self.current_game:
            return
        record = self._record()
        if not record:
            QMessageBox.information(self, "Kurulu değil", "Bu oyun için kayıtlı bir kurulum bulunamadı.")
            return
        target = Path(record.get("install_path", ""))
        if not target.is_dir():
            QMessageBox.warning(
                self,
                "Kurulum yolu bulunamadı",
                f"Kayıtlı klasör artık mevcut değil:\n{target}",
            )
            self.update_install_state_ui()
            return

        manifest_url = str(record.get("manifest_url") or "")
        if record.get("manifest_path"):
            manifest_url = base.raw_repo_url(
                str(record.get("owner") or self.owner),
                str(record.get("repo") or self.repo),
                str(record.get("branch") or self.branch),
                str(record["manifest_path"]),
            )
        if not manifest_url:
            QMessageBox.critical(self, "Manifest hatası", "Kurulu sürümün manifest adresi bulunamadı.")
            return

        self._active_repair_key = self._key(self.current_game, self.current_channel)
        self.progress.setValue(0)
        self.progress_text.setText("Doğrulanıyor…")
        self.status.setText("Dosyalar doğrulanıyor")
        self.logs.clear()
        self.logs.show()
        self.logs.appendPlainText(f"Kurulum: {target}")
        self.logs.appendPlainText("Eksik veya değiştirilmiş dosyalar SHA-256 ile aranıyor…")
        self.install_button.setEnabled(False)
        self.verify_button.setEnabled(False)
        self.verify_button.setText("DOĞRULANIYOR…")

        task = RepairTask(manifest_url, target)
        task.signals.progress.connect(self.install_progress)
        task.signals.log.connect(self.logs.appendPlainText)
        task.signals.done.connect(self.repair_done)
        task.signals.error.connect(self.repair_error)
        self.pool.start(task)

    def repair_done(self, result: dict):
        repaired = list(result.get("repaired_files") or [])
        chunks = int(result.get("downloaded_chunks") or 0)
        key = self._active_repair_key
        if key and key in self.install_registry.get("games", {}):
            self.install_registry["games"][key]["verified_at"] = datetime.now(timezone.utc).isoformat()
            save_registry(self.install_registry)
        self._active_repair_key = None

        self.progress.setValue(100)
        self.progress_text.setText("%100 • doğrulandı")
        if repaired:
            self.status.setText(f"Onarım tamamlandı • {len(repaired)} dosya")
            message = (
                f"{len(repaired)} eksik/bozuk dosya bulundu ve onarıldı.\n"
                f"Yeniden indirilen chunk: {chunks}"
            )
        else:
            self.status.setText("Tüm dosyalar sağlam")
            message = "Tüm dosyalar manifest ile birebir eşleşiyor. Onarım gerekmedi."
        self.verify_button.setText("DOSYALARI DOĞRULA")
        self.update_install_state_ui()
        QMessageBox.information(self, "Doğrulama tamamlandı", message)

    def repair_error(self, message: str):
        self._active_repair_key = None
        self.status.setText("Doğrulama / onarım hatası")
        self.progress_text.setText("Hata")
        self.verify_button.setText("DOSYALARI DOĞRULA")
        self.update_install_state_ui()
        QMessageBox.critical(self, "Doğrulama hatası", message)


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
