from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import quote

import requests
from PySide6.QtCore import QObject, QSettings, QThread, Qt, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QFileDialog, QFormLayout, QFrame,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow,
    QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QSplitter,
    QVBoxLayout, QWidget
)

from drowned_shared.install import fetch_json, install_manifest
from drowned_shared.util import format_bytes

APP_VERSION = "0.3.0"

STYLE = """
QWidget { background:#171a21; color:#d6d7d8; font-family:'Segoe UI'; font-size:14px; }
QMainWindow { background:#171a21; }
QFrame#topbar { background:#171a21; border-bottom:1px solid #101318; }
QFrame#sidebar { background:#1b2838; border-right:1px solid #0e141c; }
QFrame#detail { background:#1b2838; }
QFrame#gameInfo { background:#16202d; border:1px solid #26384c; }
QFrame#downloadBar { background:#111820; border-top:1px solid #2b3c4f; }
QLabel#brand { color:#ffffff; font-size:24px; font-weight:900; letter-spacing:3px; }
QLabel#navActive { color:#ffffff; font-size:16px; font-weight:800; border-bottom:3px solid #1a9fff; padding:12px 8px; }
QLabel#nav { color:#8f98a0; font-size:16px; font-weight:700; padding:12px 8px; }
QLabel#gameTitle { color:white; font-size:28px; font-weight:800; }
QLabel#muted { color:#8f98a0; }
QLabel#section { color:#c7d5e0; font-size:14px; font-weight:800; letter-spacing:1px; }
QLineEdit, QComboBox { background:#0e1621; border:1px solid #31465c; border-radius:4px; padding:8px 10px; color:#d6d7d8; }
QLineEdit:focus, QComboBox:focus { border-color:#66c0f4; }
QListWidget { background:#1b2838; border:0; outline:0; padding:4px 0; }
QListWidget::item { color:#c7d5e0; padding:10px 12px; border-left:3px solid transparent; }
QListWidget::item:hover { background:#243447; color:white; }
QListWidget::item:selected { background:#2a475e; color:white; border-left:3px solid #66c0f4; }
QPushButton { background:#2a475e; color:#d6d7d8; border:0; border-radius:3px; padding:9px 15px; font-weight:700; }
QPushButton:hover { background:#35617d; color:white; }
QPushButton#install { background:#75b022; color:#e5f7cf; font-size:16px; padding:12px 22px; }
QPushButton#install:hover { background:#8bc53f; }
QPushButton#secondary { background:#23384b; color:#c7d5e0; }
QProgressBar { background:#0d141d; border:1px solid #30445a; border-radius:4px; text-align:center; min-height:14px; color:#d6d7d8; }
QProgressBar::chunk { background:#66c0f4; }
QPlainTextEdit { background:#0c1219; border:1px solid #26384c; color:#9fb0bf; padding:7px; }
QSplitter::handle { background:#0e141c; width:1px; }
"""


def raw_repo_url(owner: str, repo: str, branch: str, path: str) -> str:
    encoded = "/".join(quote(part, safe="") for part in path.strip("/").split("/"))
    return f"https://raw.githubusercontent.com/{quote(owner, safe='')}/{quote(repo, safe='')}/{quote(branch or 'main', safe='')}/{encoded}"


class CatalogWorker(QObject):
    done = Signal(dict)
    error = Signal(str)

    def __init__(self, url: str):
        super().__init__()
        self.url = url

    def run(self):
        try:
            response = requests.get(self.url, timeout=25, headers={"User-Agent": "Drowned-Launcher/0.3", "Cache-Control": "no-cache"})
            response.raise_for_status()
            data = response.json()
            if data.get("schema_version") != 1:
                raise RuntimeError("Desteklenmeyen catalog schema_version")
            self.done.emit(data)
        except Exception as exc:
            self.error.emit(str(exc))


class ArtworkWorker(QObject):
    done = Signal(object)

    def __init__(self, artwork: dict):
        super().__init__()
        self.artwork = artwork

    def run(self):
        result = {}
        for kind in ("hero", "cover", "logo"):
            url = self.artwork.get(kind)
            if not url:
                continue
            try:
                response = requests.get(url, timeout=12, headers={"User-Agent": "Drowned-Launcher/0.3"})
                response.raise_for_status()
                result[kind] = response.content
            except Exception:
                pass
        self.done.emit(result)


