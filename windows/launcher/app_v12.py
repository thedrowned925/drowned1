from __future__ import annotations

import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSplashScreen,
    QVBoxLayout,
    QWidget,
)

import app_v4 as base
import app_v6 as registry_base
import app_v11 as previous
from drowned_shared.addons import (
    install_optional_package,
    is_addon_installed,
    list_installed_addons,
    remove_optional_package,
    repair_base_with_addons,
)
from drowned_shared.install import DEFAULT_DOWNLOAD_WORKERS, fetch_json
from drowned_shared.util import format_bytes, slugify

APP_VERSION = "0.12.0"
ADDON_DOWNLOAD_WORKERS = DEFAULT_DOWNLOAD_WORKERS


def _fetch_with_retry(url: str) -> dict:
    last_error = None
    for delay in (0.0, 0.5, 1.0, 2.0):
        if delay:
            time.sleep(delay)
        try:
            return fetch_json(base.cache_bust(url))
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"Manifest alınamadı: {last_error}")


class AddonSignals(QObject):
    progress = Signal(int, str)
    log = Signal(str)
    done = Signal(object)
    error = Signal(str)


class AddonInstallTask(QRunnable):
    def __init__(self, package_url: str, base_url: str, target: Path):
        super().__init__()
        self.package_url = package_url
        self.base_url = base_url
        self.target = Path(target)
        self.signals = AddonSignals()

    def run(self):
        try:
            package_manifest = _fetch_with_retry(self.package_url)
            base_manifest = _fetch_with_retry(self.base_url)
            started = time.monotonic()

            def report(done: int, total: int):
                elapsed = max(time.monotonic() - started, 0.001)
                speed = int(done / elapsed)
                self.signals.progress.emit(
                    int(done * 100 / max(total, 1)),
                    f"{format_bytes(done)} / {format_bytes(total)} • {format_bytes(speed)}/sn",
                )

            result = install_optional_package(
                package_manifest,
                self.target,
                base_manifest,
                manifest_url=self.package_url,
                base_manifest_url=self.base_url,
                progress=report,
                log=self.signals.log.emit,
                workers=ADDON_DOWNLOAD_WORKERS,
            )
            self.signals.done.emit(result)
        except Exception as exc:
            self.signals.error.emit(str(exc))


class AddonRemoveTask(QRunnable):
    def __init__(
        self,
        package_id: str,
        base_url: str,
        remaining_urls: list[str],
        target: Path,
    ):
        super().__init__()
        self.package_id = package_id
        self.base_url = base_url
        self.remaining_urls = list(remaining_urls)
        self.target = Path(target)
        self.signals = AddonSignals()

    def run(self):
        try:
            base_manifest = _fetch_with_retry(self.base_url)
            remaining = []
            for url in self.remaining_urls:
                if url:
                    remaining.append(_fetch_with_retry(url))

            def report(done: int, total: int):
                self.signals.progress.emit(
                    int(done * 100 / max(total, 1)),
                    f"Ana dosyalar geri yükleniyor • {format_bytes(done)} / {format_bytes(total)}",
                )

            result = remove_optional_package(
                self.package_id,
                self.target,
                base_manifest,
                remaining,
                progress=report,
                log=self.signals.log.emit,
                workers=ADDON_DOWNLOAD_WORKERS,
            )
            self.signals.done.emit(result)
        except Exception as exc:
            self.signals.error.emit(str(exc))


class AddonAwareRepairTask(QRunnable):
    def __init__(self, base_url: str, addon_urls: list[str], target: Path):
        super().__init__()
        self.base_url = base_url
        self.addon_urls = list(addon_urls)
        self.target = Path(target)
        self.signals = AddonSignals()

    def run(self):
        try:
            base_manifest = _fetch_with_retry(self.base_url)
            addon_manifests = [
                _fetch_with_retry(url) for url in self.addon_urls if url
            ]

            def report(done: int, total: int):
                self.signals.progress.emit(
                    int(done * 100 / max(total, 1)),
                    f"{format_bytes(done)} / {format_bytes(total)}",
                )

            result = repair_base_with_addons(
                base_manifest,
                self.target,
                addon_manifests,
                progress=report,
                log=self.signals.log.emit,
                workers=ADDON_DOWNLOAD_WORKERS,
            )
            self.signals.done.emit(result)
        except Exception as exc:
            self.signals.error.emit(str(exc))


