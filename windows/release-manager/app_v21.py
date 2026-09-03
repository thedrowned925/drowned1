from __future__ import annotations

import re
import sys
import threading
from pathlib import Path

from PySide6.QtWidgets import QApplication

import app_v20 as previous
from drowned_shared.realtime_status import LiveStatusPublisher
from remote_file_ops import extract_archive_remote, run_file_operation


APP_VERSION = "0.22.0"
_ARCHIVE_SUFFIXES = {".zip", ".rar", ".7z"}
_MULTIPART_RAR = re.compile(r"\.part(\d+)\.rar$", re.I)


class Manager(previous.Manager):
    """v0.22: Android remote extraction + basic PC file management."""

    def __init__(self):
        self._remote_extract_thread: threading.Thread | None = None
        self._remote_extract_cancel = threading.Event()
        self._remote_extract_archive = ""
        self._remote_extract_target = ""
        self._remote_extract_output = ""
        self._remote_extract_error = ""
        self._remote_extract_live: LiveStatusPublisher | None = None

        self._remote_file_thread: threading.Thread | None = None
        self._remote_file_cancel = threading.Event()
        self._remote_file_operation = ""
        self._remote_file_source = ""
        self._remote_file_target = ""
        self._remote_file_output = ""
        self._remote_file_error = ""
        self._remote_file_live: LiveStatusPublisher | None = None

        super().__init__()
        self.setWindowTitle(
            f"Drowned Release Manager {APP_VERSION} • Android Remote Extract + File Manager + Upload"
        )

    def _extract_running(self) -> bool:
        return bool(self._remote_extract_thread is not None and self._remote_extract_thread.is_alive())

    def _file_running(self) -> bool:
        return bool(self._remote_file_thread is not None and self._remote_file_thread.is_alive())

    def _upload_running(self) -> bool:
        upload_thread = getattr(self, "thread", None)
        return bool(
            upload_thread is not None
            and hasattr(upload_thread, "isRunning")
            and upload_thread.isRunning()
        )

    def _storage_busy(self) -> bool:
        return self._extract_running() or self._file_running() or self._upload_running()

    def _remote_state(self) -> dict:
        state = super()._remote_state()
        state.update(
            {
                # Supabase Realtime is the canonical activity source on Android.
                "extract_running": False,
                "extract_archive": self._remote_extract_archive,
                "extract_target": self._remote_extract_target,
                "extract_output": self._remote_extract_output,
                "extract_error": self._remote_extract_error,
                "file_running": False,
                "file_operation": self._remote_file_operation,
                "file_source": self._remote_file_source,
                "file_target": self._remote_file_target,
                "file_output": self._remote_file_output,
                "file_error": self._remote_file_error,
            }
        )
        return state

    @classmethod
    def _validated_path(cls, raw_path: str) -> Path:
        path = Path(str(raw_path or "")).expanduser().resolve()
        if not path.exists():
            raise RuntimeError("Dosya/klasör bulunamadı.")
        if path.is_dir():
            return cls._validated_directory(str(path))
        cls._validated_directory(str(path.parent))
        return path

    @classmethod
    def _validated_archive(cls, raw_path: str) -> Path:
        path = cls._validated_path(raw_path)
        if not path.is_file():
            raise RuntimeError("Arşiv dosyası bulunamadı.")
        if path.suffix.lower() not in _ARCHIVE_SUFFIXES:
            raise RuntimeError("Yalnızca ZIP, RAR ve 7z arşivleri destekleniyor.")
        match = _MULTIPART_RAR.search(path.name)
        if match and int(match.group(1)) != 1:
            raise RuntimeError("Çok parçalı RAR için ilk parçayı (.part1.rar / .part01.rar) seç.")
        return path

    @staticmethod
    def _validated_leaf_name(raw_name: str) -> str:
        name = str(raw_name or "").strip()
        if not name or name in {".", ".."}:
            raise RuntimeError("Geçerli bir ad gir.")
        if any(ch in name for ch in '<>:"/\\|?*') or any(ord(ch) < 32 for ch in name):
            raise RuntimeError("Dosya/klasör adı geçersiz karakter içeriyor.")
        if name.endswith(" ") or name.endswith("."):
            raise RuntimeError("Ad boşluk veya nokta ile bitemez.")
        return name

    @classmethod
    def _list_directory(cls, raw_path: str) -> dict:
        result = super()._list_directory(raw_path)
        path = cls._validated_directory(raw_path)
        archives: list[dict] = []
        files: list[dict] = []
        try:
            entries = sorted(path.iterdir(), key=lambda p: p.name.casefold())
        except PermissionError as exc:
            raise RuntimeError("Bu klasöre erişim izni yok.") from exc
        for item in entries:
            if len(archives) + len(files) >= 240:
                break
            try:
                if not item.is_file():
                    continue
                size = int(item.stat().st_size)
            except OSError:
                continue
            if item.suffix.lower() in _ARCHIVE_SUFFIXES:
                match = _MULTIPART_RAR.search(item.name)
                first_part = not match or int(match.group(1)) == 1
                archives.append(
                    {
                        "name": item.name,
                        "path": str(item),
                        "size": size,
                        "kind": item.suffix.lower().lstrip("."),
                        "first_part": first_part,
                    }
                )
            else:
                files.append(
                    {
                        "name": item.name,
                        "path": str(item),
                        "size": size,
                        "kind": item.suffix.lower().lstrip(".") or "file",
                    }
                )
        result["archives"] = archives
        result["files"] = files
        return result

    def _new_extract_publisher(self, title: str) -> LiveStatusPublisher | None:
        publisher = self._new_live_publisher("extract")
        if publisher is None:
            return None
        publisher.set_context(kind="extract", title=title)
        return publisher

    def _new_file_publisher(self, title: str) -> LiveStatusPublisher | None:
        publisher = self._new_live_publisher("fileop")
        if publisher is None:
            return None
        publisher.set_context(kind="fileop", title=title)
        return publisher

    def _start_remote_extract(self, command_id: str, payload: dict) -> None:
        if self._extract_running():
            raise RuntimeError("Zaten aktif bir arşiv çıkarma işlemi var.")
        if self._file_running():
            raise RuntimeError("Dosya işlemi devam ederken arşiv çıkarma başlatılamaz.")
        if self._upload_running():
            raise RuntimeError("Upload devam ederken arşiv çıkarma başlatılamaz.")

        archive = self._validated_archive(str(payload.get("archive") or ""))
        target_raw = str(payload.get("target") or "").strip() or str(archive.parent)
        target = self._validated_directory(target_raw)
        title = str(payload.get("title") or "").strip()
        if not title:
            title = self.game_title.text().strip() or self.prep_title.text().strip() or archive.stem

        self._remote_extract_cancel.clear()
        self._remote_extract_archive = str(archive)
        self._remote_extract_target = str(target)
        self._remote_extract_output = ""
        self._remote_extract_error = ""

        if self._remote_extract_live is not None:
            self._remote_extract_live.close()
        publisher = self._new_extract_publisher(title)
        self._remote_extract_live = publisher

        def telemetry(snapshot: dict) -> None:
            if publisher is not None:
                publisher.update(dict(snapshot), active=True)

        def log(message: str) -> None:
            try:
                self.log(f"[Android Extract] {message}")
            except Exception:
                pass

        def worker() -> None:
            try:
                if publisher is not None:
                    publisher.update(
                        {
                            "phase": "extract",
                            "done": 0,
                            "total": max(1, int(archive.stat().st_size)),
                            "progress": 0.0,
                            "speed": 0.0,
                            "eta": None,
                            "detail": archive.name,
                            "current_item": str(archive),
                        },
                        force=True,
                        active=True,
                    )
                extract_root = extract_archive_remote(
                    archive,
                    target,
                    title,
                    telemetry=telemetry,
                    log=log,
                    cancelled=self._remote_extract_cancel.is_set,
                )
                self._remote_extract_output = str(extract_root)
                self._remote_extract_error = ""
                if publisher is not None:
                    publisher.finish("complete", f"Arşiv çıkarıldı: {extract_root}")
            except Exception as exc:
                message = str(exc)
                self._remote_extract_error = message
                if publisher is not None:
                    if self._remote_extract_cancel.is_set():
                        publisher.update(
                            {
                                "phase": "cancelled",
                                "done": 0,
                                "total": 1,
                                "progress": 0.0,
                                "speed": 0.0,
                                "eta": None,
                                "detail": "Arşiv çıkarma kullanıcı tarafından iptal edildi",
                            },
                            force=True,
                            active=False,
                        )
                    else:
                        publisher.fail(message)
            finally:
                self._remote_extract_thread = None

        thread = threading.Thread(target=worker, name="drowned-remote-extract", daemon=True)
        self._remote_extract_thread = thread
        thread.start()
        result = self._remote_state()
        result["accepted"] = True
        result["archive"] = str(archive)
        result["target"] = str(target)
        self._remote_complete(command_id, result)

    def _cancel_remote_extract(self, command_id: str) -> None:
        if not self._extract_running():
            result = self._remote_state()
            result["accepted"] = False
            result["message"] = "Aktif arşiv çıkarma işlemi yok."
            self._remote_complete(command_id, result)
            return
        self._remote_extract_cancel.set()
        result = self._remote_state()
        result["accepted"] = True
        result["message"] = "İptal sinyali PC'ye gönderildi."
        self._remote_complete(command_id, result)

    def _start_file_operation(self, command_id: str, payload: dict, *, move: bool) -> None:
        if self._storage_busy():
            raise RuntimeError("Başka bir disk/yayın işlemi devam ediyor.")
        source = self._validated_path(str(payload.get("source") or ""))
        target = self._validated_directory(str(payload.get("target") or ""))
        operation = "move" if move else "copy"

        self._remote_file_cancel.clear()
        self._remote_file_operation = operation
        self._remote_file_source = str(source)
        self._remote_file_target = str(target)
        self._remote_file_output = ""
        self._remote_file_error = ""

        if self._remote_file_live is not None:
            self._remote_file_live.close()
        publisher = self._new_file_publisher(source.name)
        self._remote_file_live = publisher

        def telemetry(snapshot: dict) -> None:
            if publisher is not None:
                publisher.update(dict(snapshot), active=True)

        def log(message: str) -> None:
            try:
                self.log(f"[Android File] {message}")
            except Exception:
                pass

        def worker() -> None:
            try:
                output = run_file_operation(
                    source,
                    target,
                    move=move,
                    telemetry=telemetry,
                    log=log,
                    cancelled=self._remote_file_cancel.is_set,
                )
                self._remote_file_output = str(output)
                self._remote_file_error = ""
                if publisher is not None:
                    publisher.finish("complete", f"{'Taşıma' if move else 'Kopyalama'} tamamlandı: {output}")
            except Exception as exc:
                message = str(exc)
                self._remote_file_error = message
                if publisher is not None:
                    if self._remote_file_cancel.is_set():
                        publisher.update(
                            {
                                "phase": "cancelled",
                                "done": 0,
                                "total": 1,
                                "progress": 0.0,
                                "speed": 0.0,
                                "eta": None,
                                "detail": "Dosya işlemi kullanıcı tarafından iptal edildi",
                            },
                            force=True,
                            active=False,
                        )
                    else:
                        publisher.fail(message)
            finally:
                self._remote_file_thread = None

        thread = threading.Thread(target=worker, name=f"drowned-remote-{operation}", daemon=True)
        self._remote_file_thread = thread
        thread.start()
        result = self._remote_state()
        result["accepted"] = True
        self._remote_complete(command_id, result)

    def _cancel_file_operation(self, command_id: str) -> None:
        if not self._file_running():
            result = self._remote_state()
            result["accepted"] = False
            result["message"] = "Aktif dosya işlemi yok."
            self._remote_complete(command_id, result)
            return
        self._remote_file_cancel.set()
        result = self._remote_state()
        result["accepted"] = True
        result["message"] = "Dosya işlemi için iptal sinyali gönderildi."
        self._remote_complete(command_id, result)

    def _make_remote_folder(self, command_id: str, payload: dict) -> None:
        if self._storage_busy():
            raise RuntimeError("Başka bir disk/yayın işlemi devam ediyor.")
        parent = self._validated_directory(str(payload.get("parent") or ""))
        name = self._validated_leaf_name(str(payload.get("name") or ""))
        destination = parent / name
        if destination.exists():
            raise RuntimeError("Bu isimde bir dosya/klasör zaten var.")
        destination.mkdir()
        self._remote_complete(command_id, {"ok": True, "path": str(destination)})

    def _rename_remote_path(self, command_id: str, payload: dict) -> None:
        if self._storage_busy():
            raise RuntimeError("Başka bir disk/yayın işlemi devam ediyor.")
        source = self._validated_path(str(payload.get("path") or ""))
        new_name = self._validated_leaf_name(str(payload.get("name") or ""))
        destination = source.with_name(new_name)
        self._validated_directory(str(destination.parent))
        if destination.exists():
            raise RuntimeError("Hedef isim zaten kullanılıyor.")
        source.rename(destination)
        self._remote_complete(command_id, {"ok": True, "path": str(destination)})

    def _handle_remote_command(self, command: dict) -> None:
        command_id = str(command.get("id") or "")
        command_type = str(command.get("command_type") or "")
        payload = command.get("payload") if isinstance(command.get("payload"), dict) else {}
        if not command_id:
            return
        try:
            if command_type == "start_extract":
                self._start_remote_extract(command_id, payload)
                return
            if command_type == "cancel_extract":
                self._cancel_remote_extract(command_id)
                return
            if command_type == "fs_copy":
                self._start_file_operation(command_id, payload, move=False)
                return
            if command_type == "fs_move":
                self._start_file_operation(command_id, payload, move=True)
                return
            if command_type == "fs_cancel":
                self._cancel_file_operation(command_id)
                return
            if command_type == "fs_mkdir":
                self._make_remote_folder(command_id, payload)
                return
            if command_type == "fs_rename":
                self._rename_remote_path(command_id, payload)
                return
            if command_type == "start_upload" and (self._extract_running() or self._file_running()):
                raise RuntimeError("Disk işlemi bitmeden upload başlatılamaz.")
        except Exception as exc:
            self._remote_fail(command_id, str(exc))
            return
        super()._handle_remote_command(command)

    def closeEvent(self, event):
        self._remote_extract_cancel.set()
        self._remote_file_cancel.set()
        if self._remote_extract_live is not None:
            self._remote_extract_live.close()
        if self._remote_file_live is not None:
            self._remote_file_live.close()
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
