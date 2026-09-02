from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QTabWidget,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

import app_v9 as previous
from drowned_shared.addon_delete import delete_optional_package
from drowned_shared.addon_publish import publish_optional_package
from drowned_shared.chunking import ChunkBuilder
from drowned_shared.github_client import GitHubClient
from drowned_shared.metadata import load_catalog
from drowned_shared.turbo_upload import choose_upload_plan
from drowned_shared.upload_status import UploadStatusBroadcaster
from drowned_shared.util import format_bytes, slugify

APP_VERSION = "0.10.0"


class OptionalPackageWorker(QObject):
    progress = Signal(int)
    log = Signal(str)
    done = Signal(object)
    error = Signal(str)

    def __init__(self, params: dict):
        super().__init__()
        self.params = params
        self.cancelled = False

    def run(self):
        broadcaster = None
        try:
            p = self.params
            client = GitHubClient(p["token"], p["owner"], p["repo"], p["branch"])
            client.repo_info()
            broadcaster = UploadStatusBroadcaster(
                client, "addon", p["package_title"], p["platform"], p["channel"], p["package_version"]
            )

            def on_progress(sent, total):
                self.progress.emit(int(sent * 100 / max(total, 1)))
                broadcaster.update_simple(sent, total)

            manifest = publish_optional_package(
                client,
                Path(p["source"]),
                p["game_id"],
                p["platform"],
                p["channel"],
                p["base_version"],
                p["package_title"],
                p["package_id"],
                p["package_version"],
                p["description"],
                progress=on_progress,
                log=self.log.emit,
                cancelled=lambda: self.cancelled,
            )
            broadcaster.finish()
            self.done.emit(manifest)
        except Exception as exc:
            if broadcaster:
                broadcaster.fail(str(exc))
            self.error.emit(str(exc))


class OptionalPackageDeleteWorker(QObject):
    log = Signal(str)
    done = Signal(object)
    error = Signal(str)

    def __init__(self, params: dict):
        super().__init__()
        self.params = params

    def run(self):
        try:
            p = self.params
            client = GitHubClient(p["token"], p["owner"], p["repo"], p["branch"])
            client.repo_info()
            result = delete_optional_package(
                client,
                p["game_id"],
                p["platform"],
                p["channel"],
                p["package_id"],
                log=self.log.emit,
            )
            self.done.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))


