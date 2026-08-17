from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QThread, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

import app_v3 as legacy
import app_v4 as previous
from drowned_shared.publish import publish_project
from drowned_shared.github_client import GitHubClient

APP_VERSION = "0.5.0"

# Steam client palette, shared with the Launcher so the two apps read as one
# suite: #171a21 chrome, #1b2838 page, #16202d panel, #2a475e selection,
# #66c0f4 accent, green publish button, ~2px corners throughout.
MODERN_STYLE = r"""
* {
    font-family: "Arial", "Segoe UI", sans-serif;
    outline: 0;
}
QWidget { background: #1b2838; color: #c7d5e0; font-size: 13px; }
QMainWindow { background: #1b2838; }
QToolTip {
    background: #16202d;
    color: #c7d5e0;
    border: 1px solid #000000;
    padding: 5px 7px;
}
QTabWidget::pane { border: 0; top: -1px; }
QTabBar::tab {
    background: #171a21;
    color: #8f98a0;
    font-weight: 700;
    padding: 11px 22px;
    margin-right: 2px;
}
QTabBar::tab:hover { color: #dce7f3; }
QTabBar::tab:selected { background: #1b2838; color: #ffffff; border-bottom: 2px solid #66c0f4; }
QLineEdit, QComboBox, QTextEdit, QPlainTextEdit, QTreeWidget {
    background: #0e141b;
    border: 1px solid #000000;
    border-radius: 2px;
    padding: 8px 10px;
    color: #c7d5e0;
    selection-background-color: #2a6a9c;
}
QLineEdit:hover, QComboBox:hover, QTextEdit:hover { border-color: #4c6b8a; }
QLineEdit:focus, QComboBox:focus, QTextEdit:focus { border-color: #66c0f4; background: #0b1017; }
QComboBox::drop-down { border: 0; width: 22px; }
QComboBox QAbstractItemView {
    background: #16202d;
    color: #c7d5e0;
    border: 1px solid #000000;
    selection-background-color: #2a475e;
    padding: 3px;
}
QPushButton {
    min-height: 18px;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #3d5875, stop:1 #2a3f57);
    color: #c7d5e0;
    border: 1px solid #000000;
    border-radius: 2px;
    padding: 8px 15px;
    font-weight: 700;
}
QPushButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #4b7ba8, stop:1 #35648b);
    color: #ffffff;
}
QPushButton:pressed { background: #22384c; }
QPushButton:disabled { background: #1b2733; color: #4c5866; border-color: #000000; }
QPushButton#primary {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #7cb61e, stop:1 #4f8412);
    color: #ffffff;
    border: 1px solid #3d6a0d;
    min-height: 22px;
    padding: 9px 24px;
    font-size: 14px;
    font-weight: 700;
}
QPushButton#primary:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #8ed025, stop:1 #5d9c15);
}
QPushButton#primary:disabled { background: #35502a; color: #93ab84; border-color: #2c4022; }
QPushButton#danger {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #55272f, stop:1 #3c1f24);
    color: #e5a9b0;
    border: 1px solid #000000;
}
QPushButton#danger:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #6d323c, stop:1 #4e262d);
    color: #ffd0d6;
}
QPushButton#tiny {
    padding: 3px 7px;
    font-size: 10px;
    font-weight: 600;
    min-height: 0;
}
QFrame#artCard, QFrame#infoCard {
    background: #16202d;
    border: 1px solid #22303f;
    border-radius: 2px;
}
QLabel#cardTitle { color: #ffffff; font-size: 15px; font-weight: 700; }
QLabel#cardHint { color: #8f9ba8; font-size: 12px; }
QLabel#muted { color: #67707b; font-size: 12px; }
QProgressBar {
    min-height: 6px; max-height: 6px;
    background: #0b1017;
    border: 0; border-radius: 0;
    text-align: center; color: transparent;
}
QProgressBar::chunk { background: #66c0f4; border-radius: 0; }
QTreeWidget { padding: 2px; }
QTreeWidget::item { padding: 8px; }
QTreeWidget::item:hover { background: #2a3f57; }
QTreeWidget::item:selected { background: #2a475e; color: #ffffff; }
QScrollBar:vertical { background: #16202d; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: #2a3f57; min-height: 24px; }
QScrollBar::handle:vertical:hover { background: #3d6c93; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
"""

IMAGE_FILTER = "Images (*.png *.jpg *.jpeg *.webp)"
ICON_FILTER = "Icons (*.ico *.png)"


