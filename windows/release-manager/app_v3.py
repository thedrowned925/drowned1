from __future__ import annotations

import sys
from pathlib import Path

import keyring
from PySide6.QtCore import QObject, QSettings, QThread, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QFormLayout, QFrame, QHBoxLayout,
    QInputDialog, QLabel, QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit,
    QProgressBar, QPushButton, QTabWidget, QTextEdit, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget
)

from drowned_shared.chunking import ChunkBuilder
from drowned_shared.constants import CHUNK_SIZE_MIB, MAX_DATA_ASSETS, MAX_RELEASE_DATA_BYTES
from drowned_shared.deletion import delete_channel, delete_game
from drowned_shared.github_client import GitHubClient
from drowned_shared.metadata import load_catalog
from drowned_shared.publish import publish_project
from drowned_shared.util import format_bytes

APP_VERSION = "0.3.0"
SERVICE = "DrownedReleaseManager"
ACCOUNT = "github_pat"

STYLE = """
QWidget { background:#0b1118; color:#d6d7d8; font-family:'Segoe UI'; font-size:14px; }
QMainWindow { background:#0b1118; }
QTabWidget::pane { border:0; }
QTabBar::tab { background:#17202a; color:#9da8b5; padding:12px 22px; margin-right:3px; }
QTabBar::tab:selected { background:#1b2838; color:#ffffff; }
QLineEdit, QComboBox, QTextEdit, QPlainTextEdit, QTreeWidget { background:#101923; border:1px solid #29394a; border-radius:7px; padding:9px; selection-background-color:#1a9fff; }
QLineEdit:focus, QComboBox:focus, QTextEdit:focus { border-color:#66c0f4; }
QPushButton { background:#1b2838; border:1px solid #30445a; border-radius:5px; padding:10px 15px; font-weight:600; }
QPushButton:hover { background:#253a4f; }
QPushButton#primary { background:#1a9fff; border-color:#2aaeff; color:white; }
QPushButton#primary:hover { background:#39adff; }
QPushButton#danger { background:#4b2024; border-color:#7d343c; color:#ffd9dc; }
QFrame#artCard, QFrame#infoCard { background:#101923; border:1px solid #223448; border-radius:10px; }
QProgressBar { background:#101923; border:1px solid #29394a; border-radius:6px; text-align:center; min-height:16px; }
QProgressBar::chunk { background:#66c0f4; border-radius:5px; }
QTreeWidget::item { padding:7px; }
QTreeWidget::item:selected { background:#1b3f5e; }
"""


def permission_message(exc: Exception) -> str:
    text = str(exc)
    if "403" in text or "Resource not accessible" in text:
        return (
            "GitHub bu token ile Release oluşturmaya izin vermedi.\n\n"
            "Fine-grained Personal Access Token ayarlarında şunları kontrol et:\n"
            "• Repository access: bu repository seçili olmalı\n"
            "• Contents: Read and write\n"
            "• Workflows: Read and write\n\n"
            "Bu repoda .github/workflows dosyaları bulunduğu/değiştiği için GitHub Release oluştururken Workflows yazma izni de isteyebilir.\n\n"
            "Token'ı güncelledikten sonra GitHub sekmesinde yeniden kaydet."
        )
    return text


class PublishWorker(QObject):
    log = Signal(str)
    progress = Signal(int)
    done = Signal(str)
    error = Signal(str)

    def __init__(self, params):
        super().__init__()
        self.params = params
        self.cancelled = False

    def run(self):
        try:
            p = self.params
            client = GitHubClient(p["token"], p["owner"], p["repo"], p["branch"])
            client.repo_info()
            manifest = publish_project(
                client, Path(p["source"]), p["title"], p["platform"], p["channel"], p["version"],
                p["description"], p["artwork"],
                progress=lambda sent, total: self.progress.emit(int(sent * 100 / max(total, 1))),
                log=self.log.emit, cancelled=lambda: self.cancelled,
            )
            self.done.emit(manifest["release"]["tag"])
        except Exception as exc:
            self.error.emit(permission_message(exc))