class Launcher(previous.Launcher):
    """Launcher v0.12 with safe, opt-in overlay package management."""

    def __init__(self):
        self._addon_busy = False
        self._addon_rows: list[QWidget] = []
        self._addon_task = None
        self._addon_action = ""
        super().__init__()
        self.setWindowTitle(f"Drowned Launcher {APP_VERSION}")
        self._install_addon_panel()
        self._refresh_addon_panel()

    def _install_addon_panel(self):
        self.addon_panel = QFrame()
        self.addon_panel.setObjectName("panel")
        panel_layout = QVBoxLayout(self.addon_panel)
        panel_layout.setContentsMargins(30, 11, 30, 12)
        panel_layout.setSpacing(7)

        header = QHBoxLayout()
        title = QLabel("İSTEĞE BAĞLI İÇERİK")
        title.setObjectName("panelTitle")
        self.addon_summary = QLabel("Bu sürüm için ek paket yok")
        self.addon_summary.setObjectName("muted")
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.addon_summary)
        panel_layout.addLayout(header)

        self.addon_rows_widget = QWidget()
        self.addon_rows_layout = QVBoxLayout(self.addon_rows_widget)
        self.addon_rows_layout.setContentsMargins(0, 0, 0, 0)
        self.addon_rows_layout.setSpacing(5)
        panel_layout.addWidget(self.addon_rows_widget)

        hint = QLabel(
            "Tik açılırsa paket mevcut oyun klasörünün üstüne kurulur. Tik kapatılırsa onay istenir; "
            "yalnız paketin eklediği dosyalar silinir, değiştirdiği ana oyun dosyaları manifestten geri yüklenir."
        )
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        panel_layout.addWidget(hint)

        action_bar = self.info_card.parentWidget() if hasattr(self, "info_card") else None
        detail = action_bar.parentWidget() if action_bar is not None else None
        layout = detail.layout() if detail is not None else None
        if layout is not None and action_bar is not None:
            index = layout.indexOf(action_bar)
            layout.insertWidget(index + 1, self.addon_panel)

    def _clear_addon_rows(self):
        while self.addon_rows_layout.count():
            item = self.addon_rows_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._addon_rows.clear()

    def _base_data(self) -> dict:
        if not self.current_game:
            return {}
        return (self.current_game.get("channels") or {}).get(self.current_channel) or {}

    def _url_for_record(self, data: dict, *, record: dict | None = None) -> str:
        owner = str((record or {}).get("owner") or self.owner)
        repo = str((record or {}).get("repo") or self.repo)
        branch = str((record or {}).get("branch") or self.branch)
        if data.get("manifest_path"):
            return base.raw_repo_url(owner, repo, branch, str(data["manifest_path"]))
        return str(data.get("manifest_url") or "")

    def _installed_addon_states(self, record: dict | None = None) -> list[dict]:
        record = record or (self._record() if self.current_game else None)
        if not record or not self._record_path_exists(record):
            return []
        return list_installed_addons(Path(record["install_path"]))

    def _refresh_addon_panel(self):
        if not hasattr(self, "addon_rows_layout"):
            return
        self._clear_addon_rows()
        if not self.current_game:
            self.addon_summary.setText("Oyun seçilmedi")
            return

        data = self._base_data()
        record = self._record()
        installed_path = (
            Path(record["install_path"])
            if record and self._record_path_exists(record)
            else None
        )
        states = self._installed_addon_states(record)
        state_by_id = {
            slugify(str(state.get("package_id") or "")): state for state in states
        }
        packages = {
            slugify(str(package.get("id") or package.get("title") or "")): dict(package)
            for package in data.get("optional_packages") or []
        }

        # Keep locally installed packages visible even after the catalog moves
        # to a new base version. They can only be unchecked/removed.
        for package_id, state in state_by_id.items():
            if package_id not in packages:
                packages[package_id] = {
                    "id": package_id,
                    "title": state.get("title") or package_id,
                    "version": state.get("version") or "?",
                    "tag": state.get("tag") or "",
                    "manifest_url": state.get("manifest_url") or "",
                    "size": 0,
                    "_local_only": True,
                }

        if not packages:
            self.addon_summary.setText("Bu sürüm için ek paket yok")
            empty = QLabel("Bu oyuna bağlı isteğe bağlı paket yayınlanmamış.")
            empty.setObjectName("muted")
            self.addon_rows_layout.addWidget(empty)
            return

        installed_count = sum(1 for pid in packages if pid in state_by_id)
        self.addon_summary.setText(
            f"{len(packages)} paket • {installed_count} kurulu"
        )
        base_matches = bool(
            record
            and installed_path
            and str(record.get("tag") or "") == str(data.get("tag") or "")
        )

        for package_id, package in sorted(
            packages.items(), key=lambda pair: str(pair[1].get("title") or pair[0]).lower()
        ):
            state = state_by_id.get(package_id)
            local_only = bool(package.get("_local_only"))
            row = QFrame()
            row.setObjectName("infoCard")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(9, 6, 9, 6)
            checkbox = QCheckBox(str(package.get("title") or package_id))
            checkbox.setChecked(bool(state and state.get("installed") is True))
            version = str(package.get("version") or "?")
            size = int(package.get("size") or 0)
            suffix = f"v{version}"
            if size:
                suffix += f" • {format_bytes(size)}"
            if local_only:
                suffix += " • ESKİ/UYUMSUZ — kaldır"
            meta = QLabel(suffix)
            meta.setObjectName("muted")
            row_layout.addWidget(checkbox, 1)
            row_layout.addWidget(meta)

            can_remove = bool(state and installed_path)
            can_install = bool(installed_path and base_matches and not local_only)
            checkbox.setEnabled(
                not self._addon_busy and (can_remove if checkbox.isChecked() else can_install)
            )
            checkbox.stateChanged.connect(
                lambda value, p=dict(package): self._addon_toggled(p, value == Qt.Checked.value)
            )
            self.addon_rows_layout.addWidget(row)
            self._addon_rows.append(row)

    def _addon_toggled(self, package: dict, checked: bool):
        if self._addon_busy or not self.current_game:
            self._refresh_addon_panel()
            return
        record = self._record()
        if not record or not self._record_path_exists(record):
            QMessageBox.information(self, "Oyun kurulu değil", "Ek paket için önce ana oyunu kur.")
            self._refresh_addon_panel()
            return

        package_id = slugify(str(package.get("id") or package.get("title") or ""))
        title = str(package.get("title") or package_id)
        if checked:
            if package.get("_local_only"):
                self._refresh_addon_panel()
                return
            self._start_addon_install(package)
            return

        answer = QMessageBox.question(
            self,
            f"{title} kaldırılsın mı?",
            f"{title} ek paketi kaldırılacak.\n\n"
            "Paketin yalnız kendisine ait dosyaları silinecek. Ana oyundaki bir dosyanın üstüne "
            "yazdıysa orijinal dosya otomatik olarak geri yüklenecek.\n\nDevam edilsin mi?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            self._refresh_addon_panel()
            return
        self._start_addon_remove(package_id, title)

    def _set_addon_busy(self, busy: bool, action: str = ""):
        self._addon_busy = busy
        self._addon_action = action
        if busy:
            self.install_button.setEnabled(False)
            self.verify_button.setEnabled(False)
            self.uninstall_button.setEnabled(False)
        else:
            self.update_install_state_ui()
        self._refresh_addon_panel()

    def _start_addon_install(self, package: dict):
        record = self._record()
        data = self._base_data()
        if not record:
            return
        package_url = self._url_for_record(package)
        base_url = self._url_for_record(data)
        if not package_url or not base_url:
            QMessageBox.critical(self, "Manifest hatası", "Ek paket veya ana oyun manifesti bulunamadı.")
            self._refresh_addon_panel()
            return

        self._set_addon_busy(True, "install")
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress_text.setText("Ek paket hazırlanıyor…")
        self.status.setText(f"{package.get('title') or package.get('id')} kuruluyor")
        self.logs.clear()
        self.logs.show()
        self.logs.appendPlainText(f"Ek paket: {package.get('title') or package.get('id')}")
        self.logs.appendPlainText(f"Oyun klasörü: {record['install_path']}")

        task = AddonInstallTask(package_url, base_url, Path(record["install_path"]))
        self._addon_task = task
        task.signals.progress.connect(self.install_progress)
        task.signals.log.connect(self.logs.appendPlainText)
        task.signals.done.connect(self._addon_install_done)
        task.signals.error.connect(self._addon_error)
        self.pool.start(task)

    def _start_addon_remove(self, package_id: str, title: str):
        record = self._record()
        if not record:
            return
        states = self._installed_addon_states(record)
        target_state = next(
            (state for state in states if slugify(str(state.get("package_id") or "")) == package_id),
            None,
        )
        if not target_state:
            self._refresh_addon_panel()
            return

        # Removal restores against the base version that this package was
        # actually installed over, even if catalog.json already advertises a
        # newer game version.
        base_url = str(target_state.get("base_manifest_url") or record.get("manifest_url") or "")
        if not base_url and record.get("manifest_path"):
            base_url = self._url_for_record(record, record=record)
        remaining_urls = [
            str(state.get("manifest_url") or "")
            for state in states
            if slugify(str(state.get("package_id") or "")) != package_id
        ]
        if not base_url:
            QMessageBox.critical(self, "Manifest hatası", "Kurulu ana sürümün manifest adresi bulunamadı.")
            self._refresh_addon_panel()
            return

        self._set_addon_busy(True, "remove")
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress_text.setText("Ek paket kaldırılıyor…")
        self.status.setText(f"{title} kaldırılıyor")
        self.logs.clear()
        self.logs.show()
        self.logs.appendPlainText("Paket dosyaları kaldırılıyor; base override'lar güvenli biçimde geri yüklenecek.")

        task = AddonRemoveTask(
            package_id,
            base_url,
            remaining_urls,
            Path(record["install_path"]),
        )
        self._addon_task = task
        task.signals.progress.connect(self.install_progress)
        task.signals.log.connect(self.logs.appendPlainText)
        task.signals.done.connect(lambda result, t=title: self._addon_remove_done(t, result))
        task.signals.error.connect(self._addon_error)
        self.pool.start(task)

    def _addon_install_done(self, state: dict):
        self.progress.setValue(100)
        self.progress_text.setText("%100 • ek paket doğrulandı")
        self.status.setText(f"Ek paket kuruldu • {state.get('title') or state.get('package_id')}")
        self._addon_task = None
        self._set_addon_busy(False)
        QMessageBox.information(
            self,
            "Ek paket kuruldu",
            f"{state.get('title') or state.get('package_id')} v{state.get('version')} oyunun üzerine kuruldu.",
        )

    def _addon_remove_done(self, title: str, result: dict):
        self.progress.setValue(100)
        restored = len(result.get("restored_base_files") or [])
        removed = len(result.get("removed_files") or [])
        self.progress_text.setText("%100 • kaldırıldı")
        self.status.setText(f"Ek paket kaldırıldı • {title}")
        self._addon_task = None
        self._set_addon_busy(False)
        QMessageBox.information(
            self,
            "Ek paket kaldırıldı",
            f"{title} kaldırıldı.\n\n"
            f"Silinen paket dosyası: {removed}\n"
            f"Geri yüklenen ana oyun dosyası: {restored}",
        )

    def _addon_error(self, message: str):
        self._addon_task = None
        self.progress_text.setText("Ek paket işlemi başarısız")
        self.status.setText("Ek paket hatası")
        self._set_addon_busy(False)
        QMessageBox.critical(
            self,
            "Ek paket hatası",
            f"{message}\n\nDosyalar yarım kaldıysa aynı tiki tekrar kullanarak işlem güvenli biçimde yeniden denenebilir.",
        )

    def update_install_state_ui(self):
        super().update_install_state_ui()
        if hasattr(self, "addon_panel"):
            self._refresh_addon_panel()

    def library_selection_changed(self, current, previous_item):
        super().library_selection_changed(current, previous_item)
        if hasattr(self, "addon_panel"):
            self._refresh_addon_panel()

    def install_current_game(self):
        # Do not carry an overlay made for an old base version into a new base
        # version. The local-only row remains visible so the user can uncheck it.
        if self.current_game:
            record = self._record()
            data = self._base_data()
            if (
                record
                and self._record_path_exists(record)
                and str(record.get("tag") or "") != str(data.get("tag") or "")
                and self._installed_addon_states(record)
            ):
                QMessageBox.warning(
                    self,
                    "Önce ek paketleri kaldır",
                    "Ana oyun güncellenmeden önce kurulu isteğe bağlı paketleri kapat. "
                    "Bu, eski sürüme ait override dosyalarının yeni sürüme taşınmasını engeller.",
                )
                self._refresh_addon_panel()
                return
        super().install_current_game()

    def verify_current_game(self):
        if not self.current_game or self._addon_busy:
            return
        record = self._record()
        states = self._installed_addon_states(record)
        if not states:
            super().verify_current_game()
            return
        if not record or not self._record_path_exists(record):
            return

        base_url = str(record.get("manifest_url") or "")
        if record.get("manifest_path"):
            base_url = self._url_for_record(record, record=record)
        addon_urls = [str(state.get("manifest_url") or "") for state in states]
        if not base_url or any(not url for url in addon_urls):
            QMessageBox.critical(self, "Manifest hatası", "Kurulu oyun/ek paket manifestlerinden biri bulunamadı.")
            return

        self._active_repair_key = self._key(self.current_game, self.current_channel)
        self._set_addon_busy(True, "verify")
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress_text.setText("Ana oyun + ek paketler doğrulanıyor…")
        self.status.setText("Dosyalar doğrulanıyor")
        self.logs.clear()
        self.logs.show()
        self.logs.appendPlainText("Önce ana oyun manifesti doğrulanacak, ardından kurulu ek paket overlay'leri tekrar doğrulanacak.")

        task = AddonAwareRepairTask(base_url, addon_urls, Path(record["install_path"]))
        self._addon_task = task
        task.signals.progress.connect(self.install_progress)
        task.signals.log.connect(self.logs.appendPlainText)
        task.signals.done.connect(self._addon_verify_done)
        task.signals.error.connect(self._addon_verify_error)
        self.pool.start(task)

    def _addon_verify_done(self, result: dict):
        self._addon_task = None
        self._addon_busy = False
        super().repair_done(result)
        self._refresh_addon_panel()

    def _addon_verify_error(self, message: str):
        self._addon_task = None
        self._addon_busy = False
        super().repair_error(message)
        self._refresh_addon_panel()


def main():
    previous.previous.base.install_exception_hook()
    app = QApplication(sys.argv)
    app.setApplicationName("Drowned Launcher")
    app.setOrganizationName("Drowned")
    app.setStyle("Fusion")
    app.setStyleSheet(previous.previous.STEAM_STYLE)

    splash = QSplashScreen(previous.previous._splash_pixmap())
    splash.show()
    app.processEvents()

    win = Launcher()
    win.show()
    splash.finish(win)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
