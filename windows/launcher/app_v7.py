from __future__ import annotations

import sys
from datetime import datetime, timezone

from PySide6.QtCore import QObject, QRunnable, Signal
from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox, QPushButton

import app_v4 as base
import app_v6 as previous
from drowned_shared.uninstall import remove_install_tree, validate_uninstall_target

APP_VERSION = "0.6.0"


def find_layout_containing_widget(layout, widget):
    if layout is None:
        return None
    for i in range(layout.count()):
        item = layout.itemAt(i)
        if item.widget() is widget:
            return layout
        child = item.layout()
        if child is not None:
            found = find_layout_containing_widget(child, widget)
            if found is not None:
                return found
    return None


class UninstallSignals(QObject):
    done = Signal(str)
    error = Signal(str)


class UninstallTask(QRunnable):
    def __init__(self, path: str, tag: str):
        super().__init__()
        self.path = path
        self.tag = tag
        self.signals = UninstallSignals()

    def run(self):
        try:
            removed = remove_install_tree(self.path, self.tag)
            self.signals.done.emit(str(removed))
        except Exception as exc:
            self.signals.error.emit(str(exc))


class Launcher(previous.Launcher):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Drowned Launcher {APP_VERSION}")
        self._active_uninstall_key = None
        self._active_uninstall_record = None

        self.uninstall_button = QPushButton("KALDIR")
        self.uninstall_button.setObjectName("secondary")
        self.uninstall_button.setStyleSheet(
            "QPushButton{background:#5b2530;color:#f4dce1;}"
            "QPushButton:hover{background:#7b2f3e;color:white;}"
            "QPushButton:disabled{background:#2b2528;color:#746a6e;}"
        )
        self.uninstall_button.clicked.connect(self.uninstall_current_game)
        action_layout = find_layout_containing_widget(self.centralWidget().layout(), self.install_button)
        if action_layout is not None:
            action_layout.addWidget(self.uninstall_button)
        self.update_install_state_ui()

    def update_install_state_ui(self):
        super().update_install_state_ui()
        if not hasattr(self, "uninstall_button"):
            return
        record = self._record() if self.current_game else None
        self.uninstall_button.setEnabled(bool(record and self._record_path_exists(record)))

    def install_current_game(self):
        super().install_current_game()
        if hasattr(self, "uninstall_button") and self._active_install_context:
            self.uninstall_button.setEnabled(False)

    def verify_current_game(self):
        super().verify_current_game()
        if hasattr(self, "uninstall_button") and self._active_repair_key:
            self.uninstall_button.setEnabled(False)

    def uninstall_current_game(self):
        if not self.current_game:
            return
        record = self._record()
        if not record:
            QMessageBox.information(self, "Kurulu değil", "Bu oyun için kayıtlı bir kurulum bulunamadı.")
            return

        title = str(self.current_game.get("title") or record.get("title") or "Oyun")
        path = str(record.get("install_path") or "")
        tag = str(record.get("tag") or "")
        try:
            target = validate_uninstall_target(path, tag)
        except Exception as exc:
            QMessageBox.critical(self, "Güvenli kaldırma engellendi", str(exc))
            return

        answer = QMessageBox.question(
            self,
            f"{title} kaldırılsın mı?",
            f"Aşağıdaki klasör ve içindeki tüm oyun dosyaları kalıcı olarak silinecek:\n\n{target}\n\n"
            "Launcher kurulum kaydını da temizleyecek. Oyun klasörünün dışındaki kayıt dosyalarına dokunulmaz.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        text, ok = QInputDialog.getText(
            self,
            "Kaldırmayı onayla",
            "Yanlışlıkla silmeyi önlemek için KALDIR yaz:",
        )
        if not ok or text.strip().upper() != "KALDIR":
            return

        key = self._key(self.current_game, self.current_channel)
        self._active_uninstall_key = key
        self._active_uninstall_record = dict(record)
        self.status.setText(f"{title} kaldırılıyor…")
        self.progress.setRange(0, 0)
        self.progress_text.setText("Dosyalar siliniyor")
        self.install_button.setEnabled(False)
        self.verify_button.setEnabled(False)
        self.uninstall_button.setEnabled(False)

        task = UninstallTask(str(target), tag)
        task.signals.done.connect(self.uninstall_done)
        task.signals.error.connect(self.uninstall_error)
        self.pool.start(task)

    def uninstall_done(self, removed_path: str):
        key = self._active_uninstall_key
        record = self._active_uninstall_record or {}
        if key:
            self.install_registry.setdefault("games", {}).pop(key, None)
            history = self.install_registry.setdefault("uninstall_history", [])
            history.append({
                "key": key,
                "title": record.get("title", ""),
                "game_id": record.get("game_id", ""),
                "platform": record.get("platform", ""),
                "channel": record.get("channel", ""),
                "version": record.get("version", ""),
                "tag": record.get("tag", ""),
                "install_path": removed_path,
                "uninstalled_at": datetime.now(timezone.utc).isoformat(),
            })
            if len(history) > 100:
                del history[:-100]
            previous.save_registry(self.install_registry)

        self._active_uninstall_key = None
        self._active_uninstall_record = None
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress_text.setText("")
        self.status.setText("Oyun kaldırıldı")
        self.render_library()
        self.update_install_state_ui()
        QMessageBox.information(
            self,
            "Kaldırma tamamlandı",
            f"Oyun dosyaları silindi ve Launcher kurulum kaydı temizlendi.\n\n{removed_path}",
        )

    def uninstall_error(self, message: str):
        self._active_uninstall_key = None
        self._active_uninstall_record = None
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress_text.setText("Hata")
        self.status.setText("Kaldırma başarısız")
        self.update_install_state_ui()
        QMessageBox.critical(self, "Kaldırma hatası", message)


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