class MediaPublishWorker(legacy.PublishWorker):
    """The inherited worker forwards a fixed argument list to publish_project
    and has no seam for the new `media` argument, so this subclass repeats
    the call with trailers attached. publish_project itself is unchanged."""

    def run(self):
        try:
            p = self.params
            client = GitHubClient(p["token"], p["owner"], p["repo"], p["branch"])
            client.repo_info()
            manifest = publish_project(
                client,
                Path(p["source"]),
                p["title"],
                p["platform"],
                p["channel"],
                p["version"],
                p["description"],
                p["artwork"],
                progress=lambda sent, total: self.progress.emit(int(sent * 100 / max(total, 1))),
                log=self.log.emit,
                cancelled=lambda: self.cancelled,
                media=p.get("media") or None,
            )
            self.done.emit(manifest["release"]["tag"])
        except Exception as exc:
            self.error.emit(legacy.permission_message(exc))


class IconPicker(QFrame):
    """Single-slot picker that also accepts a real `.ico`, for the icon shown
    beside a game in the Launcher list and download rows."""

    def __init__(self, title: str, hint: str):
        super().__init__()
        self.setObjectName("artCard")
        self.title = title
        self.path = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(7)

        title_label = QLabel(title)
        title_label.setObjectName("cardTitle")
        hint_label = QLabel(hint)
        hint_label.setObjectName("cardHint")
        hint_label.setWordWrap(True)

        self.preview = QLabel("Simge seçilmedi")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumHeight(96)
        self.preview.setStyleSheet(
            "background:#0b1017;border:1px dashed #2a3f57;border-radius:2px;color:#67707b"
        )

        button = QPushButton(f"{title} seç")
        button.clicked.connect(self.pick)

        layout.addWidget(title_label)
        layout.addWidget(hint_label)
        layout.addWidget(self.preview, 1)
        layout.addWidget(button)

    def pick(self):
        path, _ = QFileDialog.getOpenFileName(self, f"{self.title} seç", "", ICON_FILTER)
        if not path:
            return
        pixmap = QPixmap(path)
        if pixmap.isNull():
            QMessageBox.warning(
                self,
                "Simge okunamadı",
                "Seçilen dosya geçerli bir .ico veya .png değil.",
            )
            return
        self.apply_path(path, pixmap)

    def apply_path(self, path: str, pixmap: QPixmap | None = None) -> bool:
        pixmap = pixmap if pixmap is not None else QPixmap(path)
        if pixmap.isNull():
            return False
        self.path = path
        self.preview.clear()
        self.preview.setPixmap(pixmap.scaled(88, 88, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        return True

    def reset(self, message: str = "Simge seçilmedi"):
        self.path = ""
        self.preview.clear()
        self.preview.setText(message)


class MultiImagePicker(QFrame):
    """Optional multi-screenshot picker, alongside the single-slot
    hero/cover/logo/icon pickers. No aspect ratio is enforced because
    screenshots vary far more in shape than the fixed artwork slots."""

    def __init__(self, title: str, hint: str, max_images: int = 8):
        super().__init__()
        self.setObjectName("artCard")
        self.title = title
        self.max_images = max_images
        self.paths: list[str] = []
        self._holders: dict[str, QFrame] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(7)

        header = QHBoxLayout()
        title_label = QLabel(title)
        title_label.setObjectName("cardTitle")
        self.count_label = QLabel("0 / %d" % max_images)
        self.count_label.setObjectName("muted")
        header.addWidget(title_label)
        header.addStretch()
        header.addWidget(self.count_label)

        hint_label = QLabel(hint)
        hint_label.setObjectName("cardHint")
        hint_label.setWordWrap(True)

        self._strip = QHBoxLayout()
        self._strip.setSpacing(8)
        strip_widget = QWidget()
        strip_widget.setLayout(self._strip)
        self._empty_label = QLabel("Henüz görsel seçilmedi")
        self._empty_label.setObjectName("muted")
        self._strip.addWidget(self._empty_label)
        self._strip.addStretch(1)

        buttons = QHBoxLayout()
        buttons.setSpacing(6)
        add_button = QPushButton("Görsel ekle")
        add_button.clicked.connect(self.pick)
        clear_button = QPushButton("Tümünü temizle")
        clear_button.clicked.connect(self.clear)
        buttons.addWidget(add_button)
        buttons.addWidget(clear_button)
        buttons.addStretch()

        layout.addLayout(header)
        layout.addWidget(hint_label)
        layout.addWidget(strip_widget)
        layout.addLayout(buttons)

    def pick(self):
        if len(self.paths) >= self.max_images:
            QMessageBox.information(self, "Sınır", f"En fazla {self.max_images} görsel eklenebilir.")
            return
        paths, _ = QFileDialog.getOpenFileNames(self, f"{self.title} seç", "", IMAGE_FILTER)
        self.add_paths(paths)

    def add_paths(self, paths) -> int:
        added = 0
        for path in paths or []:
            if len(self.paths) >= self.max_images:
                break
            if path in self.paths:
                continue
            pixmap = QPixmap(path)
            if pixmap.isNull():
                continue
            self._add_thumb(path, pixmap)
            added += 1
        return added

    def _add_thumb(self, path: str, pixmap: QPixmap):
        self._empty_label.hide()
        self.paths.append(path)

        holder = QFrame()
        holder_layout = QVBoxLayout(holder)
        holder_layout.setContentsMargins(0, 0, 0, 0)
        holder_layout.setSpacing(3)
        thumb = QLabel()
        thumb.setFixedSize(96, 54)
        thumb.setPixmap(pixmap.scaled(96, 54, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation))
        remove = QPushButton("Kaldır")
        remove.setObjectName("tiny")
        remove.clicked.connect(lambda: self._remove(path))
        holder_layout.addWidget(thumb)
        holder_layout.addWidget(remove)

        self._holders[path] = holder
        self._strip.insertWidget(max(self._strip.count() - 1, 0), holder)
        self._sync_count()

    def _remove(self, path: str):
        if path in self.paths:
            self.paths.remove(path)
        holder = self._holders.pop(path, None)
        if holder is not None:
            self._strip.removeWidget(holder)
            holder.setParent(None)
            holder.deleteLater()
        if not self.paths:
            self._empty_label.show()
        self._sync_count()

    def clear(self):
        for path in list(self.paths):
            self._remove(path)

    def _sync_count(self):
        self.count_label.setText(f"{len(self.paths)} / {self.max_images}")


class TrailerPanel(QFrame):
    """Read-only view of the trailer links pulled from Steam. Trailer files
    are never downloaded: Steam already serves them, so the catalog stores
    links and the Launcher can open them."""

    def __init__(self):
        super().__init__()
        self.setObjectName("artCard")
        self.trailers: list[dict] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(7)

        header = QHBoxLayout()
        title = QLabel("Fragmanlar")
        title.setObjectName("cardTitle")
        self.count_label = QLabel("0 video")
        self.count_label.setObjectName("muted")
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.count_label)

        hint = QLabel(
            "Steam'den link olarak alınır, dosya indirilmez. Katalogda "
            "`media.trailers` altında saklanır."
        )
        hint.setObjectName("cardHint")
        hint.setWordWrap(True)

        self.view = QPlainTextEdit()
        self.view.setReadOnly(True)
        self.view.setFixedHeight(84)
        self.view.setPlaceholderText("SteamDB'den içerik çekilince fragman linkleri burada listelenir.")

        clear_button = QPushButton("Fragmanları temizle")
        clear_button.clicked.connect(self.clear)
        row = QHBoxLayout()
        row.addWidget(clear_button)
        row.addStretch()

        layout.addLayout(header)
        layout.addWidget(hint)
        layout.addWidget(self.view)
        layout.addLayout(row)

    def set_trailers(self, trailers: list[dict]):
        self.trailers = list(trailers or [])
        if not self.trailers:
            self.view.clear()
            self.count_label.setText("0 video")
            return
        lines = []
        for trailer in self.trailers:
            link = trailer.get("mp4") or trailer.get("webm") or ""
            lines.append(f"{trailer.get('name') or 'Fragman'}  —  {link}")
        self.view.setPlainText("\n".join(lines))
        self.count_label.setText(f"{len(self.trailers)} video")

    def clear(self):
        self.set_trailers([])


class Manager(previous.Manager):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Drowned Release Manager {APP_VERSION}")
        self._steam_app_id = None

    # -- publish tab ------------------------------------------------------

    def _publish_tab(self):
        widget = super()._publish_tab()
        root = widget.layout()

        extras = QWidget()
        extras_layout = QHBoxLayout(extras)
        extras_layout.setContentsMargins(0, 0, 0, 0)
        extras_layout.setSpacing(12)

        self.icon = IconPicker(
            "Simge",
            "Launcher listesinde ve indirme satırlarında görünür. .ico veya kare .png.",
        )
        self.trailer_panel = TrailerPanel()
        extras_layout.addWidget(self.icon, 1)
        extras_layout.addWidget(self.trailer_panel, 2)

        self.screenshots = MultiImagePicker(
            "Ekran Görüntüleri",
            "İsteğe bağlı, en fazla 8 görsel. SteamDB'den çekilince otomatik doldurulur.",
            max_images=8,
        )

        insert_at = self._index_of(root, self.plan)
        root.insertWidget(insert_at, extras)
        root.insertWidget(insert_at + 1, self.screenshots)
        return widget

    @staticmethod
    def _index_of(layout, widget) -> int:
        """Locate an inherited widget by identity rather than a magic index,
        so a future reordering upstream cannot silently misplace the new
        panels."""
        for i in range(layout.count()):
            item = layout.itemAt(i)
            if item is not None and item.widget() is widget:
                return i
        return layout.count()

    # -- Steam import -----------------------------------------------------

    def _cleanup_steam_temp(self, reset_previews: bool = False):
        old_paths = set(self._steam_paths)
        super()._cleanup_steam_temp(reset_previews=reset_previews)

        icon = getattr(self, "icon", None)
        if icon is not None and icon.path in old_paths:
            if reset_previews:
                icon.reset("Steam simgesi GitHub'a aktarıldı")
            else:
                icon.reset()

        shots = getattr(self, "screenshots", None)
        if shots is not None:
            for path in list(shots.paths):
                if path in old_paths:
                    shots._remove(path)

    def _steam_artwork_done(self, result: dict):
        super()._steam_artwork_done(result)

        applied = []
        icon_path = str((result.get("paths") or {}).get("icon") or "")
        if icon_path and self.icon.apply_path(icon_path):
            self._steam_paths.add(icon_path)
            applied.append("Simge")

        shot_paths = list(result.get("screenshots") or [])
        if shot_paths:
            self.screenshots.clear()
            added = self.screenshots.add_paths(shot_paths)
            if added:
                self._steam_paths.update(shot_paths[:added])
                applied.append(f"{added} ekran görüntüsü")

        trailers = list(result.get("trailers") or [])
        self.trailer_panel.set_trailers(trailers)
        if trailers:
            applied.append(f"{len(trailers)} fragman linki")

        self._steam_app_id = result.get("app_id")

        if applied:
            self.steam_status.setText(
                self.steam_status.text() + "  •  Ek içerik: " + ", ".join(applied) + "."
            )

    # -- publishing --------------------------------------------------------

    def publish(self):
        if not self.source.text() or not self.game_title.text().strip():
            QMessageBox.warning(self, "Eksik", "Proje adı ve kaynak klasörü gerekli.")
            return
        if not self.token.text().strip():
            QMessageBox.warning(self, "Token gerekli", "GitHub sekmesinden fine-grained PAT girip güvenli olarak kaydet.")
            return

        media = {}
        if self.trailer_panel.trailers:
            media["trailers"] = list(self.trailer_panel.trailers)
        if self._steam_app_id:
            media["steam_app_id"] = int(self._steam_app_id)

        params = {
            **self._params(),
            "source": self.source.text(),
            "title": self.game_title.text().strip(),
            "platform": self.platform.currentText(),
            "channel": self.channel.currentText(),
            "version": self.version.text().strip(),
            "description": self.description.toPlainText(),
            "artwork": {
                "hero": self.hero.path,
                "cover": self.cover.path,
                "logo": self.logo.path,
                "icon": self.icon.path,
                "screenshots": list(self.screenshots.paths),
            },
            "media": media,
        }
        self.publish_button.setEnabled(False)
        self.logs.clear()
        self.thread = QThread()
        self.worker = MediaPublishWorker(params)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.log.connect(self.logs.appendPlainText)
        self.worker.progress.connect(self.progress.setValue)
        self.worker.done.connect(self.on_done)
        self.worker.error.connect(self.on_error)
        self.worker.done.connect(self.thread.quit)
        self.worker.error.connect(self.thread.quit)
        self.thread.start()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Drowned Release Manager")
    app.setOrganizationName("Drowned")
    app.setStyle("Fusion")
    app.setStyleSheet(MODERN_STYLE)
    win = Manager()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
