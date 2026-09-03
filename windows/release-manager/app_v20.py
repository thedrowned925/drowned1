from __future__ import annotations

import os
import secrets
import shutil
import sys
from pathlib import Path

import psutil
from PySide6.QtCore import QSettings, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
)

import app_v18 as previous
from drowned_shared.remote_control import RemoteControlAgent
from drowned_shared.steam_artwork import SteamArtworkError, parse_steam_app_id

APP_VERSION = "0.20.0"


class Manager(previous.Manager):
    """v0.20: paired Android remote control for metadata, folder selection and upload start."""

    def __init__(self):
        self._remote_agent: RemoteControlAgent | None = None
        self._remote_pending_steam: str | None = None
        self._remote_settings = QSettings("Drowned", "Drowned Release Manager")
        token = str(self._remote_settings.value("remote/pairing_token", "") or "").strip()
        if len(token) < 24:
            token = self._new_pairing_token()
            self._remote_settings.setValue("remote/pairing_token", token)
        self._remote_pairing_token = token
        super().__init__()
        self.setWindowTitle(
            f"Drowned Release Manager {APP_VERSION} • Android Remote Control + Supabase Realtime"
        )
        self._install_remote_card()
        QTimer.singleShot(1200, self._restart_remote_agent)

    @staticmethod
    def _new_pairing_token() -> str:
        return "DR1-" + secrets.token_urlsafe(24)

    def _install_remote_card(self) -> None:
        tabs = self.centralWidget()
        if not isinstance(tabs, QTabWidget) or tabs.count() == 0:
            return
        page = tabs.widget(0)
        layout = page.layout() if page is not None else None
        if layout is None:
            return

        card = QFrame()
        card.setObjectName("infoCard")
        outer = QVBoxLayout(card)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(7)

        header = QHBoxLayout()
        title = QLabel("ANDROID UZAKTAN KONTROL")
        title.setObjectName("cardTitle")
        self.remote_status = QLabel("Başlatılıyor…")
        self.remote_status.setObjectName("cardHint")
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.remote_status)
        outer.addLayout(header)

        hint = QLabel(
            "Telefon bu kodla bir kez eşleştirilir. Android yalnız komut ve klasör isimlerini gönderir/alır; "
            "oyun dosyaları Supabase'e gitmez. Upload doğrudan bu PC'den GitHub'a yapılır."
        )
        hint.setWordWrap(True)
        hint.setObjectName("muted")
        outer.addWidget(hint)

        row = QHBoxLayout()
        machine = QLineEdit("primary")
        machine.setReadOnly(True)
        machine.setMaximumWidth(130)
        self.remote_pairing_edit = QLineEdit(self._remote_pairing_token)
        self.remote_pairing_edit.setReadOnly(True)
        copy_button = QPushButton("Kodu kopyala")
        copy_button.clicked.connect(
            lambda: QApplication.clipboard().setText(self._remote_pairing_token)
        )
        reconnect = QPushButton("Yeniden bağlan")
        reconnect.clicked.connect(self._restart_remote_agent)
        rotate = QPushButton("Kodu yenile")
        rotate.setObjectName("danger")
        rotate.clicked.connect(self._rotate_pairing_token)
        row.addWidget(machine)
        row.addWidget(self.remote_pairing_edit, 1)
        row.addWidget(copy_button)
        row.addWidget(reconnect)
        row.addWidget(rotate)
        outer.addLayout(row)

        layout.insertWidget(min(2, layout.count()), card)

    def _rotate_pairing_token(self) -> None:
        answer = QMessageBox.question(
            self,
            "Android eşleştirme kodunu yenile",
            "Eski telefondaki eşleştirme geçersiz olacak. Devam edilsin mi?",
        )
        if answer != QMessageBox.Yes:
            return
        self._remote_pairing_token = self._new_pairing_token()
        self._remote_settings.setValue("remote/pairing_token", self._remote_pairing_token)
        self.remote_pairing_edit.setText(self._remote_pairing_token)
        self._restart_remote_agent()

    def _restart_remote_agent(self) -> None:
        if self._remote_agent is not None:
            self._remote_agent.stop()
            self._remote_agent = None
        try:
            github_token = str(self._params().get("token") or "").strip()
        except Exception:
            github_token = ""
        if not github_token:
            self.remote_status.setText("GitHub token gerekli • GitHub sekmesinden kaydet")
            return
        agent = RemoteControlAgent(
            github_token,
            self._remote_pairing_token,
            machine_id="primary",
            display_name="Drowned Release Manager",
        )
        agent.command_received.connect(self._handle_remote_command)
        agent.status_changed.connect(self.remote_status.setText)
        self._remote_agent = agent
        agent.start()

    def _remote_complete(self, command_id: str, result: dict) -> None:
        if self._remote_agent is not None:
            self._remote_agent.complete(command_id, result)

    def _remote_fail(self, command_id: str, message: str) -> None:
        if self._remote_agent is not None:
            self._remote_agent.fail(command_id, message)

    def _remote_state(self) -> dict:
        steam_id = getattr(self, "_steam_app_id", None)
        if not steam_id and hasattr(self, "prep_steam_app_id"):
            raw = self.prep_steam_app_id.text().strip()
            try:
                steam_id = int(parse_steam_app_id(raw)) if raw else None
            except Exception:
                steam_id = None
        thread = getattr(self, "thread", None)
        upload_running = bool(thread is not None and hasattr(thread, "isRunning") and thread.isRunning())
        steam_thread = getattr(self, "steam_thread", None)
        steam_busy = bool(steam_thread is not None and steam_thread.isRunning())
        return {
            "machine_id": "primary",
            "app_version": APP_VERSION,
            "title": self.game_title.text().strip() or self.prep_title.text().strip(),
            "steam_app_id": int(steam_id) if steam_id else None,
            "steam_status": self.steam_status.text() if hasattr(self, "steam_status") else "",
            "steam_busy": steam_busy,
            "description": self.description.toPlainText() if hasattr(self, "description") else "",
            "platform": self.platform.currentText() if hasattr(self, "platform") else "",
            "channel": self.channel.currentText() if hasattr(self, "channel") else "",
            "version": self.version.text().strip() if hasattr(self, "version") else "",
            "source": self.source.text().strip() if hasattr(self, "source") else "",
            "upload_running": upload_running,
            "artwork": {
                "hero": bool(getattr(getattr(self, "hero", None), "path", "")),
                "cover": bool(getattr(getattr(self, "cover", None), "path", "")),
                "logo": bool(getattr(getattr(self, "logo", None), "path", "")),
                "icon": bool(getattr(getattr(self, "icon", None), "path", "")),
                "screenshots": len(getattr(getattr(self, "screenshots", None), "paths", []) or []),
                "trailers": len(getattr(getattr(self, "trailer_panel", None), "trailers", []) or []),
            },
        }

    @staticmethod
    def _remote_roots() -> list[str]:
        roots: list[str] = []
        for part in psutil.disk_partitions(all=False):
            root = str(part.mountpoint or "").strip()
            if not root or not os.path.isdir(root):
                continue
            if "cdrom" in str(part.opts or "").lower():
                continue
            if root not in roots:
                roots.append(root)
        if os.name == "nt" and not roots:
            for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ":
                root = f"{letter}:\\"
                if os.path.isdir(root):
                    roots.append(root)
        return roots

    @classmethod
    def _validated_directory(cls, raw_path: str) -> Path:
        path = Path(str(raw_path or "")).expanduser().resolve()
        if not path.is_dir():
            raise RuntimeError("Klasör bulunamadı.")
        roots = [Path(root).resolve() for root in cls._remote_roots()]
        allowed = False
        for root in roots:
            try:
                path.relative_to(root)
                allowed = True
                break
            except ValueError:
                continue
        if not allowed:
            raise RuntimeError("Bu yol Android klasör taramasına açık bir yerel diskte değil.")
        return path

    @classmethod
    def _list_directory(cls, raw_path: str) -> dict:
        path = cls._validated_directory(raw_path)
        folders = []
        try:
            entries = list(path.iterdir())
        except PermissionError as exc:
            raise RuntimeError("Bu klasöre erişim izni yok.") from exc
        for item in sorted(entries, key=lambda p: p.name.casefold()):
            if len(folders) >= 300:
                break
            try:
                if not item.is_dir():
                    continue
            except OSError:
                continue
            folders.append({"name": item.name, "path": str(item)})
        try:
            usage = shutil.disk_usage(path)
            free = int(usage.free)
        except OSError:
            free = 0
        parent = str(path.parent) if path.parent != path else ""
        return {"path": str(path), "parent": parent, "folders": folders, "disk_free": free}

    def _apply_remote_fields(self, payload: dict) -> None:
        title = str(payload.get("title") or "").strip()
        if title:
            self.game_title.setText(title)
            self.prep_title.setText(title)
        version = str(payload.get("version") or "").strip()
        if version:
            self.version.setText(version)
        if "description" in payload:
            self.description.setPlainText(str(payload.get("description") or ""))
        for key, combo in (("platform", self.platform), ("channel", self.channel)):
            value = str(payload.get(key) or "").strip()
            if not value:
                continue
            index = combo.findText(value)
            if index >= 0:
                combo.setCurrentIndex(index)

    def _handle_remote_command(self, command: dict) -> None:
        command_id = str(command.get("id") or "")
        command_type = str(command.get("command_type") or "")
        payload = command.get("payload") if isinstance(command.get("payload"), dict) else {}
        if not command_id:
            return
        try:
            if command_type in {"ping", "get_state"}:
                self._remote_complete(command_id, self._remote_state())
                return

            if command_type == "list_roots":
                roots = []
                for root in self._remote_roots():
                    try:
                        usage = shutil.disk_usage(root)
                        free = int(usage.free)
                    except OSError:
                        free = 0
                    roots.append({"name": root, "path": root, "disk_free": free})
                self._remote_complete(command_id, {"roots": roots})
                return

            if command_type == "list_dir":
                self._remote_complete(command_id, self._list_directory(str(payload.get("path") or "")))
                return

            if command_type == "fetch_steam":
                if self._remote_pending_steam:
                    raise RuntimeError("Steam bilgileri zaten alınıyor.")
                thread = getattr(self, "thread", None)
                if thread is not None and hasattr(thread, "isRunning") and thread.isRunning():
                    raise RuntimeError("Upload devam ederken yeni Steam oyunu hazırlanamaz.")
                app_id = int(parse_steam_app_id(str(payload.get("app_id") or "")))
                self.reset_for_new_game()
                self.prep_steam_app_id.setText(str(app_id))
                self._remote_pending_steam = command_id
                self.fetch_automation_steam_metadata()
                steam_thread = getattr(self, "steam_thread", None)
                if steam_thread is None:
                    self._remote_pending_steam = None
                    raise RuntimeError("Steam bilgi alma işlemi başlatılamadı.")
                return

            if command_type == "select_source":
                path = str(self._validated_directory(str(payload.get("path") or "")))
                self.auto_upload_source.setText(path)
                self._apply_publish_source(path)
                self.open_publish_button.setEnabled(True)
                self._remote_complete(command_id, self._remote_state())
                return

            if command_type == "set_publish_fields":
                self._apply_remote_fields(payload)
                self._remote_complete(command_id, self._remote_state())
                return

            if command_type == "start_upload":
                self._apply_remote_fields(payload)
                requested_source = str(payload.get("source") or "").strip()
                if requested_source:
                    path = str(self._validated_directory(requested_source))
                    self.auto_upload_source.setText(path)
                    self._apply_publish_source(path)
                if not self.source.text().strip():
                    raise RuntimeError("Önce PC'den bir upload klasörü seç.")
                if not self.game_title.text().strip():
                    raise RuntimeError("Oyun adı boş.")
                thread = getattr(self, "thread", None)
                if thread is not None and hasattr(thread, "isRunning") and thread.isRunning():
                    raise RuntimeError("Zaten aktif bir upload var.")
                self.publish()
                started_thread = getattr(self, "thread", None)
                started = bool(
                    started_thread is not None
                    and hasattr(started_thread, "isRunning")
                    and started_thread.isRunning()
                ) or not self.publish_button.isEnabled()
                if not started:
                    raise RuntimeError("Upload başlatılamadı; PC Release Manager logunu kontrol et.")
                result = self._remote_state()
                result["accepted"] = True
                self._remote_complete(command_id, result)
                return

            raise RuntimeError(f"Desteklenmeyen uzaktan komut: {command_type}")
        except SteamArtworkError as exc:
            self._remote_fail(command_id, str(exc))
        except Exception as exc:
            self._remote_fail(command_id, str(exc))

    def _steam_artwork_done(self, result: dict):
        super()._steam_artwork_done(result)
        command_id = self._remote_pending_steam
        if command_id:
            self._remote_pending_steam = None
            state = self._remote_state()
            state["steam_name"] = str(result.get("name") or state.get("title") or "")
            state["steam_app_id"] = int(result.get("app_id") or state.get("steam_app_id") or 0) or None
            self._remote_complete(command_id, state)

    def _steam_artwork_error(self, message: str):
        command_id = self._remote_pending_steam
        self._remote_pending_steam = None
        super()._steam_artwork_error(message)
        if command_id:
            self._remote_fail(command_id, message)

    def closeEvent(self, event):
        if self._remote_agent is not None:
            self._remote_agent.stop()
        super().closeEvent(event)


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
