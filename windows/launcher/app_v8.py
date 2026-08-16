from __future__ import annotations

import sys
import time
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Signal
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox, QPushButton

import app_v4 as base
import app_v6 as registry_base
import app_v7 as previous
from drowned_shared.errors import DownloadCancelled
from drowned_shared.install import DownloadControl, fetch_json, install_manifest
from drowned_shared.util import format_bytes, safe_windows_dir_name

APP_VERSION = "0.8.0"
DOWNLOAD_WORKERS = 16


class TurboInstallSignals(QObject):
    progress = Signal(int, str)
    log = Signal(str)
    done = Signal()
    cancelled = Signal()
    error = Signal(str)


class TurboInstallTask(QRunnable):
    def __init__(self, manifest_url: str, target: Path, control: DownloadControl):
        super().__init__()
        self.manifest_url = manifest_url
        self.target = Path(target)
        self.control = control
        self.signals = TurboInstallSignals()

    def run(self):
        try:
            manifest = None
            last_error = None
            for delay in (0.0, 0.5, 1.0, 2.0):
                self.control.checkpoint()
                if delay:
                    time.sleep(delay)
                try:
                    manifest = fetch_json(base.cache_bust(self.manifest_url))
                    break
                except Exception as exc:
                    last_error = exc
            if manifest is None:
                raise RuntimeError(f"Manifest alınamadı: {last_error}")

            started = time.monotonic()

            def report(done: int, total: int):
                elapsed = max(time.monotonic() - started, 0.001)
                speed = int(done / elapsed)
                percent = int(done * 100 / max(total, 1))
                text = (
                    f"{format_bytes(done)} / {format_bytes(total)}"
                    f"  •  {format_bytes(speed)}/sn  •  {DOWNLOAD_WORKERS} stream"
                )
                self.signals.progress.emit(max(0, min(percent, 100)), text)

            install_manifest(
                manifest,
                self.target,
                progress=report,
                log=self.signals.log.emit,
                cancelled=lambda: self.control.cancelled,
                workers=DOWNLOAD_WORKERS,
                control=self.control,
            )
            self.signals.done.emit()
        except DownloadCancelled:
            self.signals.cancelled.emit()
        except Exception as exc:
            if self.control.cancelled:
                self.signals.cancelled.emit()
            else:
                self.signals.error.emit(str(exc))