class DeleteWorker(QObject):
    log = Signal(str)
    done = Signal(str)
    error = Signal(str)

    def __init__(self, params, mode, record):
        super().__init__()
        self.params = params
        self.mode = mode
        self.record = record

    def run(self):
        try:
            p = self.params
            r = self.record
            client = GitHubClient(p["token"], p["owner"], p["repo"], p["branch"])
            client.repo_info()
            if self.mode == "channel":
                result = delete_channel(client, r["game_id"], r["platform"], r["channel"], log=self.log.emit)
            else:
                result = delete_game(client, r["game_id"], r["platform"], log=self.log.emit)
            self.done.emit(
                "Silme tamamlandı • "
                f"Release: {result['releases_deleted']} • Tag: {result.get('tags_deleted', 0)} • "
                f"Manifest: {result['manifests_deleted']} • Artwork: {len(result['artwork_deleted'])}"
            )
        except Exception as exc:
            self.error.emit(permission_message(exc))


class ArtworkPicker(QFrame):
    def __init__(self, title: str, hint: str, ratio: float | None):
        super().__init__()
        self.setObjectName("artCard")
        self.path = ""
        self.title = title
        self.ratio = ratio
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        title_label = QLabel(title)
        title_label.setStyleSheet("font-size:16px;font-weight:800;color:white")
        hint_label = QLabel(hint)
        hint_label.setWordWrap(True)
        hint_label.setStyleSheet("color:#8f9ba8;font-size:12px")
        self.preview = QLabel("Görsel seçilmedi")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumHeight(135)
        self.preview.setStyleSheet("background:#070c12;border:1px dashed #3a5168;border-radius:8px;color:#708090")
        button = QPushButton(f"{title} seç")
        button.clicked.connect(self.pick)
        layout.addWidget(title_label)
        layout.addWidget(hint_label)
        layout.addWidget(self.preview, 1)
        layout.addWidget(button)

    def pick(self):
        path, _ = QFileDialog.getOpenFileName(self, f"{self.title} seç", "", "Images (*.png *.jpg *.jpeg *.webp)")
        if not path:
            return
        pix = QPixmap(path)
        if pix.isNull():
            QMessageBox.warning(self, "Görsel okunamadı", "Seçilen dosya geçerli bir görsel değil.")
            return
        if self.ratio:
            actual = pix.width() / max(pix.height(), 1)
            if abs(actual - self.ratio) / self.ratio > 0.22:
                QMessageBox.information(self, "Görsel oranı farklı", f"{self.title} için önerilen oran yaklaşık {self.ratio:.2f}:1.\nSeçtiğin görsel {actual:.2f}:1. Kullanabilirsin ama arayüzde kırpılabilir.")
        self.path = path
        self.preview.setPixmap(pix.scaled(max(self.preview.width(), 300), self.preview.height(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation))


class Manager(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Drowned Release Manager {APP_VERSION}")
        self.resize(1240, 900)
        self.settings = QSettings("Drowned", "ReleaseManager")
        self.thread = None
        self.worker = None
        tabs = QTabWidget()
        tabs.addTab(self._publish_tab(), "Yeni Yayın")
        tabs.addTab(self._manage_tab(), "Yayınları Yönet")
        tabs.addTab(self._settings_tab(), "GitHub")
        self.setCentralWidget(tabs)

    def _params(self):
        return {"token": self.token.text().strip(), "owner": self.owner.text().strip(), "repo": self.repo.text().strip(), "branch": self.branch.text().strip() or "main"}

    def _settings_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)
        title = QLabel("GitHub bağlantısı")
        title.setStyleSheet("font-size:28px;font-weight:800;color:white")
        subtitle = QLabel("Yayınlama/silme işlemlerinde GitHub REST API; katalog, manifest ve artwork okumalarında raw.githubusercontent.com kullanılır.")
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color:#8f9ba8")
        v.addWidget(title)
        v.addWidget(subtitle)
        card = QFrame()
        card.setObjectName("infoCard")
        form = QFormLayout(card)
        self.owner = QLineEdit(self.settings.value("owner", "thedrowned925"))
        self.repo = QLineEdit(self.settings.value("repo", "drowned1"))
        self.branch = QLineEdit(self.settings.value("branch", "main"))
        self.token = QLineEdit(keyring.get_password(SERVICE, ACCOUNT) or "")
        self.token.setEchoMode(QLineEdit.Password)
        form.addRow("Owner", self.owner)
        form.addRow("Repository", self.repo)
        form.addRow("Branch", self.branch)
        form.addRow("Fine-grained PAT", self.token)
        v.addWidget(card)
        permission = QLabel(
            "<b>Gerekli token ayarları</b><br>Repository access → <b>Only select repositories</b> → dağıtım reposunu seç<br>"
            "Contents → <b>Read and write</b><br>Workflows → <b>Read and write</b> (bu repo workflow dosyaları içerdiği için önerilir)<br><br>"
            "Token repository içine veya düz metin ayar dosyasına kaydedilmez."
        )
        permission.setTextFormat(Qt.RichText)
        permission.setWordWrap(True)
        permission.setStyleSheet("background:#162432;border-left:4px solid #66c0f4;padding:14px;color:#c9d6e2")
        v.addWidget(permission)
        row = QHBoxLayout()
        save = QPushButton("Güvenli kaydet")
        save.setObjectName("primary")
        test = QPushButton("Bağlantıyı test et")
        save.clicked.connect(self.save_settings)
        test.clicked.connect(self.test_connection)
        row.addWidget(save)
        row.addWidget(test)
        row.addStretch()
        v.addLayout(row)
        v.addStretch()
        return w

    def _publish_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)
        title = QLabel("Yeni dağıtım")
        title.setStyleSheet("font-size:28px;font-weight:800;color:white")
        subtitle = QLabel(f"RAR/ZIP yok • {CHUNK_SIZE_MIB} MiB streaming chunk • yayın tamamlanana kadar Release draft kalır")
        subtitle.setStyleSheet("color:#8f9ba8")
        v.addWidget(title)
        v.addWidget(subtitle)
        form = QFormLayout()
        self.game_title = QLineEdit()
        self.platform = QComboBox()
        self.platform.addItems(["PC", "PS2", "PS3", "PS4", "PS5", "PSP", "PS Vita", "Xbox", "Xbox 360", "Xbox One", "Xbox Series", "Nintendo Switch", "Android", "Other"])
        self.channel = QComboBox()
        self.channel.addItems(["stable", "beta", "dev", "nightly", "archive"])
        self.version = QLineEdit("1.0.0")
        self.description = QTextEdit()
        self.description.setFixedHeight(75)
        self.source = QLineEdit()
        self.source.setReadOnly(True)
        choose = QPushButton("Klasör seç")
        choose.clicked.connect(self.pick_source)
        source_row = QHBoxLayout()
        source_row.setContentsMargins(0, 0, 0, 0)
        source_row.addWidget(self.source, 1)
        source_row.addWidget(choose)
        source_widget = QWidget()
        source_widget.setLayout(source_row)
        form.addRow("Proje / oyun", self.game_title)
        form.addRow("Platform", self.platform)
        form.addRow("Kanal", self.channel)
        form.addRow("Sürüm", self.version)
        form.addRow("Kaynak", source_widget)
        form.addRow("Açıklama", self.description)
        v.addLayout(form)
        explainer = QLabel("<b>Hero</b> = oyun sayfasının arkasındaki geniş yatay tanıtım görseli. <b>Cover</b> = Steam/PlayStation kutu kapağı gibi dikey oyun kapağı. <b>Logo</b> = oyunun yalnızca yazı/logosu; tercihen şeffaf PNG/WebP.")
        explainer.setTextFormat(Qt.RichText)
        explainer.setWordWrap(True)
        explainer.setStyleSheet("background:#142130;padding:11px;border-radius:7px;color:#b9c9d8")
        v.addWidget(explainer)
        arts = QHBoxLayout()
        self.hero = ArtworkPicker("Hero", "Geniş yatay arka plan. Önerilen: 1920×620. Launcher detay sayfasının üstünde kullanılır.", 1920 / 620)
        self.cover = ArtworkPicker("Cover", "Dikey kutu kapağı. Önerilen: 600×900. Kütüphanede ve detay sayfasında kullanılır.", 600 / 900)
        self.logo = ArtworkPicker("Logo", "Oyunun yazısı/logosu. Şeffaf PNG/WebP önerilir. Sabit oran zorunlu değil.", None)
        arts.addWidget(self.hero)
        arts.addWidget(self.cover)
        arts.addWidget(self.logo)
        v.addLayout(arts)
        self.plan = QLabel("Kaynak klasörü seçildiğinde plan hesaplanır.")
        self.plan.setWordWrap(True)
        self.plan.setStyleSheet("background:#101923;border:1px solid #223448;border-radius:8px;padding:13px")
        v.addWidget(self.plan)
        self.progress = QProgressBar()
        self.logs = QPlainTextEdit()
        self.logs.setReadOnly(True)
        self.logs.setFixedHeight(130)
        self.publish_button = QPushButton("GitHub'a taslak oluştur ve yayınla")
        self.publish_button.setObjectName("primary")
        self.publish_button.clicked.connect(self.publish)
        v.addWidget(self.progress)
        v.addWidget(self.logs)
        v.addWidget(self.publish_button)
        return w

    def _manage_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)
        title = QLabel("Yayınları yönet")
        title.setStyleSheet("font-size:28px;font-weight:800;color:white")
        v.addWidget(title)
        info = QLabel("Silme sırası: GitHub Release + chunk assetleri → Git tag → raw manifest → gerekiyorsa artwork → catalog.json. Katalog en son güncellenir.")
        info.setWordWrap(True)
        info.setStyleSheet("background:#101923;padding:12px;border-radius:7px;color:#9eacba")
        v.addWidget(info)
        refresh = QPushButton("Raw katalogdan yenile")
        refresh.clicked.connect(self.refresh_catalog)
        v.addWidget(refresh, 0, Qt.AlignLeft)
        self.manage_tree = QTreeWidget()
        self.manage_tree.setHeaderLabels(["Oyun", "Platform", "Kanal", "Sürüm", "Boyut / Tag"])
        v.addWidget(self.manage_tree, 1)
        actions = QHBoxLayout()
        self.delete_channel_button = QPushButton("Seçili sürümü / kanalı sil")
        self.delete_game_button = QPushButton("Oyunu tamamen sil")
        self.delete_channel_button.setObjectName("danger")
        self.delete_game_button.setObjectName("danger")
        self.delete_channel_button.clicked.connect(self.confirm_delete_channel)
        self.delete_game_button.clicked.connect(self.confirm_delete_game)
        actions.addWidget(self.delete_channel_button)
        actions.addWidget(self.delete_game_button)
        actions.addStretch()
        v.addLayout(actions)
        self.delete_logs = QPlainTextEdit()
        self.delete_logs.setReadOnly(True)
        self.delete_logs.setFixedHeight(130)
        v.addWidget(self.delete_logs)
        return w

    def pick_source(self):
        path = QFileDialog.getExistingDirectory(self, "Kaynak klasörü")
        if not path:
            return
        self.source.setText(path)
        builder = ChunkBuilder(Path(path))
        status = "✓ Tek Release'e sığıyor" if builder.chunk_count <= MAX_DATA_ASSETS else "⚠ Tek Release'e sığmıyor"
        self.plan.setText(f"<b>{status}</b><br>Kaynak: {format_bytes(builder.total_size)} • Chunk: {builder.chunk_count}/{MAX_DATA_ASSETS}<br>Tek Release veri tavanı: {format_bytes(MAX_RELEASE_DATA_BYTES)}")

    def save_settings(self):
        for key, widget in (("owner", self.owner), ("repo", self.repo), ("branch", self.branch)):
            self.settings.setValue(key, widget.text().strip())
        if self.token.text().strip():
            keyring.set_password(SERVICE, ACCOUNT, self.token.text().strip())
        QMessageBox.information(self, "Kaydedildi", "GitHub ayarları güvenli biçimde kaydedildi.")

    def test_connection(self):
        try:
            data = GitHubClient(self.token.text(), self.owner.text(), self.repo.text(), self.branch.text()).repo_info()
            permission = data.get("permissions") or {}
            suffix = "\nPush erişimi: " + ("var" if permission.get("push") else "GitHub doğrulamadı")
            QMessageBox.information(self, "Bağlantı başarılı", data["full_name"] + suffix)
        except Exception as exc:
            QMessageBox.critical(self, "GitHub hatası", permission_message(exc))

    def publish(self):
        if not self.source.text() or not self.game_title.text().strip():
            QMessageBox.warning(self, "Eksik", "Proje adı ve kaynak klasörü gerekli.")
            return
        if not self.token.text().strip():
            QMessageBox.warning(self, "Token gerekli", "GitHub sekmesinden fine-grained PAT girip güvenli olarak kaydet.")
            return
        params = {**self._params(), "source": self.source.text(), "title": self.game_title.text().strip(), "platform": self.platform.currentText(), "channel": self.channel.currentText(), "version": self.version.text().strip(), "description": self.description.toPlainText(), "artwork": {"hero": self.hero.path, "cover": self.cover.path, "logo": self.logo.path}}
        self.publish_button.setEnabled(False)
        self.logs.clear()
        self.thread = QThread()
        self.worker = PublishWorker(params)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.log.connect(self.logs.appendPlainText)
        self.worker.progress.connect(self.progress.setValue)
        self.worker.done.connect(self.on_done)
        self.worker.error.connect(self.on_error)
        self.worker.done.connect(self.thread.quit)
        self.worker.error.connect(self.thread.quit)
        self.thread.start()

    def refresh_catalog(self):
        try:
            catalog = load_catalog(GitHubClient(self.token.text(), self.owner.text(), self.repo.text(), self.branch.text()))
            self.manage_tree.clear()
            for game in sorted(catalog.get("games", []), key=lambda g: (g.get("platform", ""), g.get("title", "").lower())):
                channels = game.get("channels") or {}
                total = sum(int(c.get("size", 0)) for c in channels.values())
                parent = QTreeWidgetItem([game.get("title", "?"), game.get("platform", "").upper(), "Tümü", f"{len(channels)} yayın", format_bytes(total)])
                parent.setData(0, Qt.UserRole, {"kind": "game", "game_id": game.get("id"), "platform": game.get("platform"), "title": game.get("title")})
                self.manage_tree.addTopLevelItem(parent)
                for channel, data in sorted(channels.items()):
                    child = QTreeWidgetItem(["", game.get("platform", "").upper(), channel, data.get("version", "?"), f"{format_bytes(int(data.get('size', 0)))} • {data.get('tag', '')}"])
                    child.setData(0, Qt.UserRole, {"kind": "channel", "game_id": game.get("id"), "platform": game.get("platform"), "title": game.get("title"), "channel": channel, "version": data.get("version"), "tag": data.get("tag")})
                    parent.addChild(child)
                parent.setExpanded(True)
            self.delete_logs.appendPlainText(f"Raw katalog yenilendi: {len(catalog.get('games', []))} oyun")
        except Exception as exc:
            QMessageBox.critical(self, "Katalog hatası", permission_message(exc))

    def _selected_record(self):
        item = self.manage_tree.currentItem()
        return item.data(0, Qt.UserRole) if item else None

    def confirm_delete_channel(self):
        record = self._selected_record()
        if not record or record.get("kind") != "channel":
            QMessageBox.warning(self, "Seçim gerekli", "Silmek istediğin kanal/sürüm satırını seç.")
            return
        text, ok = QInputDialog.getText(self, "Sürümü kalıcı sil", f"{record['title']} • {record['platform'].upper()} • {record['channel']} • v{record.get('version')}\n\nRelease, chunk dosyaları, tag, raw manifest ve katalog kaydı silinecek.\n\nDevam etmek için SİL yaz:")
        if ok and text.strip().upper() == "SİL":
            self._start_delete("channel", record)

    def confirm_delete_game(self):
        record = self._selected_record()
        if not record:
            QMessageBox.warning(self, "Seçim gerekli", "Silmek istediğin oyunu seç.")
            return
        text, ok = QInputDialog.getText(self, "Oyunu tamamen sil", f"{record['title']} ({record['platform'].upper()}) tamamen silinecek.\n\nTüm kanallar, Release/chunk dosyaları, tag'ler, manifestler, kullanılmayan artwork ve katalog kaydı kaldırılacak.\n\nOnaylamak için oyun adını aynen yaz:\n{record['title']}")
        if not ok:
            return
        if text.strip() != record["title"]:
            QMessageBox.warning(self, "İptal", "Oyun adı eşleşmedi; hiçbir şey silinmedi.")
            return
        self._start_delete("game", record)

    def _start_delete(self, mode, record):
        self.delete_channel_button.setEnabled(False)
        self.delete_game_button.setEnabled(False)
        self.delete_logs.clear()
        self.thread = QThread()
        self.worker = DeleteWorker(self._params(), mode, record)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.log.connect(self.delete_logs.appendPlainText)
        self.worker.done.connect(self.on_delete_done)
        self.worker.error.connect(self.on_delete_error)
        self.worker.done.connect(self.thread.quit)
        self.worker.error.connect(self.thread.quit)
        self.thread.start()

    def on_done(self, tag):
        self.publish_button.setEnabled(True)
        self.progress.setValue(100)
        QMessageBox.information(self, "Yayınlandı", f"Release yayınlandı:\n{tag}")

    def on_error(self, message):
        self.publish_button.setEnabled(True)
        QMessageBox.critical(self, "Yayınlama hatası", message)

    def on_delete_done(self, message):
        self.delete_channel_button.setEnabled(True)
        self.delete_game_button.setEnabled(True)
        self.delete_logs.appendPlainText(message)
        self.refresh_catalog()
        QMessageBox.information(self, "Silme tamamlandı", message)

    def on_delete_error(self, message):
        self.delete_channel_button.setEnabled(True)
        self.delete_game_button.setEnabled(True)
        QMessageBox.critical(self, "Silme hatası", message)


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLE)
    win = Manager()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
