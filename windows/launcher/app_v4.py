from __future__ import annotations

import json
import sys
import time
import traceback
import uuid
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit, parse_qsl, urlencode

import requests
from PySide6.QtCore import QObject, QRunnable, QSettings, QStandardPaths, QThreadPool, Qt, Signal, QRect
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QFileDialog, QFormLayout, QFrame,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow,
    QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QSplitter,
    QVBoxLayout, QWidget
)

from drowned_shared.install import fetch_json, install_manifest
from drowned_shared.util import format_bytes

APP_VERSION = "0.4.0"

STYLE = """
QWidget { background:#171a21; color:#d6d7d8; font-family:'Segoe UI'; font-size:14px; }
QMainWindow { background:#171a21; }
QFrame#topbar { background:#171a21; border-bottom:1px solid #101318; }
QFrame#sidebar { background:#1b2838; border-right:1px solid #0e141c; }
QFrame#detail { background:#1b2838; }
QFrame#gameInfo { background:#16202d; border-top:1px solid #26384c; }
QFrame#downloadBar { background:#111820; border-top:1px solid #2b3c4f; }
QLabel#brand { color:#ffffff; font-size:24px; font-weight:900; letter-spacing:3px; }
QLabel#navActive { color:#ffffff; font-size:16px; font-weight:800; border-bottom:3px solid #1a9fff; padding:12px 8px; }
QLabel#nav { color:#8f98a0; font-size:16px; font-weight:700; padding:12px 8px; }
QLabel#gameTitle { color:white; font-size:30px; font-weight:800; }
QLabel#muted { color:#8f98a0; }
QLabel#section { color:#c7d5e0; font-size:13px; font-weight:800; letter-spacing:1px; }
QLineEdit, QComboBox { background:#0e1621; border:1px solid #31465c; border-radius:4px; padding:8px 10px; color:#d6d7d8; }
QLineEdit:focus, QComboBox:focus { border-color:#66c0f4; }
QListWidget { background:#1b2838; border:0; outline:0; padding:4px 0; }
QListWidget::item { color:#c7d5e0; padding:10px 12px; border-left:3px solid transparent; }
QListWidget::item:hover { background:#243447; color:white; }
QListWidget::item:selected { background:#2a475e; color:white; border-left:3px solid #66c0f4; }
QPushButton { background:#2a475e; color:#d6d7d8; border:0; border-radius:3px; padding:9px 15px; font-weight:700; }
QPushButton:hover { background:#35617d; color:white; }
QPushButton#install { background:#75b022; color:#e5f7cf; font-size:16px; padding:12px 24px; }
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


def cache_bust(url: str) -> str:
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["drowned_ts"] = str(int(time.time() * 1000))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def app_data_dir() -> Path:
    p = Path(QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation))
    p.mkdir(parents=True, exist_ok=True)
    return p


class CatalogSignals(QObject):
    done = Signal(object, str)
    error = Signal(str)


class CatalogTask(QRunnable):
    def __init__(self, url: str, cache_path: Path):
        super().__init__()
        self.url = url
        self.cache_path = cache_path
        self.signals = CatalogSignals()

    def run(self):
        last_error = "Bilinmeyen hata"
        for attempt, delay in enumerate((0.0, 0.7, 1.5, 3.0), start=1):
            if delay:
                time.sleep(delay)
            try:
                response = requests.get(
                    cache_bust(self.url), timeout=(8, 18),
                    headers={"User-Agent": "Drowned-Launcher/0.4", "Cache-Control": "no-cache, no-store", "Pragma": "no-cache"},
                )
                response.raise_for_status()
                data = response.json()
                if data.get("schema_version") != 1 or not isinstance(data.get("games", []), list):
                    raise RuntimeError("Geçersiz catalog.json")
                tmp = self.cache_path.with_suffix(".tmp")
                tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                tmp.replace(self.cache_path)
                self.signals.done.emit(data, "raw")
                return
            except Exception as exc:
                last_error = f"Deneme {attempt}/4: {exc}"

        try:
            if self.cache_path.exists():
                data = json.loads(self.cache_path.read_text(encoding="utf-8"))
                if data.get("schema_version") == 1 and isinstance(data.get("games", []), list):
                    self.signals.done.emit(data, "cache")
                    return
        except Exception:
            pass
        self.signals.error.emit(last_error)


class ArtworkSignals(QObject):
    done = Signal(str, object)


class ArtworkTask(QRunnable):
    def __init__(self, token: str, artwork: dict):
        super().__init__()
        self.token = token
        self.artwork = artwork
        self.signals = ArtworkSignals()

    def run(self):
        result = {}
        for kind in ("hero", "cover", "logo"):
            url = self.artwork.get(kind)
            if not url:
                continue
            for delay in (0.0, 0.5, 1.2):
                if delay:
                    time.sleep(delay)
                try:
                    response = requests.get(
                        cache_bust(url), timeout=(6, 15),
                        headers={"User-Agent": "Drowned-Launcher/0.4", "Cache-Control": "no-cache"},
                    )
                    response.raise_for_status()
                    if response.content:
                        result[kind] = response.content
                        break
                except Exception:
                    continue
        self.signals.done.emit(self.token, result)


class InstallSignals(QObject):
    progress = Signal(int, str)
    log = Signal(str)
    done = Signal()
    error = Signal(str)


class InstallTask(QRunnable):
    def __init__(self, url: str, target: Path):
        super().__init__()
        self.url = url
        self.target = target
        self.signals = InstallSignals()

    def run(self):
        try:
            manifest = None
            last_error = None
            for delay in (0.0, 0.7, 1.5, 3.0):
                if delay:
                    time.sleep(delay)
                try:
                    manifest = fetch_json(cache_bust(self.url))
                    break
                except Exception as exc:
                    last_error = exc
            if manifest is None:
                raise RuntimeError(f"Manifest raw sunucusunda henüz hazır değil: {last_error}")
            install_manifest(
                manifest,
                self.target,
                lambda done, total: self.signals.progress.emit(
                    int(done * 100 / max(total, 1)), f"{format_bytes(done)} / {format_bytes(total)}"
                ),
                self.signals.log.emit,
                lambda: False,
            )
            self.signals.done.emit()
        except Exception as exc:
            self.signals.error.emit(str(exc))


class HeroView(QFrame):
    def __init__(self):
        super().__init__()
        self.setMinimumHeight(360)
        self.hero = QPixmap()
        self.logo = QPixmap()
        self.fallback_title = "DROWNED"

    def set_art(self, hero: QPixmap | None, logo: QPixmap | None, title: str):
        self.hero = hero if hero is not None else QPixmap()
        self.logo = logo if logo is not None else QPixmap()
        self.fallback_title = title or "DROWNED"
        self.update()

    def paintEvent(self, event):
        QFrame.paintEvent(self, event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        rect = self.rect()
        if not self.hero.isNull() and rect.width() > 0 and rect.height() > 0:
            scaled = self.hero.scaled(rect.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            sx = max((scaled.width() - rect.width()) // 2, 0)
            sy = max((scaled.height() - rect.height()) // 2, 0)
            source = QRect(sx, sy, min(rect.width(), scaled.width()), min(rect.height(), scaled.height()))
            painter.drawPixmap(rect, scaled, source)
        else:
            painter.fillRect(rect, QColor("#0d1824"))
        gradient = QLinearGradient(0, 0, 0, rect.height())
        gradient.setColorAt(0.0, QColor(10, 15, 22, 18))
        gradient.setColorAt(0.55, QColor(10, 15, 22, 65))
        gradient.setColorAt(1.0, QColor(10, 15, 22, 245))
        painter.fillRect(rect, gradient)
        side = QLinearGradient(0, 0, max(rect.width() * 0.65, 1), 0)
        side.setColorAt(0.0, QColor(10, 15, 22, 205))
        side.setColorAt(1.0, QColor(10, 15, 22, 0))
        painter.fillRect(rect, side)
        if not self.logo.isNull():
            target = self.logo.scaled(430, 150, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            painter.drawPixmap(34, max(rect.height() - target.height() - 34, 12), target)
        else:
            painter.setPen(QColor("#ffffff"))
            font = painter.font()
            font.setPointSize(28)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(34, max(rect.height() - 55, 45), self.fallback_title)
        painter.end()


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
        self.owner_edit = QLineEdit(owner)
        self.repo_edit = QLineEdit(repo)
        self.branch_edit = QLineEdit(branch)
        form.addRow("GitHub owner", self.owner_edit)
        form.addRow("Repository", self.repo_edit)
        form.addRow("Branch", self.branch_edit)
        layout.addLayout(form)
        note = QLabel("Katalog, manifest ve artwork raw.githubusercontent.com üzerinden okunur. Raw gecikirse Launcher birkaç kez yeniden dener ve son başarılı kataloğu cache'den gösterebilir.")
        note.setWordWrap(True)
        note.setObjectName("muted")
        layout.addWidget(note)
        row = QHBoxLayout()
        cancel = QPushButton("İptal")
        cancel.setObjectName("secondary")
        cancel.clicked.connect(self.reject)
        save = QPushButton("Kaydet ve yenile")
        save.clicked.connect(self.accept_and_save)
        row.addStretch(); row.addWidget(cancel); row.addWidget(save)
        layout.addLayout(row)

    def accept_and_save(self):
        self.saved.emit(self.owner_edit.text().strip(), self.repo_edit.text().strip(), self.branch_edit.text().strip() or "main")
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
        self.pool = QThreadPool.globalInstance()
        self.pool.setMaxThreadCount(max(4, self.pool.maxThreadCount()))
        self.catalog_loading = False
        self.art_token = ""
        self._build_ui()
        self.load_catalog()

    @property
    def catalog_cache_path(self) -> Path:
        return app_data_dir() / "catalog_cache.json"

    def _build_ui(self):
        root = QWidget(); self.setCentralWidget(root)
        outer = QVBoxLayout(root); outer.setContentsMargins(0,0,0,0); outer.setSpacing(0)
        top = QFrame(); top.setObjectName("topbar"); top.setFixedHeight(72)
        top_layout = QHBoxLayout(top); top_layout.setContentsMargins(22,0,18,0)
        brand = QLabel("DROWNED"); brand.setObjectName("brand")
        library_nav = QLabel("KÜTÜPHANE"); library_nav.setObjectName("navActive")
        downloads_nav = QLabel("İNDİRMELER"); downloads_nav.setObjectName("nav")
        top_layout.addWidget(brand); top_layout.addSpacing(34); top_layout.addWidget(library_nav); top_layout.addWidget(downloads_nav); top_layout.addStretch()
        self.connection = QLabel("RAW • bağlanıyor"); self.connection.setObjectName("muted")
        refresh = QPushButton("↻"); refresh.setFixedWidth(42); refresh.setToolTip("Kataloğu yenile"); refresh.clicked.connect(self.load_catalog)
        settings_button = QPushButton("⚙"); settings_button.setFixedWidth(42); settings_button.setToolTip("Ayarlar"); settings_button.clicked.connect(self.open_settings)
        top_layout.addWidget(self.connection); top_layout.addSpacing(8); top_layout.addWidget(refresh); top_layout.addWidget(settings_button); outer.addWidget(top)

        splitter = QSplitter(Qt.Horizontal); splitter.setChildrenCollapsible(False)
        sidebar = QFrame(); sidebar.setObjectName("sidebar"); sidebar.setMinimumWidth(260); sidebar.setMaximumWidth(360)
        side_layout = QVBoxLayout(sidebar); side_layout.setContentsMargins(12,14,12,12)
        label = QLabel("OYUNLAR"); label.setObjectName("section")
        self.search = QLineEdit(); self.search.setPlaceholderText("Kütüphanede ara"); self.search.textChanged.connect(self.render_library)
        filter_row = QHBoxLayout(); self.platform = QComboBox(); self.platform.addItem("Tümü"); self.channel = QComboBox(); self.channel.addItems(["stable","beta","dev","nightly","archive"])
        self.platform.currentTextChanged.connect(self.render_library); self.channel.currentTextChanged.connect(self.render_library)
        filter_row.addWidget(self.platform,1); filter_row.addWidget(self.channel,1)
        self.library = QListWidget(); self.library.currentItemChanged.connect(self.library_selection_changed)
        side_layout.addWidget(label); side_layout.addWidget(self.search); side_layout.addLayout(filter_row); side_layout.addWidget(self.library,1)
        self.game_count = QLabel("0 oyun"); self.game_count.setObjectName("muted"); side_layout.addWidget(self.game_count)

        detail = QFrame(); detail.setObjectName("detail"); detail_layout = QVBoxLayout(detail); detail_layout.setContentsMargins(0,0,0,0); detail_layout.setSpacing(0)
        self.hero = HeroView(); detail_layout.addWidget(self.hero)
        content = QFrame(); content.setObjectName("gameInfo"); content_layout = QHBoxLayout(content); content_layout.setContentsMargins(26,22,26,24); content_layout.setSpacing(24)
        self.cover = QLabel("COVER"); self.cover.setFixedSize(190,285); self.cover.setAlignment(Qt.AlignCenter); self.cover.setStyleSheet("background:#0b1118;border:1px solid #2e4258;color:#657789")
        content_layout.addWidget(self.cover)
        right = QVBoxLayout(); self.title = QLabel("Kütüphane yükleniyor…"); self.title.setObjectName("gameTitle")
        self.meta = QLabel(""); self.meta.setStyleSheet("color:#66c0f4;font-weight:700")
        self.description = QLabel("Raw GitHub kataloğundan oyunlar yükleniyor."); self.description.setWordWrap(True); self.description.setAlignment(Qt.AlignTop); self.description.setStyleSheet("color:#b8c2ca")
        buttons = QHBoxLayout(); self.install_button = QPushButton("YÜKLE"); self.install_button.setObjectName("install"); self.install_button.clicked.connect(self.install_current_game); self.install_button.setEnabled(False)
        self.verify_button = QPushButton("DOSYALARI DOĞRULA"); self.verify_button.setObjectName("secondary"); self.verify_button.setEnabled(False)
        buttons.addWidget(self.install_button); buttons.addWidget(self.verify_button); buttons.addStretch()
        right.addWidget(self.title); right.addWidget(self.meta); right.addSpacing(10); right.addWidget(self.description,1); right.addLayout(buttons); content_layout.addLayout(right,1); detail_layout.addWidget(content,1)
        splitter.addWidget(sidebar); splitter.addWidget(detail); splitter.setStretchFactor(0,0); splitter.setStretchFactor(1,1); splitter.setSizes([300,1180]); outer.addWidget(splitter,1)

        download = QFrame(); download.setObjectName("downloadBar"); dl = QVBoxLayout(download); dl.setContentsMargins(16,8,16,9)
        status_row = QHBoxLayout(); self.status = QLabel("Hazır"); self.status.setObjectName("muted"); self.progress_text = QLabel(""); self.progress_text.setStyleSheet("color:#66c0f4;font-weight:700")
        status_row.addWidget(self.status); status_row.addStretch(); status_row.addWidget(self.progress_text)
        self.progress = QProgressBar(); self.progress.setValue(0); self.logs = QPlainTextEdit(); self.logs.setReadOnly(True); self.logs.setFixedHeight(60); self.logs.hide()
        dl.addLayout(status_row); dl.addWidget(self.progress); dl.addWidget(self.logs); outer.addWidget(download)

    def open_settings(self):
        dialog = SettingsDialog(self, self.owner, self.repo, self.branch); dialog.saved.connect(self.apply_settings); dialog.exec()

    def apply_settings(self, owner: str, repo: str, branch: str):
        if not owner or not repo: return
        self.owner, self.repo, self.branch = owner, repo, branch
        self.settings.setValue("owner", owner); self.settings.setValue("repo", repo); self.settings.setValue("branch", branch); self.load_catalog()

    def load_catalog(self):
        if self.catalog_loading:
            self.status.setText("Katalog zaten yenileniyor…"); return
        self.catalog_loading = True; self.connection.setText("RAW • yükleniyor"); self.status.setText("Katalog yenileniyor…")
        task = CatalogTask(raw_repo_url(self.owner,self.repo,self.branch,"catalog.json"), self.catalog_cache_path)
        task.signals.done.connect(self.catalog_loaded); task.signals.error.connect(self.catalog_error); self.pool.start(task)

    def catalog_loaded(self, data: dict, source: str):
        self.catalog_loading = False; self.catalog = data
        platforms = sorted({str(g.get("platform","")).upper() for g in data.get("games",[]) if g.get("platform")})
        current = self.platform.currentText(); self.platform.blockSignals(True); self.platform.clear(); self.platform.addItem("Tümü"); self.platform.addItems(platforms)
        idx = self.platform.findText(current)
        if idx >= 0: self.platform.setCurrentIndex(idx)
        self.platform.blockSignals(False)
        if source == "raw": self.connection.setText("RAW • çevrimiçi"); self.status.setText(f"Katalog güncel • {len(data.get('games',[]))} oyun")
        else: self.connection.setText("CACHE • raw bekleniyor"); self.status.setText(f"Son kayıtlı katalog gösteriliyor • {len(data.get('games',[]))} oyun")
        self.render_library()

    def catalog_error(self, message: str):
        self.catalog_loading = False; self.connection.setText("RAW • bağlantı hatası"); self.status.setText("Katalog yüklenemedi")
        QMessageBox.warning(self,"Katalog henüz hazır değil",f"Raw katalog birkaç kez denendi fakat alınamadı.\n\n{message}\n\nYayın yeni yapıldıysa birkaç saniye sonra ↻ ile tekrar deneyebilirsin. Launcher artık bu durumda kapanmaz.")
        if not self.catalog.get("games"): self.show_empty_state("Katalog henüz alınamadı","Raw bağlantı hazır olduğunda ↻ ile tekrar dene.")

    def render_library(self):
        if not hasattr(self,"library"): return
        selected_key = None; current = self.library.currentItem()
        if current:
            payload = current.data(Qt.UserRole)
            if payload:
                game, old_channel = payload; selected_key = (game.get("id"),game.get("platform"),old_channel)
        query = self.search.text().strip().lower(); platform = self.platform.currentText(); channel = self.channel.currentText(); self.current_channel = channel
        items = []
        for game in self.catalog.get("games",[]):
            channels = game.get("channels") or {}
            if platform != "Tümü" and str(game.get("platform","")).upper() != platform: continue
            if channel not in channels: continue
            if query and query not in str(game.get("title","")).lower(): continue
            items.append(game)
        items.sort(key=lambda g: str(g.get("title","")).lower())
        self.library.blockSignals(True); self.library.clear(); selected_row = -1
        for row, game in enumerate(items):
            data = (game.get("channels") or {}).get(channel) or {}
            item = QListWidgetItem(f"{game.get('title','Untitled')}\n{str(game.get('platform','')).upper()}  •  v{data.get('version','?')}"); item.setData(Qt.UserRole,(game,channel)); self.library.addItem(item)
            if selected_key == (game.get("id"),game.get("platform"),channel): selected_row = row
        self.library.blockSignals(False); self.game_count.setText(f"{len(items)} oyun")
        if items: self.library.setCurrentRow(selected_row if selected_row >= 0 else 0)
        else: self.show_empty_state("Bu filtrede oyun yok","Platform, kanal veya arama filtresini değiştir.")

    def show_empty_state(self, title: str, description: str):
        self.current_game = None; self.art_token = ""; self.title.setText(title); self.meta.setText(""); self.description.setText(description)
        self.cover.clear(); self.cover.setText("COVER"); self.hero.set_art(None,None,"DROWNED"); self.install_button.setEnabled(False)

    def library_selection_changed(self, current, previous):
        if not current: return
        try:
            payload = current.data(Qt.UserRole)
            if not payload: return
            game, channel = payload; data = (game.get("channels") or {}).get(channel)
            if not isinstance(data,dict): return
            self.current_game = game; self.current_channel = channel; self.title.setText(str(game.get("title","Untitled")))
            size = int(data.get("size") or 0); self.meta.setText(f"{str(game.get('platform','')).upper()}  •  {channel.upper()}  •  v{data.get('version','?')}  •  {format_bytes(size)}")
            self.description.setText(str(game.get("description") or "Bu oyun için açıklama eklenmemiş.")); self.cover.clear(); self.cover.setText("COVER")
            self.hero.set_art(None,None,str(game.get("title","DROWNED"))); self.install_button.setEnabled(True); self.install_button.setText("YÜKLE"); self.load_artwork(game.get("artwork") or {})
        except Exception as exc: self.status.setText(f"Oyun bilgisi okunamadı: {exc}")

    def load_artwork(self, artwork: dict):
        self.art_token = uuid.uuid4().hex; token = self.art_token
        if not artwork: return
        task = ArtworkTask(token,artwork); task.signals.done.connect(self.artwork_loaded); self.pool.start(task)

    def artwork_loaded(self, token: str, raw: dict):
        if token != self.art_token or not self.current_game: return
        hero = None; logo = None
        if raw.get("hero"):
            p=QPixmap(); hero = p if p.loadFromData(raw["hero"]) else None
        if raw.get("logo"):
            p=QPixmap(); logo = p if p.loadFromData(raw["logo"]) else None
        if raw.get("cover"):
            cover=QPixmap()
            if cover.loadFromData(raw["cover"]): self.cover.setPixmap(cover.scaled(self.cover.size(),Qt.KeepAspectRatioByExpanding,Qt.SmoothTransformation))
        self.hero.set_art(hero,logo,str(self.current_game.get("title","DROWNED")))

    def install_current_game(self):
        if not self.current_game: return
        game=self.current_game; channel=self.current_channel; data=(game.get("channels") or {}).get(channel) or {}
        folder=QFileDialog.getExistingDirectory(self,f"{game.get('title','Oyun')} için kurulum klasörü")
        if not folder: return
        manifest_url=data.get("manifest_url","")
        if data.get("manifest_path"): manifest_url=raw_repo_url(self.owner,self.repo,self.branch,data["manifest_path"])
        if not manifest_url: QMessageBox.critical(self,"Manifest hatası","Bu yayın için manifest adresi bulunamadı."); return
        target=Path(folder)/str(game.get("title","Game")); self.progress.setValue(0); self.progress_text.setText("Hazırlanıyor"); self.status.setText(f"{game.get('title','Oyun')} indiriliyor")
        self.logs.clear(); self.logs.show(); self.install_button.setEnabled(False); self.install_button.setText("İNDİRİLİYOR…")
        task=InstallTask(manifest_url,target); task.signals.progress.connect(self.install_progress); task.signals.log.connect(self.logs.appendPlainText); task.signals.done.connect(self.install_done); task.signals.error.connect(self.install_error); self.pool.start(task)

    def install_progress(self, percent:int, text:str): self.progress.setValue(percent); self.progress_text.setText(f"%{percent}  •  {text}")
    def install_done(self):
        self.progress.setValue(100); self.progress_text.setText("%100 • doğrulandı"); self.status.setText("Kurulum tamamlandı"); self.install_button.setEnabled(True); self.install_button.setText("YENİDEN YÜKLE"); QMessageBox.information(self,"Tamamlandı","Kurulum ve SHA-256 doğrulaması tamamlandı.")
    def install_error(self,message:str):
        self.status.setText("İndirme hatası"); self.progress_text.setText("Hata"); self.install_button.setEnabled(True); self.install_button.setText("TEKRAR DENE"); QMessageBox.critical(self,"İndirme hatası",message)


def install_exception_hook():
    def hook(exc_type, exc_value, exc_tb):
        text="".join(traceback.format_exception(exc_type,exc_value,exc_tb))
        try: (app_data_dir()/"launcher-crash.log").write_text(text,encoding="utf-8")
        except Exception: pass
        try: QMessageBox.critical(None,"Drowned Launcher hatası",f"Beklenmeyen hata oluştu. Launcher kapanmadan hata kaydedildi.\n\n{exc_value}")
        except Exception: pass
        sys.__excepthook__(exc_type,exc_value,exc_tb)
    sys.excepthook=hook


def main():
    install_exception_hook(); app=QApplication(sys.argv); app.setApplicationName("Drowned Launcher"); app.setOrganizationName("Drowned"); app.setStyleSheet(STYLE)
    win=Launcher(); win.show(); sys.exit(app.exec())

if __name__ == "__main__": main()