class InstallWorker(QObject):
    progress = Signal(int, str)
    done = Signal()
    error = Signal(str)
    log = Signal(str)

    def __init__(self, url: str, target: str):
        super().__init__()
        self.url = url
        self.target = Path(target)
        self.cancelled = False

    def run(self):
        try:
            manifest = fetch_json(self.url)
            install_manifest(
                manifest,
                self.target,
                lambda done, total: self.progress.emit(int(done * 100 / max(total, 1)), f"{format_bytes(done)} / {format_bytes(total)}"),
                self.log.emit,
                lambda: self.cancelled,
            )
            self.done.emit()
        except Exception as exc:
            self.error.emit(str(exc))


class HeroView(QFrame):
    def __init__(self):
        super().__init__()
        self.setMinimumHeight(360)
        self.hero = QPixmap()
        self.logo = QPixmap()
        self.fallback_title = "DROWNED"

    def set_art(self, hero: QPixmap | None, logo: QPixmap | None, title: str):
        self.hero = hero or QPixmap()
        self.logo = logo or QPixmap()
        self.fallback_title = title
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        rect = self.rect()
        if not self.hero.isNull():
            scaled = self.hero.scaled(rect.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            sx = max((scaled.width() - rect.width()) // 2, 0)
            sy = max((scaled.height() - rect.height()) // 2, 0)
            painter.drawPixmap(rect, scaled, scaled.rect().adjusted(sx, sy, -sx, -sy))
        else:
            painter.fillRect(rect, QColor("#0d1824"))
        gradient = QLinearGradient(0, 0, 0, rect.height())
        gradient.setColorAt(0.0, QColor(10, 15, 22, 20))
        gradient.setColorAt(0.58, QColor(10, 15, 22, 55))
        gradient.setColorAt(1.0, QColor(10, 15, 22, 240))
        painter.fillRect(rect, gradient)
        side = QLinearGradient(0, 0, rect.width() * 0.55, 0)
        side.setColorAt(0.0, QColor(10, 15, 22, 190))
        side.setColorAt(1.0, QColor(10, 15, 22, 0))
        painter.fillRect(rect, side)
        if not self.logo.isNull():
            target = self.logo.scaled(430, 150, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            painter.drawPixmap(34, rect.height() - target.height() - 34, target)
        else:
            painter.setPen(QColor("#ffffff"))
            font = painter.font()
            font.setPointSize(28)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(34, rect.height() - 55, self.fallback_title)
        painter.end()
        super().paintEvent(event)


class SettingsDialog(QDialog):
    saved = Signal(str, str, str)

    def __init__(self, parent, owner: str, repo: str, branch: str):
        super().__init__(parent)
        self.setWindowTitle("Drowned Launcher Ayarları")
        self.resize(480, 250)
        layout = QVBoxLayout(self)
        title = QLabel("Katalog kaynağı")
        title.setStyleSheet("font-size:22px;font-weight:800;color:white")
        layout.addWidget(title)
        form = QFormLayout()
        self.owner = QLineEdit(owner)
        self.repo = QLineEdit(repo)
        self.branch = QLineEdit(branch)
        form.addRow("GitHub owner", self.owner)
        form.addRow("Repository", self.repo)
        form.addRow("Branch", self.branch)
        layout.addLayout(form)
        note = QLabel("Katalog, manifest ve artwork mümkün olduğunca raw.githubusercontent.com üzerinden okunur.")
        note.setWordWrap(True)
        note.setObjectName("muted")
        layout.addWidget(note)
        row = QHBoxLayout()
        save = QPushButton("Kaydet ve yenile")
        save.clicked.connect(self.accept_and_save)
        cancel = QPushButton("İptal")
        cancel.setObjectName("secondary")
        cancel.clicked.connect(self.reject)
        row.addStretch()
        row.addWidget(cancel)
        row.addWidget(save)
        layout.addLayout(row)

    def accept_and_save(self):
        self.saved.emit(self.owner.text().strip(), self.repo.text().strip(), self.branch.text().strip() or "main")
        self.accept()


class Launcher(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Drowned Launcher {APP_VERSION}")
        self.resize(1480, 900)
        self.setMinimumSize(1080, 700)
        self.settings = QSettings("Drowned", "Launcher")
        self.owner = self.settings.value("owner", "thedrowned925")
        self.repo = self.settings.value("repo", "drowned1")
        self.branch = self.settings.value("branch", "main")
        self.catalog = {"games": []}
        self.current_game = None
        self.current_channel = "stable"
        self.catalog_thread = None
        self.catalog_worker = None
        self.art_thread = None
        self.art_worker = None
        self.install_thread = None
        self.install_worker = None
        self._build_ui()
        self.load_catalog()

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        top = QFrame()
        top.setObjectName("topbar")
        top.setFixedHeight(72)
        top_layout = QHBoxLayout(top)
        top_layout.setContentsMargins(22, 0, 18, 0)
        brand = QLabel("DROWNED")
        brand.setObjectName("brand")
        library_nav = QLabel("KÜTÜPHANE")
        library_nav.setObjectName("navActive")
        downloads_nav = QLabel("İNDİRMELER")
        downloads_nav.setObjectName("nav")
        top_layout.addWidget(brand)
        top_layout.addSpacing(34)
        top_layout.addWidget(library_nav)
        top_layout.addWidget(downloads_nav)
        top_layout.addStretch()
        self.connection = QLabel("RAW • bağlanıyor")
        self.connection.setObjectName("muted")
        refresh = QPushButton("↻")
        refresh.setFixedWidth(42)
        refresh.setToolTip("Kataloğu yenile")
        refresh.clicked.connect(self.load_catalog)
        settings_button = QPushButton("⚙")
        settings_button.setFixedWidth(42)
        settings_button.setToolTip("Ayarlar")
        settings_button.clicked.connect(self.open_settings)
        top_layout.addWidget(self.connection)
        top_layout.addSpacing(8)
        top_layout.addWidget(refresh)
        top_layout.addWidget(settings_button)
        outer.addWidget(top)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setMinimumWidth(260)
        sidebar.setMaximumWidth(360)
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(12, 14, 12, 12)
        label = QLabel("OYUNLAR")
        label.setObjectName("section")
        self.search = QLineEdit()
        self.search.setPlaceholderText("Kütüphanede ara")
        self.search.textChanged.connect(self.render_library)
        filter_row = QHBoxLayout()
        self.platform = QComboBox()
        self.platform.addItem("Tümü")
        self.channel = QComboBox()
        self.channel.addItems(["stable", "beta", "dev", "nightly", "archive"])
        self.platform.currentTextChanged.connect(self.render_library)
        self.channel.currentTextChanged.connect(self.render_library)
        filter_row.addWidget(self.platform, 1)
        filter_row.addWidget(self.channel, 1)
        self.library = QListWidget()
        self.library.currentItemChanged.connect(self.library_selection_changed)
        side_layout.addWidget(label)
        side_layout.addWidget(self.search)
        side_layout.addLayout(filter_row)
        side_layout.addWidget(self.library, 1)
        count_row = QHBoxLayout()
        self.game_count = QLabel("0 oyun")
        self.game_count.setObjectName("muted")
        count_row.addWidget(self.game_count)
        count_row.addStretch()
        side_layout.addLayout(count_row)

        detail = QFrame()
        detail.setObjectName("detail")
        detail_layout = QVBoxLayout(detail)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        detail_layout.setSpacing(0)
        self.hero = HeroView()
        detail_layout.addWidget(self.hero)
        content = QFrame()
        content.setObjectName("gameInfo")
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(26, 22, 26, 24)
        content_layout.setSpacing(24)
        self.cover = QLabel("COVER")
        self.cover.setFixedSize(190, 285)
        self.cover.setAlignment(Qt.AlignCenter)
        self.cover.setStyleSheet("background:#0b1118;border:1px solid #2e4258;color:#657789")
        content_layout.addWidget(self.cover)
        right = QVBoxLayout()
        self.title = QLabel("Kütüphane yükleniyor…")
        self.title.setObjectName("gameTitle")
        self.meta = QLabel("")
        self.meta.setStyleSheet("color:#66c0f4;font-weight:700")
        self.description = QLabel("Raw GitHub kataloğundan oyunlar yükleniyor.")
        self.description.setWordWrap(True)
        self.description.setAlignment(Qt.AlignTop)
        self.description.setStyleSheet("color:#b8c2ca")
        buttons = QHBoxLayout()
        self.install_button = QPushButton("YÜKLE")
        self.install_button.setObjectName("install")
        self.install_button.clicked.connect(self.install_current_game)
        self.install_button.setEnabled(False)
        self.verify_button = QPushButton("DOSYALARI DOĞRULA")
        self.verify_button.setObjectName("secondary")
        self.verify_button.setEnabled(False)
        buttons.addWidget(self.install_button)
        buttons.addWidget(self.verify_button)
        buttons.addStretch()
        right.addWidget(self.title)
        right.addWidget(self.meta)
        right.addSpacing(10)
        right.addWidget(self.description, 1)
        right.addLayout(buttons)
        content_layout.addLayout(right, 1)
        detail_layout.addWidget(content, 1)
        splitter.addWidget(sidebar)
        splitter.addWidget(detail)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([300, 1180])
        outer.addWidget(splitter, 1)

        download = QFrame()
        download.setObjectName("downloadBar")
        dl = QVBoxLayout(download)
        dl.setContentsMargins(16, 8, 16, 9)
        status_row = QHBoxLayout()
        self.status = QLabel("Hazır")
        self.status.setObjectName("muted")
        self.progress_text = QLabel("")
        self.progress_text.setStyleSheet("color:#66c0f4;font-weight:700")
        status_row.addWidget(self.status)
        status_row.addStretch()
        status_row.addWidget(self.progress_text)
        self.progress = QProgressBar()
        self.progress.setValue(0)
        self.logs = QPlainTextEdit()
        self.logs.setReadOnly(True)
        self.logs.setFixedHeight(60)
        self.logs.hide()
        dl.addLayout(status_row)
        dl.addWidget(self.progress)
        dl.addWidget(self.logs)
        outer.addWidget(download)

    def open_settings(self):
        dialog = SettingsDialog(self, self.owner, self.repo, self.branch)
        dialog.saved.connect(self.apply_settings)
        dialog.exec()

    def apply_settings(self, owner: str, repo: str, branch: str):
        self.owner, self.repo, self.branch = owner, repo, branch
        self.settings.setValue("owner", owner)
        self.settings.setValue("repo", repo)
        self.settings.setValue("branch", branch)
        self.load_catalog()

    def load_catalog(self):
        self.connection.setText("RAW • yükleniyor")
        self.status.setText("Katalog yenileniyor…")
        url = raw_repo_url(self.owner, self.repo, self.branch, "catalog.json")
        self.catalog_thread = QThread()
        self.catalog_worker = CatalogWorker(url)
        self.catalog_worker.moveToThread(self.catalog_thread)
        self.catalog_thread.started.connect(self.catalog_worker.run)
        self.catalog_worker.done.connect(self.catalog_loaded)
        self.catalog_worker.error.connect(self.catalog_error)
        self.catalog_worker.done.connect(self.catalog_thread.quit)
        self.catalog_worker.error.connect(self.catalog_thread.quit)
        self.catalog_thread.start()

    def catalog_loaded(self, data: dict):
        self.catalog = data
        platforms = sorted({g.get("platform", "").upper() for g in data.get("games", []) if g.get("platform")})
        current = self.platform.currentText()
        self.platform.blockSignals(True)
        self.platform.clear()
        self.platform.addItem("Tümü")
        self.platform.addItems(platforms)
        index = self.platform.findText(current)
        if index >= 0:
            self.platform.setCurrentIndex(index)
        self.platform.blockSignals(False)
        self.connection.setText("RAW • çevrimiçi")
        self.status.setText(f"Katalog güncel • {len(data.get('games', []))} oyun")
        self.render_library()

    def catalog_error(self, message: str):
        self.connection.setText("RAW • bağlantı hatası")
        self.status.setText("Katalog yüklenemedi")
        QMessageBox.critical(self, "Katalog hatası", f"Raw katalog yüklenemedi:\n{message}\n\nKaynak: {self.owner}/{self.repo}@{self.branch}")

    def render_library(self):
        selected_key = None
        current = self.library.currentItem()
        if current:
            payload = current.data(Qt.UserRole)
            if payload:
                selected_key = (payload[0].get("id"), payload[0].get("platform"), payload[1])
        query = self.search.text().strip().lower()
        platform = self.platform.currentText()
        channel = self.channel.currentText()
        self.current_channel = channel
        items = []
        for game in self.catalog.get("games", []):
            if platform != "Tümü" and game.get("platform", "").upper() != platform:
                continue
            if channel not in (game.get("channels") or {}):
                continue
            if query and query not in game.get("title", "").lower():
                continue
            items.append(game)
        items.sort(key=lambda g: g.get("title", "").lower())
        self.library.blockSignals(True)
        self.library.clear()
        selected_row = -1
        for row, game in enumerate(items):
            data = game["channels"][channel]
            item = QListWidgetItem(f"{game.get('title', 'Untitled')}\n{game.get('platform', '').upper()}  •  v{data.get('version', '?')}")
            item.setData(Qt.UserRole, (game, channel))
            self.library.addItem(item)
            if selected_key == (game.get("id"), game.get("platform"), channel):
                selected_row = row
        self.library.blockSignals(False)
        self.game_count.setText(f"{len(items)} oyun")
        if items:
            self.library.setCurrentRow(selected_row if selected_row >= 0 else 0)
            self.library_selection_changed(self.library.currentItem(), None)
        else:
            self.show_empty_state()

    def show_empty_state(self):
        self.current_game = None
        self.title.setText("Bu filtrede oyun yok")
        self.meta.setText("")
        self.description.setText("Platform, kanal veya arama filtresini değiştir.")
        self.cover.clear()
        self.cover.setText("COVER")
        self.hero.set_art(None, None, "DROWNED")
        self.install_button.setEnabled(False)

    def library_selection_changed(self, current, previous):
        if not current:
            return
        payload = current.data(Qt.UserRole)
        if not payload:
            return
        game, channel = payload
        self.current_game = game
        self.current_channel = channel
        data = game["channels"][channel]
        self.title.setText(game.get("title", "Untitled"))
        self.meta.setText(f"{game.get('platform', '').upper()}  •  {channel.upper()}  •  v{data.get('version', '?')}  •  {format_bytes(int(data.get('size', 0)))}")
        self.description.setText(game.get("description") or "Bu oyun için açıklama eklenmemiş.")
        self.cover.clear()
        self.cover.setText("COVER")
        self.hero.set_art(None, None, game.get("title", "DROWNED"))
        self.install_button.setEnabled(True)
        self.install_button.setText("YÜKLE")
        self.load_artwork(game.get("artwork") or {})

    def load_artwork(self, artwork: dict):
        if not artwork:
            return
        self.art_thread = QThread()
        self.art_worker = ArtworkWorker(artwork)
        self.art_worker.moveToThread(self.art_thread)
        self.art_thread.started.connect(self.art_worker.run)
        self.art_worker.done.connect(self.artwork_loaded)
        self.art_worker.done.connect(self.art_thread.quit)
        self.art_thread.start()

    def artwork_loaded(self, raw: dict):
        hero = None
        logo = None
        if raw.get("hero"):
            hero = QPixmap()
            hero.loadFromData(raw["hero"])
        if raw.get("logo"):
            logo = QPixmap()
            logo.loadFromData(raw["logo"])
        if raw.get("cover"):
            cover = QPixmap()
            cover.loadFromData(raw["cover"])
            self.cover.setPixmap(cover.scaled(self.cover.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation))
        if self.current_game:
            self.hero.set_art(hero, logo, self.current_game.get("title", "DROWNED"))

    def install_current_game(self):
        if not self.current_game:
            return
        game = self.current_game
        channel = self.current_channel
        data = game["channels"][channel]
        folder = QFileDialog.getExistingDirectory(self, f"{game['title']} için kurulum klasörü")
        if not folder:
            return
        manifest_url = data.get("manifest_url", "")
        if data.get("manifest_path"):
            manifest_url = raw_repo_url(self.owner, self.repo, self.branch, data["manifest_path"])
        if not manifest_url:
            QMessageBox.critical(self, "Manifest hatası", "Bu yayın için manifest adresi bulunamadı.")
            return
        target = Path(folder) / game["title"]
        self.progress.setValue(0)
        self.progress_text.setText("Hazırlanıyor")
        self.status.setText(f"{game['title']} indiriliyor")
        self.logs.clear()
        self.logs.show()
        self.install_button.setEnabled(False)
        self.install_button.setText("İNDİRİLİYOR…")
        self.install_thread = QThread()
        self.install_worker = InstallWorker(manifest_url, str(target))
        self.install_worker.moveToThread(self.install_thread)
        self.install_thread.started.connect(self.install_worker.run)
        self.install_worker.progress.connect(self.install_progress)
        self.install_worker.log.connect(self.logs.appendPlainText)
        self.install_worker.done.connect(self.install_done)
        self.install_worker.error.connect(self.install_error)
        self.install_worker.done.connect(self.install_thread.quit)
        self.install_worker.error.connect(self.install_thread.quit)
        self.install_thread.start()

    def install_progress(self, percent: int, text: str):
        self.progress.setValue(percent)
        self.progress_text.setText(f"%{percent}  •  {text}")

    def install_done(self):
        self.progress.setValue(100)
        self.progress_text.setText("%100 • doğrulandı")
        self.status.setText("Kurulum tamamlandı")
        self.install_button.setEnabled(True)
        self.install_button.setText("YENİDEN YÜKLE")
        QMessageBox.information(self, "Tamamlandı", "Kurulum ve SHA-256 doğrulaması tamamlandı.")

    def install_error(self, message: str):
        self.status.setText("İndirme hatası")
        self.progress_text.setText("Hata")
        self.install_button.setEnabled(True)
        self.install_button.setText("TEKRAR DENE")
        QMessageBox.critical(self, "İndirme hatası", message)


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLE)
    win = Launcher()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