class Launcher(previous.Launcher):
    def __init__(self):
        self.download_control: DownloadControl | None = None
        super().__init__()
        self.setWindowTitle(f"Drowned Launcher {APP_VERSION}")

        # app_v7 created the uninstall button, but its search started above a
        # QSplitter and therefore could not reach the nested action row. Start
        # from the content widget itself so the button is guaranteed visible.
        action_root = self.install_button.parentWidget()
        action_layout = previous.find_layout_containing_widget(
            action_root.layout() if action_root else None,
            self.install_button,
        )
        if action_layout is not None and action_layout.indexOf(self.uninstall_button) < 0:
            action_layout.insertWidget(2, self.uninstall_button)
        self.uninstall_button.show()
        self.uninstall_button.setToolTip("Kurulu oyun dosyalarını ve Launcher kaydını kaldır")

        self.pause_button = QPushButton("DURAKLAT")
        self.pause_button.setObjectName("secondary")
        self.pause_button.clicked.connect(self.toggle_pause)
        self.pause_button.hide()

        self.cancel_button = QPushButton("İPTAL ET")
        self.cancel_button.setObjectName("secondary")
        self.cancel_button.setStyleSheet(
            "QPushButton{background:#5b2530;color:#f4dce1;}"
            "QPushButton:hover{background:#7b2f3e;color:white;}"
        )
        self.cancel_button.clicked.connect(self.cancel_download)
        self.cancel_button.hide()

        status_root = self.status.parentWidget()
        status_layout = previous.find_layout_containing_widget(
            status_root.layout() if status_root else None,
            self.status,
        )
        if status_layout is not None:
            status_layout.insertWidget(1, self.pause_button)
            status_layout.insertWidget(2, self.cancel_button)

        self.update_install_state_ui()

    def _partials(self) -> dict:
        return self.install_registry.setdefault("partials", {})

    def _partial(self) -> dict | None:
        if not self.current_game:
            return None
        return self._partials().get(self._key(self.current_game, self.current_channel))

    def _valid_partial(self) -> dict | None:
        partial = self._partial()
        if not partial:
            return None
        try:
            path = Path(partial.get("install_path", ""))
            if path.is_dir() and (path / ".drowned" / "state.json").is_file():
                return partial
        except Exception:
            pass
        return None

    def _set_download_controls(self, active: bool):
        self.pause_button.setVisible(active)
        self.cancel_button.setVisible(active)
        if not active:
            self.pause_button.setText("DURAKLAT")

    def update_install_state_ui(self):
        super().update_install_state_ui()
        if not hasattr(self, "pause_button"):
            return
        if self.download_control is not None:
            self.install_button.setEnabled(False)
            self.verify_button.setEnabled(False)
            self.uninstall_button.setEnabled(False)
            return

        record = self._record() if self.current_game else None
        partial = self._valid_partial() if self.current_game else None
        if not record and partial:
            self.install_button.setText("DEVAM ET")
            self.install_button.setEnabled(True)
            self.verify_button.setEnabled(False)
            self.uninstall_button.setEnabled(False)
            self.status.setText(
                f"Yarım indirme bulundu • {partial.get('install_path','')}"
            )

    def install_current_game(self):
        if not self.current_game or self.download_control is not None:
            return

        game = self.current_game
        channel = self.current_channel
        data = (game.get("channels") or {}).get(channel) or {}
        display_title = str(game.get("title") or "Game")
        record = self._record(game, channel)
        partial = self._valid_partial()

        manifest_url = self._manifest_url(data)
        if not manifest_url:
            QMessageBox.critical(self, "Manifest hatası", "Bu yayın için manifest adresi bulunamadı.")
            return

        if record and self._record_path_exists(record):
            target = Path(record["install_path"])
        elif partial:
            target = Path(partial["install_path"])
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

        context = {
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
        self._active_install_context = context
        self._partials()[context["key"]] = dict(context)
        registry_base.save_registry(self.install_registry)

        self.download_control = DownloadControl()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress_text.setText("Bağlantılar hazırlanıyor…")
        self.status.setText(f"{display_title} indiriliyor • Turbo {DOWNLOAD_WORKERS} stream")
        self.logs.clear()
        self.logs.show()
        self.logs.appendPlainText(f"Kurulum klasörü: {target}")
        self.logs.appendPlainText(
            "Turbo indirme aktif: çoklu chunk/range bağlantıları kullanılacak."
        )
        if (target / ".drowned" / "state.json").exists():
            self.logs.appendPlainText(
                "Önceki indirme state'i bulundu; tamamlanan chunk'lar atlanacak."
            )

        self.install_button.setText("İNDİRİLİYOR…")
        self.install_button.setEnabled(False)
        self.verify_button.setEnabled(False)
        self.uninstall_button.setEnabled(False)
        self._set_download_controls(True)

        task = TurboInstallTask(manifest_url, target, self.download_control)
        task.signals.progress.connect(self.install_progress)
        task.signals.log.connect(self.logs.appendPlainText)
        task.signals.done.connect(self.install_done)
        task.signals.cancelled.connect(self.install_cancelled)
        task.signals.error.connect(self.install_error)
        self.pool.start(task)

    def toggle_pause(self):
        control = self.download_control
        if control is None:
            return
        if control.paused:
            control.resume()
            self.pause_button.setText("DURAKLAT")
            self.status.setText("İndirme devam ediyor…")
            self.logs.appendPlainText("İndirme devam ettirildi.")
        else:
            control.pause()
            self.pause_button.setText("DEVAM ET")
            self.status.setText("İndirme duraklatıldı")
            self.logs.appendPlainText("İndirme duraklatıldı; çalışan stream'ler bekletiliyor.")

    def cancel_download(self):
        if self.download_control is None:
            return
        answer = QMessageBox.question(
            self,
            "İndirme iptal edilsin mi?",
            "İndirme durdurulacak. Tamamlanıp SHA-256 doğrulaması geçmiş chunk'lar "
            "korunacak; daha sonra DEVAM ET ile kaldığın yerden sürdürebilirsin.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self.cancel_button.setEnabled(False)
        self.pause_button.setEnabled(False)
        self.status.setText("İndirme iptal ediliyor…")
        self.download_control.cancel()

    def install_done(self):
        key = (self._active_install_context or {}).get("key")
        if key:
            self._partials().pop(key, None)
            registry_base.save_registry(self.install_registry)
        self.download_control = None
        self.pause_button.setEnabled(True)
        self.cancel_button.setEnabled(True)
        self._set_download_controls(False)
        super().install_done()
        self.update_install_state_ui()

    def install_cancelled(self):
        self.download_control = None
        self.pause_button.setEnabled(True)
        self.cancel_button.setEnabled(True)
        self._set_download_controls(False)
        self._active_install_context = None
        self.progress_text.setText("İptal edildi • tamamlanan parçalar korundu")
        self.status.setText("İndirme iptal edildi • DEVAM ET ile sürdürülebilir")
        self.logs.appendPlainText(
            "İptal tamamlandı. Yalnız SHA-256 doğrulanmış chunk'lar tamamlandı olarak saklandı."
        )
        self.update_install_state_ui()

    def install_error(self, message: str):
        self.download_control = None
        self.pause_button.setEnabled(True)
        self.cancel_button.setEnabled(True)
        self._set_download_controls(False)
        # Partial registry deliberately remains so a transient network failure
        # never forces the user to restart a large download from zero.
        self._active_install_context = None
        self.progress_text.setText("Hata • tamamlanan parçalar korundu")
        self.status.setText("İndirme kesildi • DEVAM ET kullanılabilir")
        self.update_install_state_ui()
        QMessageBox.critical(
            self,
            "İndirme hatası",
            f"{message}\n\nTamamlanan ve doğrulanan parçalar korundu. DEVAM ET ile tekrar deneyebilirsin.",
        )


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