class Manager(previous.Manager):
    """Balanced Direct Stream Release Manager with optional overlay packages."""

    def __init__(self):
        self.addon_catalog = {"games": []}
        self.addon_thread = None
        self.addon_worker = None
        self.addon_delete_thread = None
        self.addon_delete_worker = None
        super().__init__()
        self.setWindowTitle(
            f"Drowned Release Manager {APP_VERSION} • Balanced Direct Stream + Optional Packages"
        )
        tabs = self.centralWidget()
        if isinstance(tabs, QTabWidget):
            tabs.insertTab(1, self._optional_packages_tab(), "Ek Paketler")
        self.refresh_addon_catalog(silent=True)

    def _optional_packages_tab(self):
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(16, 16, 16, 18)
        outer.setSpacing(12)

        title = QLabel("İsteğe bağlı ek paketler")
        title.setStyleSheet("font-size:28px;font-weight:800;color:white")
        subtitle = QLabel(
            "High Resolution Textures, HD Audio, Bonus Content gibi paketleri ana oyundan ayrı yayınla. "
            "Launcher kullanıcı isterse paketi aynı oyun klasörünün üstüne kurar; kaldırınca yalnız paket "
            "dosyaları temizlenir ve değiştirilmiş ana dosyalar otomatik geri onarılır."
        )
        subtitle.setWordWrap(True)
        subtitle.setObjectName("cardHint")
        outer.addWidget(title)
        outer.addWidget(subtitle)

        target_card = QFrame()
        target_card.setObjectName("infoCard")
        target_form = QFormLayout(target_card)
        self.addon_target = QComboBox()
        self.addon_target.currentIndexChanged.connect(self._sync_addon_target)
        refresh = QPushButton("Kataloğu yenile")
        refresh.clicked.connect(self.refresh_addon_catalog)
        row = QHBoxLayout()
        row.addWidget(self.addon_target, 1)
        row.addWidget(refresh)
        row_widget = QWidget()
        row_widget.setLayout(row)
        self.addon_base_info = QLabel("Önce katalogdan bir oyun/sürüm seç.")
        self.addon_base_info.setWordWrap(True)
        self.addon_base_info.setObjectName("muted")
        target_form.addRow("Ana oyun / sürüm", row_widget)
        target_form.addRow("Bağlantı", self.addon_base_info)
        outer.addWidget(target_card)

        form_card = QFrame()
        form_card.setObjectName("infoCard")
        form = QFormLayout(form_card)
        self.addon_title = QLineEdit()
        self.addon_title.setPlaceholderText("High Resolution Textures")
        self.addon_id = QLineEdit()
        self.addon_id.setPlaceholderText("high-resolution-textures")
        self.addon_title.textChanged.connect(
            lambda text: self.addon_id.setText(slugify(text)) if text.strip() else None
        )
        self.addon_version = QLineEdit("1.0.0")
        self.addon_description = QTextEdit()
        self.addon_description.setFixedHeight(70)
        self.addon_source = QLineEdit()
        self.addon_source.setReadOnly(True)
        choose = QPushButton("Paket klasörü seç")
        choose.clicked.connect(self.pick_addon_source)
        source_row = QHBoxLayout()
        source_row.setContentsMargins(0, 0, 0, 0)
        source_row.addWidget(self.addon_source, 1)
        source_row.addWidget(choose)
        source_widget = QWidget()
        source_widget.setLayout(source_row)
        form.addRow("Paket adı", self.addon_title)
        form.addRow("Paket ID", self.addon_id)
        form.addRow("Paket sürümü", self.addon_version)
        form.addRow("Kaynak klasör", source_widget)
        form.addRow("Açıklama", self.addon_description)
        outer.addWidget(form_card)

        self.addon_plan = QLabel(
            "Paket klasörü seçildiğinde Balanced Direct Stream planı hesaplanır. Temp BIN kullanılmaz."
        )
        self.addon_plan.setWordWrap(True)
        self.addon_plan.setStyleSheet(
            "background:#101923;border:1px solid #223448;padding:12px;color:#b9c9d8"
        )
        outer.addWidget(self.addon_plan)

        existing_header = QHBoxLayout()
        existing_title = QLabel("BU SÜRÜME BAĞLI EK PAKETLER")
        existing_title.setObjectName("cardTitle")
        self.addon_delete_button = QPushButton("Seçili ek paketi sil")
        self.addon_delete_button.setObjectName("danger")
        self.addon_delete_button.setEnabled(False)
        self.addon_delete_button.clicked.connect(self.delete_selected_addon)
        existing_header.addWidget(existing_title)
        existing_header.addStretch()
        existing_header.addWidget(self.addon_delete_button)
        outer.addLayout(existing_header)

        self.addon_tree = QTreeWidget()
        self.addon_tree.setHeaderLabels(["Paket", "Sürüm", "Boyut", "Release tag"])
        self.addon_tree.setMinimumHeight(150)
        self.addon_tree.setMaximumHeight(230)
        self.addon_tree.itemSelectionChanged.connect(
            lambda: self.addon_delete_button.setEnabled(
                bool(self.addon_tree.currentItem()) and self.addon_worker is None and self.addon_delete_worker is None
            )
        )
        outer.addWidget(self.addon_tree)

        self.addon_progress = QProgressBar()
        self.addon_logs = QPlainTextEdit()
        self.addon_logs.setReadOnly(True)
        self.addon_logs.setMinimumHeight(120)
        self.addon_logs.setMaximumHeight(170)
        self.addon_publish_button = QPushButton("Ek paketi GitHub'a yayınla")
        self.addon_publish_button.setObjectName("primary")
        self.addon_publish_button.clicked.connect(self.publish_addon)
        outer.addWidget(self.addon_progress)
        outer.addWidget(self.addon_logs)
        outer.addWidget(self.addon_publish_button)
        outer.addStretch()
        return page

    def _client(self):
        p = self._params()
        return GitHubClient(p["token"], p["owner"], p["repo"], p["branch"])

    def refresh_addon_catalog(self, checked=False, silent=False):
        del checked
        try:
            client = self._client()
            self.addon_catalog = load_catalog(client)
            current = self.addon_target.currentData() if hasattr(self, "addon_target") else None
            current_key = ""
            if current:
                current_key = "|".join(
                    str(current.get(k) or "")
                    for k in ("platform", "game_id", "channel", "base_version")
                )
            self.addon_target.blockSignals(True)
            self.addon_target.clear()
            restore = -1
            for game in sorted(
                self.addon_catalog.get("games", []),
                key=lambda g: str(g.get("title") or "").lower(),
            ):
                for channel, data in sorted((game.get("channels") or {}).items()):
                    record = {
                        "game_id": str(game.get("id") or ""),
                        "title": str(game.get("title") or game.get("id") or ""),
                        "platform": str(game.get("platform") or ""),
                        "channel": str(channel),
                        "base_version": str(data.get("version") or ""),
                        "channel_data": data,
                    }
                    label = (
                        f"{record['title']}  •  {record['platform'].upper()}  •  "
                        f"{record['channel']}  •  v{record['base_version']}"
                    )
                    self.addon_target.addItem(label, record)
                    key = "|".join(
                        str(record.get(k) or "")
                        for k in ("platform", "game_id", "channel", "base_version")
                    )
                    if key == current_key:
                        restore = self.addon_target.count() - 1
            if restore >= 0:
                self.addon_target.setCurrentIndex(restore)
            self.addon_target.blockSignals(False)
            self._sync_addon_target()
        except Exception as exc:
            if not silent:
                QMessageBox.critical(self, "Katalog okunamadı", str(exc))

    def _sync_addon_target(self):
        if not hasattr(self, "addon_tree"):
            return
        record = self.addon_target.currentData()
        self.addon_tree.clear()
        self.addon_delete_button.setEnabled(False)
        if not record:
            self.addon_base_info.setText("Katalogda yayınlanmış oyun bulunamadı.")
            self.addon_publish_button.setEnabled(False)
            return
        self.addon_publish_button.setEnabled(self.addon_worker is None and self.addon_delete_worker is None)
        self.addon_base_info.setText(
            f"{record['title']} • {record['platform'].upper()} • {record['channel']} • "
            f"ana sürüm v{record['base_version']}"
        )
        for package in (record.get("channel_data") or {}).get("optional_packages") or []:
            item = QTreeWidgetItem([
                str(package.get("title") or package.get("id") or "?"),
                str(package.get("version") or "?"),
                format_bytes(int(package.get("size") or 0)),
                str(package.get("tag") or ""),
            ])
            item.setData(0, Qt.UserRole, str(package.get("id") or ""))
            self.addon_tree.addTopLevelItem(item)

    def pick_addon_source(self):
        path = QFileDialog.getExistingDirectory(self, "Ek paket kaynak klasörü")
        if not path:
            return
        self.addon_source.setText(path)
        try:
            builder = ChunkBuilder(Path(path))
            plan = choose_upload_plan(builder.total_size)
            wave_text = "tek dalga" if int(plan["waves"]) == 1 else f"{plan['waves']} tam dalga"
            self.addon_plan.setText(
                f"Paket: <b>{format_bytes(builder.total_size)}</b> • "
                f"{plan['chunk_count']} chunk • hedef {format_bytes(int(plan['chunk_size']))}<br>"
                f"Upload: <b>{plan['workers']} paralel stream × {wave_text}</b> • Temp BIN: 0 B"
            )
        except Exception as exc:
            self.addon_plan.setText(f"Plan hatası: {exc}")

    def publish(self):
        """Protect attached packages from being orphaned by a base-version swap."""
        try:
            client = self._client()
            catalog = load_catalog(client)
            game_id = slugify(self.game_title.text().strip())
            platform = slugify(self.platform.currentText())
            channel = slugify(self.channel.currentText())
            new_version = self.version.text().strip()
            game = next(
                (
                    item
                    for item in catalog.get("games", [])
                    if item.get("id") == game_id and item.get("platform") == platform
                ),
                None,
            )
            current = ((game or {}).get("channels") or {}).get(channel)
            packages = list((current or {}).get("optional_packages") or [])
            if packages and str((current or {}).get("version") or "") != new_version:
                names = ", ".join(str(p.get("title") or p.get("id") or "?") for p in packages[:5])
                if len(packages) > 5:
                    names += f" (+{len(packages) - 5})"
                QMessageBox.warning(
                    self,
                    "Ek paketler bağlı",
                    "Bu kanalın mevcut sürümüne isteğe bağlı paketler bağlı. Ana sürümü değiştirirsek bu paketler "
                    "eski base sürümüne ait kalır.\n\n"
                    f"Bağlı paketler: {names}\n\n"
                    "Önce Ek Paketler sekmesinden bu paketleri sil, ardından yeni ana sürümü yayınla. "
                    "Yeni base yayınlandıktan sonra paketlerin uyumlu sürümlerini yeniden ekleyebilirsin.",
                )
                return
        except Exception as exc:
            # Publishing already performs its own connection/permission checks;
            # if catalog preflight itself fails, do not silently bypass it.
            QMessageBox.critical(self, "Yayın ön kontrolü başarısız", str(exc))
            return
        super().publish()

    def publish_addon(self):
        target = self.addon_target.currentData()
        if not target:
            QMessageBox.warning(self, "Ana oyun gerekli", "Önce yayınlanmış ana oyun/sürüm seç.")
            return
        if not self.addon_source.text().strip():
            QMessageBox.warning(self, "Kaynak gerekli", "Ek paketin klasörünü seç.")
            return
        if not self.addon_title.text().strip():
            QMessageBox.warning(self, "Paket adı gerekli", "Ek paket için görünen bir ad gir.")
            return
        if not self.token.text().strip():
            QMessageBox.warning(self, "Token gerekli", "GitHub sekmesindeki mevcut PAT gerekli.")
            return

        package_id = slugify(self.addon_id.text().strip() or self.addon_title.text())
        existing = next(
            (
                item
                for item in (target.get("channel_data") or {}).get("optional_packages") or []
                if slugify(str(item.get("id") or "")) == package_id
            ),
            None,
        )
        if existing:
            QMessageBox.warning(
                self,
                "Paket ID zaten kullanılıyor",
                f"{package_id} ID'li paket zaten bu sürüme bağlı. Eski Release'i yetim bırakmamak için "
                "önce listeden mevcut paketi sil, sonra yeni paket sürümünü yayınla.",
            )
            return

        params = {
            **self._params(),
            **target,
            "source": self.addon_source.text().strip(),
            "package_title": self.addon_title.text().strip(),
            "package_id": package_id,
            "package_version": self.addon_version.text().strip() or "1.0.0",
            "description": self.addon_description.toPlainText().strip(),
        }
        params.pop("channel_data", None)
        self.addon_progress.setValue(0)
        self.addon_logs.clear()
        self.addon_logs.appendPlainText(
            f"Ana oyun: {target['title']} v{target['base_version']} ({target['channel']})"
        )
        self.addon_logs.appendPlainText(f"Paket klasörü: {params['source']}")
        self.addon_publish_button.setEnabled(False)
        self.addon_delete_button.setEnabled(False)

        self.addon_thread = QThread()
        self.addon_worker = OptionalPackageWorker(params)
        self.addon_worker.moveToThread(self.addon_thread)
        self.addon_thread.started.connect(self.addon_worker.run)
        self.addon_worker.progress.connect(self.addon_progress.setValue)
        self.addon_worker.log.connect(self.addon_logs.appendPlainText)
        self.addon_worker.done.connect(self._addon_done)
        self.addon_worker.error.connect(self._addon_error)
        self.addon_worker.done.connect(self.addon_thread.quit)
        self.addon_worker.error.connect(self.addon_thread.quit)
        self.addon_thread.start()

    def _addon_done(self, manifest: dict):
        self.addon_progress.setValue(100)
        package = manifest.get("package") or {}
        self.addon_logs.appendPlainText("✓ Ek paket yayınlandı ve catalog.json güncellendi.")
        self.addon_worker = None
        self.refresh_addon_catalog(silent=True)
        QMessageBox.information(
            self,
            "Ek paket yayınlandı",
            f"{package.get('title') or package.get('id')} v{package.get('version')} hazır.\n\n"
            "Launcher bu paketi isteğe bağlı olarak gösterecek.",
        )

    def _addon_error(self, message: str):
        self.addon_worker = None
        self.addon_publish_button.setEnabled(True)
        self.addon_logs.appendPlainText(f"HATA: {message}")
        self._sync_addon_target()
        QMessageBox.critical(self, "Ek paket yayınlama hatası", message)

    def delete_selected_addon(self):
        target = self.addon_target.currentData()
        item = self.addon_tree.currentItem()
        if not target or item is None:
            return
        package_id = slugify(str(item.data(0, Qt.UserRole) or ""))
        title = item.text(0) or package_id
        if not package_id:
            return
        answer = QMessageBox.question(
            self,
            "Ek paket yayından kaldırılsın mı?",
            f"{title} paketi GitHub'dan tamamen kaldırılacak:\n\n"
            "• Paket Release'i ve chunk assetleri\n"
            "• Paket Git tag'i\n"
            "• Paket manifesti\n"
            "• catalog.json içindeki paket kaydı\n\n"
            "Ana oyun Release'ine ve dosyalarına dokunulmaz. Devam edilsin mi?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        params = {
            **self._params(),
            "game_id": target["game_id"],
            "platform": target["platform"],
            "channel": target["channel"],
            "package_id": package_id,
        }
        self.addon_logs.clear()
        self.addon_logs.appendPlainText(f"Ek paket yayından kaldırılıyor: {title}")
        self.addon_progress.setRange(0, 0)
        self.addon_publish_button.setEnabled(False)
        self.addon_delete_button.setEnabled(False)

        self.addon_delete_thread = QThread()
        self.addon_delete_worker = OptionalPackageDeleteWorker(params)
        self.addon_delete_worker.moveToThread(self.addon_delete_thread)
        self.addon_delete_thread.started.connect(self.addon_delete_worker.run)
        self.addon_delete_worker.log.connect(self.addon_logs.appendPlainText)
        self.addon_delete_worker.done.connect(lambda result, t=title: self._addon_delete_done(t, result))
        self.addon_delete_worker.error.connect(self._addon_delete_error)
        self.addon_delete_worker.done.connect(self.addon_delete_thread.quit)
        self.addon_delete_worker.error.connect(self.addon_delete_thread.quit)
        self.addon_delete_thread.start()

    def _addon_delete_done(self, title: str, result: dict):
        self.addon_delete_worker = None
        self.addon_progress.setRange(0, 100)
        self.addon_progress.setValue(100)
        self.addon_logs.appendPlainText("✓ Ek paket Release/tag/manifest/catalog kaydı temizlendi.")
        self.refresh_addon_catalog(silent=True)
        QMessageBox.information(
            self,
            "Ek paket silindi",
            f"{title} yayından kaldırıldı. Ana oyun yayını değişmedi.",
        )

    def _addon_delete_error(self, message: str):
        self.addon_delete_worker = None
        self.addon_progress.setRange(0, 100)
        self.addon_progress.setValue(0)
        self.addon_logs.appendPlainText(f"HATA: {message}")
        self._sync_addon_target()
        QMessageBox.critical(self, "Ek paket silme hatası", message)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Drowned Release Manager")
    app.setOrganizationName("Drowned")
    app.setStyle("Fusion")
    app.setStyleSheet(previous.previous.previous.previous.previous.MODERN_STYLE)
    win = Manager()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
