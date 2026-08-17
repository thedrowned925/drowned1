from __future__ import annotations

import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from PySide6.QtCore import (
    QDateTime,
    QEasingCurve,
    QEvent,
    QObject,
    QPropertyAnimation,
    QRect,
    QRunnable,
    Qt,
    QTimer,
    QUrl,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QDesktopServices,
    QKeyEvent,
    QKeySequence,
    QLinearGradient,
    QPainter,
    QPixmap,
    QShortcut,
)
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSplashScreen,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

import app_v4 as base
import app_v6 as registry_base
import app_v9 as previous
from library_grid import GameGridView, GameListView, ScreenshotGallery

try:
    from xinput import GamepadPoller
except Exception:  # pragma: no cover - xinput is Windows-only
    GamepadPoller = None

APP_VERSION = "0.10.0"

# ---------------------------------------------------------------------------
# Steam's own palette, sampled from the client rather than invented:
#   #171a21  window chrome / menu bar / status bar
#   #1b2838  page background
#   #16202d  panel background
#   #2a475e  selected row
#   #3d6c93  hover / active row
#   #66c0f4  link + accent blue
#   #5b9c1f  PLAY button green
# Corner radius stays at 2px throughout, because the real client is
# essentially square-cornered.
# ---------------------------------------------------------------------------
STEAM_STYLE = r"""
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

/* ---- window chrome ---- */
QFrame#menubar { background: #171a21; border: 0; }
QLabel#menuItem { color: #b8b6b4; font-size: 12px; padding: 4px 9px; }
QLabel#menuItem:hover { color: #ffffff; }

QFrame#navbar { background: #171a21; border-bottom: 1px solid #000000; }
QLabel#navActive {
    color: #ffffff;
    font-size: 14px;
    font-weight: 700;
    padding: 12px 14px 10px 14px;
    border-bottom: 2px solid #66c0f4;
}
QLabel#nav {
    color: #8f98a0;
    font-size: 14px;
    font-weight: 700;
    padding: 12px 14px;
}
QLabel#nav:hover { color: #ffffff; }
QLabel#navUser { color: #b8b6b4; font-size: 12px; font-weight: 700; padding: 0 8px; }

QFrame#sidebar { background: #16202d; border-right: 1px solid #000000; }
QFrame#detail { background: #1b2838; }
QFrame#infoCard { background: transparent; border: 0; }
QFrame#actionBar { background: #16202d; border-bottom: 1px solid #0d1319; }
QFrame#panel { background: #16202d; border: 1px solid #22303f; border-radius: 2px; }
QFrame#hairline { background: #2a3f57; }
QFrame#statusbar { background: #171a21; border-top: 1px solid #000000; }
QFrame#downloadBar { background: #171a21; border-top: 1px solid #000000; }
QFrame#downloadCard { background: transparent; border: 0; }

/* ---- typography ---- */
QLabel#brandMark {
    background: #66c0f4;
    color: #0e141b;
    border-radius: 2px;
    font-size: 14px;
    font-weight: 900;
}
QLabel#sectionLabel {
    color: #6b7883;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1px;
}
QLabel#panelTitle {
    color: #8f98a0;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1px;
}
QLabel#gameTitle { color: #ffffff; font-size: 28px; font-weight: 700; }
QLabel#metaLine { color: #67c1f5; font-size: 12px; font-weight: 600; }
QLabel#description { color: #acb2b8; font-size: 13px; }
QLabel#statName { color: #67707b; font-size: 10px; font-weight: 700; letter-spacing: 1px; }
QLabel#statValue { color: #d1d9e0; font-size: 13px; font-weight: 700; }
QLabel#rowKey { color: #67707b; font-size: 12px; }
QLabel#rowValue { color: #c7d5e0; font-size: 12px; font-weight: 600; }
QLabel#connectionOnline { color: #90c33b; font-size: 11px; font-weight: 700; }
QLabel#muted { color: #67707b; font-size: 12px; }
QLabel#downloadDot { color: #66c0f4; font-size: 13px; }
QLabel#downloadTitle { color: #c7d5e0; font-size: 12px; font-weight: 700; }
QLabel#progressText { color: #67c1f5; font-size: 11px; font-weight: 600; }
QLabel#bigMetric { color: #ffffff; font-size: 17px; font-weight: 700; }

/* ---- detail page tabs ---- */
QLabel#tabActive {
    color: #ffffff;
    font-size: 12px;
    font-weight: 700;
    padding: 10px 16px;
    border-bottom: 2px solid #66c0f4;
}
QLabel#tab {
    color: #8f98a0;
    font-size: 12px;
    font-weight: 700;
    padding: 10px 16px;
    border-bottom: 2px solid transparent;
}
QLabel#tab:hover { color: #ffffff; }

/* ---- inputs ---- */
QLineEdit, QComboBox {
    min-height: 18px;
    background: #0e141b;
    border: 1px solid #000000;
    border-radius: 2px;
    padding: 6px 9px;
    color: #c7d5e0;
    selection-background-color: #2a6a9c;
}
QLineEdit:hover, QComboBox:hover { border-color: #4c6b8a; }
QLineEdit:focus, QComboBox:focus { border-color: #66c0f4; background: #0b1017; }
QComboBox::drop-down { border: 0; width: 20px; }
QComboBox QAbstractItemView {
    background: #16202d;
    color: #c7d5e0;
    border: 1px solid #000000;
    selection-background-color: #2a475e;
    padding: 2px;
}
QListWidget { background: transparent; border: 0; outline: 0; }

/* ---- buttons ---- */
QPushButton {
    min-height: 18px;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #3d5875, stop:1 #2a3f57);
    color: #c7d5e0;
    border: 1px solid #000000;
    border-radius: 2px;
    padding: 7px 14px;
    font-weight: 700;
}
QPushButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #4b7ba8, stop:1 #35648b);
    color: #ffffff;
}
QPushButton:pressed { background: #22384c; }
QPushButton:disabled { background: #1b2733; color: #4c5866; border-color: #000000; }
QPushButton#iconButton {
    min-width: 30px; max-width: 30px; min-height: 30px; max-height: 30px;
    padding: 0; font-size: 14px;
}
QPushButton#install {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #7cb61e, stop:1 #4f8412);
    color: #ffffff;
    border: 1px solid #3d6a0d;
    min-height: 24px;
    padding: 9px 30px;
    font-size: 15px;
    font-weight: 700;
}
QPushButton#install:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #8ed025, stop:1 #5d9c15);
}
QPushButton#install:disabled {
    background: #35502a; color: #93ab84; border-color: #2c4022;
}
QPushButton#secondary {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #3d5875, stop:1 #2a3f57);
    color: #c7d5e0;
}
QPushButton#danger {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #55272f, stop:1 #3c1f24);
    color: #e5a9b0;
}
QPushButton#danger:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #6d323c, stop:1 #4e262d);
    color: #ffd0d6;
}
QPushButton#linkButton {
    background: transparent; border: 0; color: #67c1f5;
    font-weight: 600; padding: 4px 6px;
}
QPushButton#linkButton:hover { color: #ffffff; background: transparent; }
QPushButton#pauseButton {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #3a9adf, stop:1 #2a76a7);
    color: #ffffff;
    border: 1px solid #21587e;
    min-height: 22px;
    padding: 8px 20px;
    font-weight: 700;
}
QPushButton#pauseButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #4cabef, stop:1 #3387bb);
}

/* ---- progress ---- */
QProgressBar {
    min-height: 5px; max-height: 5px;
    background: #0b1017;
    border: 0; border-radius: 0;
    text-align: center; color: transparent;
}
QProgressBar::chunk { background: #66c0f4; border-radius: 0; }
QProgressBar#fatBar { min-height: 10px; max-height: 10px; background: #0b1017; }
QProgressBar#fatBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #3a8fc4, stop:1 #66c0f4);
}

QPlainTextEdit {
    background: #0b1017;
    border: 1px solid #000000;
    border-radius: 2px;
    color: #8f98a0;
    padding: 6px 8px;
    selection-background-color: #2a6a9c;
}

/* ---- scrollbars ---- */
QScrollBar:vertical { background: #16202d; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: #2a3f57; min-height: 24px; }
QScrollBar::handle:vertical:hover { background: #3d6c93; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QScrollBar:horizontal { background: #16202d; height: 10px; margin: 0; }
QScrollBar::handle:horizontal { background: #2a3f57; min-width: 24px; }
QScrollBar::handle:horizontal:hover { background: #3d6c93; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }

QSplitter::handle { background: #000000; width: 1px; }

/* ================= BIG PICTURE ================= */
QWidget#bigPictureRoot { background: #10161d; }
QFrame#bpHeader { background: transparent; }
QLineEdit#bpSearch {
    background: #39424e;
    border: 1px solid #4a5563;
    border-radius: 16px;
    padding: 9px 16px;
    color: #ffffff;
    font-size: 15px;
    min-height: 22px;
}
QLineEdit#bpSearch:focus { border-color: #66c0f4; background: #414c59; }
QLabel#bpClock { color: #ffffff; font-size: 17px; font-weight: 600; }
QLabel#bpShoulder {
    color: #ffffff;
    background: #39424e;
    border: 1px solid #58616e;
    border-radius: 4px;
    font-size: 12px;
    font-weight: 700;
    padding: 5px 9px;
}
QLabel#bpTabActive {
    color: #ffffff;
    background: #39424e;
    border-radius: 17px;
    font-size: 14px;
    font-weight: 700;
    padding: 9px 20px;
}
QLabel#bpTab {
    color: #b0b8c1;
    background: transparent;
    border-radius: 17px;
    font-size: 14px;
    font-weight: 700;
    padding: 9px 20px;
}
QLabel#bpTab:hover { color: #ffffff; }
QFrame#bpFooter { background: #0b1014; border-top: 1px solid #000000; }
QLabel#bpSteamPill {
    color: #10161d;
    background: #ffffff;
    border-radius: 11px;
    font-size: 12px;
    font-weight: 800;
    padding: 4px 14px;
}
QLabel#bpFooterText { color: #ffffff; font-size: 12px; font-weight: 700; }
QLabel#bpGlyph {
    color: #10161d;
    background: #ffffff;
    border-radius: 10px;
    font-size: 12px;
    font-weight: 800;
    min-width: 20px;
    max-width: 20px;
    min-height: 20px;
    max-height: 20px;
}
QLabel#bpHint { color: #c8cfd6; font-size: 12px; font-weight: 700; }
QLabel#bpBigTitle { color: #ffffff; font-size: 30px; font-weight: 700; }
QLabel#bpMeta { color: #9aa4ae; font-size: 14px; }
QLabel#bpSectionTitle { color: #ffffff; font-size: 20px; font-weight: 700; }
QScrollArea#bpGrid { background: transparent; }
QWidget#gameGridContent { background: transparent; }
"""

_GAMEPAD_DIRECTION_KEYS = {
    "up": Qt.Key_Up,
    "down": Qt.Key_Down,
    "left": Qt.Key_Left,
    "right": Qt.Key_Right,
}


def _fetch_image_bytes(url: str) -> bytes | None:
    for delay in (0.0, 0.5, 1.2):
        if delay:
            time.sleep(delay)
        try:
            response = requests.get(
                base.cache_bust(url),
                timeout=(6, 15),
                headers={"User-Agent": f"Drowned-Launcher/{APP_VERSION}", "Cache-Control": "no-cache"},
            )
            response.raise_for_status()
            if response.content:
                return response.content
        except Exception:
            continue
    return None


class TileCoverSignals(QObject):
    done = Signal(str, str, object)  # key, url, bytes|None


class TileCoverTask(QRunnable):
    def __init__(self, key: str, url: str):
        super().__init__()
        self.key = key
        self.url = url
        self.signals = TileCoverSignals()

    def run(self):
        self.signals.done.emit(self.key, self.url, _fetch_image_bytes(self.url))


class ScreenshotSignals(QObject):
    done = Signal(str, int, str, object)  # token, index, url, bytes|None


class ScreenshotTask(QRunnable):
    def __init__(self, token: str, index: int, url: str):
        super().__init__()
        self.token = token
        self.index = index
        self.url = url
        self.signals = ScreenshotSignals()

    def run(self):
        self.signals.done.emit(self.token, self.index, self.url, _fetch_image_bytes(self.url))


class ClickableLabel(QLabel):
    clicked = Signal()

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class SteamHeroView(previous.ModernHeroView):
    """The game page banner: hero art bleeding into the page background with
    the logo sitting bottom-left, plus a very slow ambient zoom so a static
    library page still feels alive."""

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(300)
        self._zoom = 0.0
        self._zoom_anim = QVariantAnimation(self)
        self._zoom_anim.setStartValue(0.0)
        self._zoom_anim.setKeyValueAt(0.5, 1.0)
        self._zoom_anim.setEndValue(0.0)
        self._zoom_anim.setDuration(28000)
        self._zoom_anim.setEasingCurve(QEasingCurve.InOutSine)
        self._zoom_anim.setLoopCount(-1)
        self._zoom_anim.valueChanged.connect(self._on_zoom)

    def _on_zoom(self, value):
        self._zoom = float(value)
        self.update()

    def set_art(self, hero: QPixmap | None, logo: QPixmap | None, title: str):
        super().set_art(hero, logo, title)
        if hero is not None and not hero.isNull():
            self._zoom_anim.start()
        else:
            self._zoom_anim.stop()

    def paintEvent(self, event):
        QFrame.paintEvent(self, event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        rect = self.rect()

        if not self.hero.isNull() and rect.width() > 0 and rect.height() > 0:
            zoom = 1.0 + 0.045 * self._zoom
            scaled = self.hero.scaled(
                max(int(rect.width() * zoom), 1),
                max(int(rect.height() * zoom), 1),
                Qt.KeepAspectRatioByExpanding,
                Qt.SmoothTransformation,
            )
            sx = max((scaled.width() - rect.width()) // 2, 0)
            sy = max((scaled.height() - rect.height()) // 2, 0)
            source = QRect(sx, sy, min(rect.width(), scaled.width()), min(rect.height(), scaled.height()))
            painter.drawPixmap(rect, scaled, source)
        else:
            painter.fillRect(rect, QColor("#16202d"))

        # Blend the art into the page instead of ending on a hard edge.
        fade = QLinearGradient(0, 0, 0, rect.height())
        fade.setColorAt(0.0, QColor(27, 40, 56, 10))
        fade.setColorAt(0.60, QColor(27, 40, 56, 70))
        fade.setColorAt(1.0, QColor(27, 40, 56, 255))
        painter.fillRect(rect, fade)
        side = QLinearGradient(0, 0, max(rect.width() * 0.5, 1), 0)
        side.setColorAt(0.0, QColor(22, 32, 45, 200))
        side.setColorAt(1.0, QColor(22, 32, 45, 0))
        painter.fillRect(rect, side)

        if not self.logo.isNull():
            target = self.logo.scaled(400, 132, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            painter.drawPixmap(30, max(rect.height() - target.height() - 26, 12), target)
        else:
            painter.setPen(QColor("#ffffff"))
            font = painter.font()
            font.setPointSize(24)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(30, max(rect.height() - 44, 40), self.fallback_title)

        if self._reveal < 1.0:
            painter.fillRect(rect, QColor(16, 22, 29, int((1.0 - self._reveal) * 150)))
        painter.end()


def format_eta(seconds: float) -> str:
    """Steam-style remaining time: "3 gün 01:20", "41:07", "0:24"."""
    seconds = int(max(0, seconds))
    days, rest = divmod(seconds, 86400)
    hours, rest = divmod(rest, 3600)
    minutes, secs = divmod(rest, 60)
    if days:
        return f"{days} gün {hours:02d}:{minutes:02d}"
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def split_progress_text(text: str) -> tuple[str, str, str]:
    """Split the downloader's own status line into its three parts.

    app_v8 emits "<done> / <total>  •  <speed>/sn  •  <n> stream". Parsing it
    here keeps the Steam-style panel fed with the downloader's real numbers
    instead of inventing metrics; anything unexpected falls back to showing
    the raw line.
    """
    parts = [part.strip() for part in str(text or "").split("•")]
    sizes = parts[0] if parts else ""
    speed = parts[1] if len(parts) > 1 else ""
    streams = parts[2] if len(parts) > 2 else ""
    return sizes, speed, streams


def parse_speed_bytes(speed_text: str) -> float:
    """Read "12,3 MB/sn" back into bytes/sec so peak speed can be tracked.
    Returns 0.0 when the shape is not recognised."""
    cleaned = str(speed_text or "").replace("/sn", "").strip().replace(",", ".")
    parts = cleaned.split()
    if len(parts) < 2:
        return 0.0
    try:
        amount = float(parts[0])
    except ValueError:
        return 0.0
    units = {"B": 1, "KB": 1024, "MB": 1024 ** 2, "GB": 1024 ** 3, "TB": 1024 ** 4}
    return amount * units.get(parts[1].upper(), 0)


class IconLabel(QLabel):
    """Small rounded game icon used in the status bar and download rows."""

    def __init__(self, width: int = 30, height: int = 30, parent=None):
        super().__init__(parent)
        self.setFixedSize(width, height)
        self._pixmap = QPixmap()

    def set_icon(self, pixmap: QPixmap | None):
        self._pixmap = pixmap if pixmap is not None else QPixmap()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        rect = self.rect()
        painter.fillRect(rect, QColor("#0d1319"))
        if not self._pixmap.isNull():
            scaled = self._pixmap.scaled(rect.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            sx = max((scaled.width() - rect.width()) // 2, 0)
            sy = max((scaled.height() - rect.height()) // 2, 0)
            painter.drawPixmap(
                rect, scaled,
                QRect(sx, sy, min(rect.width(), scaled.width()), min(rect.height(), scaled.height())),
            )
        painter.end()


class DownloadHeroPanel(QFrame):
    """Downloads-page banner: the active game's hero art behind a dark scrim,
    matching the way Steam fronts its downloads view with the artwork of
    whatever is currently transferring."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(210)
        self._hero = QPixmap()

    def set_hero(self, pixmap: QPixmap | None):
        self._hero = pixmap if pixmap is not None else QPixmap()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        rect = self.rect()
        if self._hero.isNull():
            painter.fillRect(rect, QColor("#16202d"))
        else:
            scaled = self._hero.scaled(rect.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            sx = max((scaled.width() - rect.width()) // 2, 0)
            sy = max((scaled.height() - rect.height()) // 2, 0)
            painter.drawPixmap(
                rect, scaled,
                QRect(sx, sy, min(rect.width(), scaled.width()), min(rect.height(), scaled.height())),
            )
            scrim = QLinearGradient(0, 0, rect.width(), 0)
            scrim.setColorAt(0.0, QColor(16, 22, 29, 120))
            scrim.setColorAt(0.55, QColor(16, 22, 29, 215))
            scrim.setColorAt(1.0, QColor(16, 22, 29, 245))
            painter.fillRect(rect, scrim)
        painter.end()


class CompletedRow(QFrame):
    """One finished-install row on the downloads page."""

    openRequested = Signal(str)
    removeRequested = Signal(str)

    def __init__(self, record: dict, parent=None):
        super().__init__(parent)
        self.setObjectName("panel")
        self.key = str(record.get("key") or "")
        self.record = record

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(12)

        self.icon = IconLabel(72, 34)
        layout.addWidget(self.icon)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        title = QLabel(str(record.get("title") or "?"))
        title.setObjectName("rowValue")
        subtitle = QLabel(
            f"v{record.get('version', '?')}   •   {str(record.get('channel', '')).upper()}"
        )
        subtitle.setObjectName("muted")
        text_col.addWidget(title)
        text_col.addWidget(subtitle)
        layout.addLayout(text_col, 1)

        stamp = str(record.get("installed_at") or "")[:10]
        when = QLabel(f"TAMAMLANDI: {stamp}" if stamp else "TAMAMLANDI")
        when.setObjectName("statName")
        layout.addWidget(when)

        open_button = QPushButton("KLASÖRÜ AÇ")
        open_button.setObjectName("install")
        open_button.clicked.connect(lambda: self.openRequested.emit(self.key))
        layout.addWidget(open_button)

        remove_button = QPushButton("✕")
        remove_button.setObjectName("iconButton")
        remove_button.setToolTip("Bu kaydı listeden kaldır")
        remove_button.clicked.connect(lambda: self.removeRequested.emit(self.key))
        layout.addWidget(remove_button)


def _stat_pair(name: str, value: str) -> tuple[QWidget, QLabel]:
    box = QWidget()
    layout = QVBoxLayout(box)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(2)
    label = QLabel(name.upper())
    label.setObjectName("statName")
    value_label = QLabel(value)
    value_label.setObjectName("statValue")
    layout.addWidget(label)
    layout.addWidget(value_label)
    return box, value_label


def _panel_row(key: str, value: str) -> tuple[QWidget, QLabel]:
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 3, 0, 3)
    layout.setSpacing(10)
    key_label = QLabel(key)
    key_label.setObjectName("rowKey")
    value_label = QLabel(value)
    value_label.setObjectName("rowValue")
    value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    value_label.setWordWrap(True)
    layout.addWidget(key_label, 0)
    layout.addStretch()
    layout.addWidget(value_label, 1)
    return row, value_label


def _hairline(horizontal: bool = True) -> QFrame:
    line = QFrame()
    line.setObjectName("hairline")
    if horizontal:
        line.setFixedHeight(1)
    else:
        line.setFixedWidth(1)
    return line


class BigPictureView(QWidget):
    """Full-screen, couch-distance shell: search bar, shoulder-button tab
    strip, capsule wall, and a gamepad legend pinned to the bottom. Mirrors
    the real Big Picture library rather than scaling up the desktop UI."""

    tabChanged = Signal(int)
    backRequested = Signal()

    TAB_ALL = 0
    TAB_INSTALLED = 1
    TAB_DOWNLOADS = 2

    PAGE_GRID = 0
    PAGE_DOWNLOADS = 1
    PAGE_GAME = 2

    def __init__(self, grid: GameGridView, parent=None):
        super().__init__(parent)
        self.setObjectName("bigPictureRoot")
        self.grid = grid
        self._tab_index = 0

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QFrame()
        header.setObjectName("bpHeader")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(34, 20, 34, 0)
        header_layout.setSpacing(18)

        search_row = QHBoxLayout()
        search_row.setSpacing(18)
        self.search = QLineEdit()
        self.search.setObjectName("bpSearch")
        self.search.setPlaceholderText("Oyun ara")
        self.search.setClearButtonEnabled(True)
        self.clock = QLabel("")
        self.clock.setObjectName("bpClock")
        self.connection = QLabel("")
        self.connection.setObjectName("bpHint")
        search_row.addWidget(self.search, 1)
        search_row.addWidget(self.connection, 0)
        search_row.addWidget(self.clock, 0)
        header_layout.addLayout(search_row)

        tab_row = QHBoxLayout()
        tab_row.setSpacing(6)
        left_shoulder = QLabel("L1")
        left_shoulder.setObjectName("bpShoulder")
        right_shoulder = QLabel("R1")
        right_shoulder.setObjectName("bpShoulder")
        tab_row.addWidget(left_shoulder, 0, Qt.AlignVCenter)
        tab_row.addStretch()

        self._tabs: list[ClickableLabel] = []
        for index, text in enumerate(("TÜM OYUNLAR", "YÜKLÜ", "İNDİRMELER")):
            tab = ClickableLabel(text)
            tab.setObjectName("bpTabActive" if index == 0 else "bpTab")
            tab.clicked.connect(lambda i=index: self.set_tab(i))
            self._tabs.append(tab)
            tab_row.addWidget(tab)

        tab_row.addStretch()
        tab_row.addWidget(right_shoulder, 0, Qt.AlignVCenter)
        header_layout.addLayout(tab_row)
        outer.addWidget(header)

        self.stack = QStackedWidget()
        grid_page = QWidget()
        grid_layout = QVBoxLayout(grid_page)
        grid_layout.setContentsMargins(30, 14, 30, 0)
        grid_layout.setSpacing(0)
        self.grid.setObjectName("bpGrid")
        grid_layout.addWidget(self.grid)
        self.stack.addWidget(grid_page)
        self.stack.addWidget(self._build_downloads_page())
        self.stack.addWidget(self._build_game_page())
        outer.addWidget(self.stack, 1)
        self.header = header

        footer = QFrame()
        footer.setObjectName("bpFooter")
        footer.setFixedHeight(46)
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(30, 0, 30, 0)
        footer_layout.setSpacing(10)
        steam_pill = QLabel("DROWNED")
        steam_pill.setObjectName("bpSteamPill")
        menu_hint = QLabel("MENÜ")
        menu_hint.setObjectName("bpFooterText")
        footer_layout.addWidget(steam_pill)
        footer_layout.addWidget(menu_hint)
        footer_layout.addStretch()
        self._hint_labels: list[tuple[QLabel, QLabel]] = []
        for glyph, text in (("A", "SEÇ"), ("B", "GERİ"), ("LB", "SEKME"), ("ST", "PENCERE")):
            badge = QLabel(glyph)
            badge.setObjectName("bpGlyph")
            badge.setAlignment(Qt.AlignCenter)
            if len(glyph) > 1:
                badge.setMinimumWidth(30)
                badge.setMaximumWidth(30)
            hint = QLabel(text)
            hint.setObjectName("bpHint")
            footer_layout.addWidget(badge)
            footer_layout.addWidget(hint)
            footer_layout.addSpacing(10)
            self._hint_labels.append((badge, hint))
        outer.addWidget(footer)

        self._clock_timer = QTimer(self)
        self._clock_timer.setInterval(20000)
        self._clock_timer.timeout.connect(self._tick_clock)
        self._clock_timer.start()
        self._tick_clock()

    def _build_downloads_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(34, 20, 34, 20)
        layout.setSpacing(14)

        self.dl_title = QLabel("Etkin indirme yok")
        self.dl_title.setObjectName("bpBigTitle")
        layout.addWidget(self.dl_title)

        self.dl_meta = QLabel("Bir oyun seçip YÜKLE ile indirmeyi başlat.")
        self.dl_meta.setObjectName("bpMeta")
        layout.addWidget(self.dl_meta)

        self.dl_progress = QProgressBar()
        self.dl_progress.setObjectName("fatBar")
        self.dl_progress.setRange(0, 100)
        self.dl_progress.setValue(0)
        self.dl_progress.setTextVisible(False)
        layout.addWidget(self.dl_progress)

        # Attribute names are spelled out rather than derived from the label
        # text: str.lower() on a Turkish dotted capital "I" yields "i" plus a
        # combining dot, so a generated attribute name would never match the
        # one the caller looks up.
        stats = QHBoxLayout()
        stats.setSpacing(46)
        self.dl_metric_progress = self._metric_box(stats, "İLERLEME")
        self.dl_metric_state = self._metric_box(stats, "DURUM")
        self.dl_metric_channel = self._metric_box(stats, "KANAL")
        stats.addStretch()
        layout.addLayout(stats)

        layout.addSpacing(8)
        installed_caption = QLabel("KURULU OYUNLAR")
        installed_caption.setObjectName("bpSectionTitle")
        layout.addWidget(installed_caption)

        self.dl_installed = QLabel("Henüz kurulu oyun yok.")
        self.dl_installed.setObjectName("bpMeta")
        self.dl_installed.setWordWrap(True)
        self.dl_installed.setAlignment(Qt.AlignTop)
        layout.addWidget(self.dl_installed, 1)
        return page

    def _build_game_page(self) -> QWidget:
        """Couch-distance game page. Every control here is reachable with the
        D-pad and A/B alone, so a controller-only session never needs the
        desktop shell."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.game_hero = DownloadHeroPanel()
        self.game_hero.setFixedHeight(300)
        hero_layout = QVBoxLayout(self.game_hero)
        hero_layout.setContentsMargins(40, 0, 40, 26)
        hero_layout.addStretch(1)
        self.game_title = QLabel("—")
        self.game_title.setObjectName("bpBigTitle")
        self.game_meta = QLabel("")
        self.game_meta.setObjectName("bpMeta")
        hero_layout.addWidget(self.game_title)
        hero_layout.addWidget(self.game_meta)
        layout.addWidget(self.game_hero)

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(40, 22, 40, 24)
        body_layout.setSpacing(16)

        actions = QHBoxLayout()
        actions.setSpacing(12)
        self.action_buttons: list[QPushButton] = []
        for name, text, object_name in (
            ("bp_install", "YÜKLE", "install"),
            ("bp_pause", "DURAKLAT", "pauseButton"),
            ("bp_cancel", "İPTAL", "danger"),
            ("bp_verify", "DOĞRULA", "secondary"),
            ("bp_uninstall", "KALDIR", "danger"),
        ):
            button = QPushButton(text)
            button.setObjectName(object_name)
            button.setMinimumHeight(46)
            button.setFocusPolicy(Qt.StrongFocus)
            setattr(self, name, button)
            actions.addWidget(button)
            self.action_buttons.append(button)
        actions.addStretch()
        body_layout.addLayout(actions)

        self.game_progress = QProgressBar()
        self.game_progress.setObjectName("fatBar")
        self.game_progress.setRange(0, 100)
        self.game_progress.setValue(0)
        self.game_progress.setTextVisible(False)
        self.game_progress.hide()
        body_layout.addWidget(self.game_progress)

        self.game_status = QLabel("")
        self.game_status.setObjectName("bpMeta")
        self.game_status.hide()
        body_layout.addWidget(self.game_status)

        self.game_description = QLabel("")
        self.game_description.setObjectName("bpMeta")
        self.game_description.setWordWrap(True)
        self.game_description.setAlignment(Qt.AlignTop)
        body_layout.addWidget(self.game_description, 1)

        layout.addWidget(body, 1)
        self._action_index = 0
        return page

    # -- page control ----------------------------------------------------

    def show_game_page(self) -> None:
        self.stack.setCurrentIndex(self.PAGE_GAME)
        self.header.hide()
        self._set_hints((("A", "UYGULA"), ("B", "KÜTÜPHANE"), ("LB", "SEKME"), ("ST", "PENCERE")))
        self.focus_action(0)

    def show_grid(self) -> None:
        self.header.show()
        self.stack.setCurrentIndex(
            self.PAGE_DOWNLOADS if self._tab_index == self.TAB_DOWNLOADS else self.PAGE_GRID
        )
        self._set_hints((("A", "SEÇ"), ("B", "GERİ"), ("LB", "SEKME"), ("ST", "PENCERE")))

    def _set_hints(self, pairs) -> None:
        for (badge, hint), (glyph, text) in zip(self._hint_labels, pairs):
            badge.setText(glyph)
            hint.setText(text)

    @property
    def on_game_page(self) -> bool:
        return self.stack.currentIndex() == self.PAGE_GAME

    def visible_actions(self) -> list[QPushButton]:
        return [button for button in self.action_buttons if button.isVisible() and button.isEnabled()]

    # The tracked index, not Qt focus, is the source of truth for controller
    # navigation: hasFocus() is false whenever the window is inactive, and a
    # stray mouse click elsewhere would otherwise strand the D-pad.
    def focus_action(self, index: int) -> None:
        buttons = self.visible_actions()
        if not buttons:
            self._action_index = 0
            return
        self._action_index = max(0, min(index, len(buttons) - 1))
        buttons[self._action_index].setFocus(Qt.OtherFocusReason)

    def move_action_focus(self, delta: int) -> None:
        buttons = self.visible_actions()
        if not buttons:
            return
        current = next(
            (i for i, button in enumerate(buttons) if button.hasFocus()),
            min(self._action_index, len(buttons) - 1),
        )
        self.focus_action((current + delta) % len(buttons))

    def focused_action(self) -> QPushButton | None:
        buttons = self.visible_actions()
        if not buttons:
            return None
        for button in buttons:
            if button.hasFocus():
                return button
        return buttons[min(self._action_index, len(buttons) - 1)]

    def activate_focused_action(self) -> bool:
        button = self.focused_action()
        if button is None or not button.isEnabled():
            return False
        button.click()
        return True

    @staticmethod
    def _metric_box(row: QHBoxLayout, caption_text: str) -> QLabel:
        box = QWidget()
        box_layout = QVBoxLayout(box)
        box_layout.setContentsMargins(0, 0, 0, 0)
        box_layout.setSpacing(3)
        caption = QLabel(caption_text)
        caption.setObjectName("statName")
        value = QLabel("—")
        value.setObjectName("bigMetric")
        box_layout.addWidget(caption)
        box_layout.addWidget(value)
        row.addWidget(box)
        return value

    def _tick_clock(self):
        self.clock.setText(QDateTime.currentDateTime().toString("HH:mm"))

    def set_tab(self, index: int) -> None:
        index = max(0, min(index, len(self._tabs) - 1))
        self._tab_index = index
        for i, tab in enumerate(self._tabs):
            tab.setObjectName("bpTabActive" if i == index else "bpTab")
            tab.style().unpolish(tab)
            tab.style().polish(tab)
        self.stack.setCurrentIndex(1 if index == self.TAB_DOWNLOADS else 0)
        self.tabChanged.emit(index)

    def cycle_tab(self, delta: int = 1) -> None:
        self.set_tab((self._tab_index + delta) % len(self._tabs))

    @property
    def tab_index(self) -> int:
        return self._tab_index

    def set_tab_counts(self, total: int, installed: int) -> None:
        self._tabs[self.TAB_ALL].setText(f"TÜM OYUNLAR  {total}")
        self._tabs[self.TAB_INSTALLED].setText(f"YÜKLÜ  {installed}")


class Launcher(previous.Launcher):
    def __init__(self):
        self._dl_started_at = None
        self._dl_peak_bytes = 0.0
        self._dl_peak_text = ""
        self._requested_images: set[str] = set()
        super().__init__()

        # app_v8 injects the pause/cancel buttons at fixed indices near the
        # front of the status row. Steam keeps transfer controls on the right
        # of the bar, so move them to the end now that they exist. Only the
        # layout order changes; the buttons and their wiring are untouched.
        for button in (self.pause_button, self.cancel_button):
            self._status_row.removeWidget(button)
            self._status_row.addWidget(button)
            button.setObjectName("pauseButton" if button is self.pause_button else "danger")
            button.setStyleSheet("")

        self.progress.hide()
        self._refresh_downloads_page()
        self._refresh_side_panels()

    def _build_ui(self):
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._chrome_widgets: list[QWidget] = []

        # ---- window menu strip ---------------------------------------------
        menubar = QFrame()
        menubar.setObjectName("menubar")
        menubar.setFixedHeight(26)
        menu_layout = QHBoxLayout(menubar)
        menu_layout.setContentsMargins(10, 0, 10, 0)
        menu_layout.setSpacing(0)
        mark = QLabel("D")
        mark.setObjectName("brandMark")
        mark.setAlignment(Qt.AlignCenter)
        mark.setFixedSize(18, 18)
        menu_layout.addWidget(mark)
        menu_layout.addSpacing(8)
        for text in ("Drowned", "Görünüm", "Kütüphane", "Yardım"):
            item = QLabel(text)
            item.setObjectName("menuItem")
            menu_layout.addWidget(item)
        menu_layout.addStretch()
        self.connection = QLabel("RAW • bağlanıyor")
        self.connection.setObjectName("connectionOnline")
        menu_layout.addWidget(self.connection)
        outer.addWidget(menubar)
        self._chrome_widgets.append(menubar)

        # ---- primary navigation --------------------------------------------
        navbar = QFrame()
        navbar.setObjectName("navbar")
        navbar.setFixedHeight(44)
        nav_layout = QHBoxLayout(navbar)
        nav_layout.setContentsMargins(12, 0, 12, 0)
        nav_layout.setSpacing(2)

        self.nav_library = ClickableLabel("KÜTÜPHANE")
        self.nav_library.setObjectName("navActive")
        self.nav_downloads = ClickableLabel("İNDİRMELER")
        self.nav_downloads.setObjectName("nav")
        self.nav_library.clicked.connect(lambda: self._show_right_page(0))
        self.nav_downloads.clicked.connect(lambda: self._show_right_page(1))
        nav_layout.addWidget(self.nav_library)
        nav_layout.addWidget(self.nav_downloads)
        nav_layout.addStretch()

        self.big_picture_button = QPushButton("⛶")
        self.big_picture_button.setObjectName("iconButton")
        self.big_picture_button.setToolTip("Geniş ekran / Big Picture modu (F11)")
        refresh = QPushButton("↻")
        refresh.setObjectName("iconButton")
        refresh.setToolTip("Kataloğu yenile")
        refresh.clicked.connect(self.load_catalog)
        settings_button = QPushButton("⚙")
        settings_button.setObjectName("iconButton")
        settings_button.setToolTip("Ayarlar")
        settings_button.clicked.connect(self.open_settings)
        nav_layout.addWidget(self.big_picture_button)
        nav_layout.addWidget(refresh)
        nav_layout.addWidget(settings_button)
        outer.addWidget(navbar)
        self._chrome_widgets.append(navbar)

        # ---- main stack: desktop shell / big picture ------------------------
        self.main_stack = QStackedWidget()
        self.main_stack.addWidget(self._build_desktop_shell())

        self.library_grid_bp = GameGridView()
        self.big_picture = BigPictureView(self.library_grid_bp)
        self.main_stack.addWidget(self.big_picture)
        outer.addWidget(self.main_stack, 1)

        # ---- download strip -------------------------------------------------
        download = QFrame()
        download.setObjectName("downloadBar")
        download_outer = QVBoxLayout(download)
        download_outer.setContentsMargins(14, 7, 14, 8)
        download_outer.setSpacing(0)

        self.download_card = QFrame()
        self.download_card.setObjectName("downloadCard")
        dl = QVBoxLayout(self.download_card)
        dl.setContentsMargins(0, 0, 0, 0)
        dl.setSpacing(5)

        # Steam's status bar keeps the whole transfer on one line: game icon,
        # "İndiriliyor: n/n", a long thin bar, then the percentage.
        status_row = QHBoxLayout()
        status_row.setSpacing(9)
        self.download_dot = QLabel("●")
        self.download_dot.setObjectName("downloadDot")
        self.status_icon = IconLabel(26, 26)
        self.status_icon.hide()
        self.status = QLabel("Hazır")
        self.status.setObjectName("downloadTitle")
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress_text = QLabel("")
        self.progress_text.setObjectName("progressText")

        status_row.addWidget(self.download_dot)
        status_row.addWidget(self.status_icon)
        status_row.addWidget(self.status)
        status_row.addWidget(self.progress, 1)
        status_row.addWidget(self.progress_text)
        self._status_row = status_row

        self.logs = QPlainTextEdit()
        self.logs.setReadOnly(True)
        self.logs.setFixedHeight(58)
        self.logs.hide()

        dl.addLayout(status_row)
        dl.addWidget(self.logs)
        download_outer.addWidget(self.download_card)
        outer.addWidget(download)
        self._chrome_widgets.append(download)

        self._wire_runtime()

    # -- desktop shell -------------------------------------------------------

    def _build_desktop_shell(self) -> QWidget:
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        self.main_splitter = splitter

        splitter.addWidget(self._build_sidebar())

        right = QFrame()
        right.setObjectName("detail")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        self.right_stack = QStackedWidget()
        self.right_stack.addWidget(self._build_game_page())
        self.right_stack.addWidget(self._build_downloads_page())
        right_layout.addWidget(self.right_stack)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([300, 1180])
        return splitter

    def _build_sidebar(self) -> QWidget:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setMinimumWidth(250)
        sidebar.setMaximumWidth(420)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(10, 10, 6, 8)
        side.setSpacing(7)

        header = QHBoxLayout()
        title = QLabel("KÜTÜPHANE ANA SAYFASI")
        title.setObjectName("sectionLabel")
        self.game_count = QLabel("0 oyun")
        self.game_count.setObjectName("muted")
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.game_count)
        side.addLayout(header)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Ara")
        self.search.setClearButtonEnabled(True)
        self._search_debounce = QTimer(self)
        self._search_debounce.setSingleShot(True)
        self._search_debounce.setInterval(150)
        self._search_debounce.timeout.connect(self.render_library)
        self.search.textChanged.connect(lambda _text: self._search_debounce.start())
        side.addWidget(self.search)

        filters = QHBoxLayout()
        filters.setSpacing(5)
        self.platform = QComboBox()
        self.platform.addItem("Tümü")
        self.channel = QComboBox()
        self.channel.addItems(["stable", "beta", "dev", "nightly", "archive"])
        self.platform.currentTextChanged.connect(self.render_library)
        self.channel.currentTextChanged.connect(self.render_library)
        filters.addWidget(self.platform, 1)
        filters.addWidget(self.channel, 1)
        side.addLayout(filters)

        # The single source of truth for selection. Every inherited method
        # (render_library, library_selection_changed, install_*) reads and
        # writes this exact QListWidget, so it stays alive and wired; the
        # visible list and the Big Picture wall are mirrors that drive it
        # through setCurrentRow().
        self.library = QListWidget()
        self.library.setSpacing(1)
        self.library.currentItemChanged.connect(self.library_selection_changed)
        self.library.hide()
        side.addWidget(self.library)

        self.library_grid = GameListView()
        side.addWidget(self.library_grid, 1)
        return sidebar

    def _build_game_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.hero = SteamHeroView()
        layout.addWidget(self.hero)

        # ---- action bar: PLAY button plus the stat strip -------------------
        action_bar = QFrame()
        action_bar.setObjectName("actionBar")
        action_layout = QHBoxLayout(action_bar)
        action_layout.setContentsMargins(30, 14, 30, 14)
        action_layout.setSpacing(22)

        self.info_card = QFrame()
        self.info_card.setObjectName("infoCard")
        info = QHBoxLayout(self.info_card)
        info.setContentsMargins(0, 0, 0, 0)
        info.setSpacing(10)
        self.install_button = QPushButton("YÜKLE")
        self.install_button.setObjectName("install")
        self.install_button.clicked.connect(self.install_current_game)
        self.install_button.setEnabled(False)
        self.verify_button = QPushButton("DOSYALARI DOĞRULA")
        self.verify_button.setObjectName("secondary")
        self.verify_button.setEnabled(False)
        info.addWidget(self.install_button)
        info.addWidget(self.verify_button)
        action_layout.addWidget(self.info_card, 0)

        # While a download runs Steam turns this spot into a pause control
        # plus an inline "İNDİRİLİYOR / %n Tamamlandı" readout.
        self.action_dl = QWidget()
        action_dl_layout = QHBoxLayout(self.action_dl)
        action_dl_layout.setContentsMargins(0, 0, 0, 0)
        action_dl_layout.setSpacing(14)
        self.action_pause = QPushButton("DURAKLAT")
        self.action_pause.setObjectName("pauseButton")
        self.action_pause.clicked.connect(self.toggle_pause)
        action_dl_layout.addWidget(self.action_pause)

        dl_text_col = QVBoxLayout()
        dl_text_col.setSpacing(3)
        self.action_dl_caption = QLabel("İNDİRİLİYOR")
        self.action_dl_caption.setObjectName("statName")
        self.action_dl_value = QLabel("%0 Tamamlandı")
        self.action_dl_value.setObjectName("rowValue")
        self.action_dl_bar = QProgressBar()
        self.action_dl_bar.setRange(0, 100)
        self.action_dl_bar.setValue(0)
        self.action_dl_bar.setTextVisible(False)
        self.action_dl_bar.setFixedWidth(150)
        dl_text_col.addWidget(self.action_dl_caption)
        dl_text_col.addWidget(self.action_dl_value)
        dl_text_col.addWidget(self.action_dl_bar)
        action_dl_layout.addLayout(dl_text_col)
        self.action_dl.hide()
        action_layout.addWidget(self.action_dl, 0)

        action_layout.addWidget(_hairline(horizontal=False))

        stats = QHBoxLayout()
        stats.setSpacing(34)
        box, self.stat_platform = _stat_pair("Platform", "—")
        stats.addWidget(box)
        box, self.stat_channel = _stat_pair("Kanal", "—")
        stats.addWidget(box)
        box, self.stat_version = _stat_pair("Sürüm", "—")
        stats.addWidget(box)
        box, self.stat_size = _stat_pair("Boyut", "—")
        stats.addWidget(box)
        action_layout.addLayout(stats)
        action_layout.addStretch()

        self.state_badge = QLabel("HAZIR")
        self.state_badge.setObjectName("connectionOnline")
        action_layout.addWidget(self.state_badge, 0, Qt.AlignVCenter)
        layout.addWidget(action_bar)

        # ---- content: title, tabs, two columns -----------------------------
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(30, 18, 30, 18)
        content_layout.setSpacing(0)

        self.title = QLabel("Kütüphane yükleniyor…")
        self.title.setObjectName("gameTitle")
        self.meta = QLabel("")
        self.meta.setObjectName("metaLine")
        content_layout.addWidget(self.title)
        content_layout.addWidget(self.meta)
        content_layout.addSpacing(14)

        tab_row = QHBoxLayout()
        tab_row.setSpacing(0)
        self.tab_overview = ClickableLabel("GENEL BAKIŞ")
        self.tab_overview.setObjectName("tabActive")
        self.tab_shots = ClickableLabel("EKRAN GÖRÜNTÜLERİ")
        self.tab_shots.setObjectName("tab")
        self.tab_overview.clicked.connect(lambda: self._show_detail_tab(0))
        self.tab_shots.clicked.connect(lambda: self._show_detail_tab(1))
        tab_row.addWidget(self.tab_overview)
        tab_row.addWidget(self.tab_shots)
        tab_row.addStretch()
        content_layout.addLayout(tab_row)
        content_layout.addWidget(_hairline())
        content_layout.addSpacing(16)

        columns = QHBoxLayout()
        columns.setSpacing(24)

        self.detail_stack = QStackedWidget()

        overview = QWidget()
        overview_layout = QVBoxLayout(overview)
        overview_layout.setContentsMargins(0, 0, 0, 0)
        overview_layout.setSpacing(0)
        self.description = QLabel("Raw GitHub kataloğundan oyunlar yükleniyor.")
        self.description.setObjectName("description")
        self.description.setWordWrap(True)
        self.description.setAlignment(Qt.AlignTop)
        overview_layout.addWidget(self.description)
        overview_layout.addStretch()
        self.detail_stack.addWidget(overview)

        shots_page = QWidget()
        shots_layout = QVBoxLayout(shots_page)
        shots_layout.setContentsMargins(0, 0, 0, 0)
        shots_layout.setSpacing(0)
        self.screenshot_gallery = ScreenshotGallery()
        shots_layout.addWidget(self.screenshot_gallery)
        shots_layout.addStretch()
        self.detail_stack.addWidget(shots_page)

        columns.addWidget(self.detail_stack, 1)
        columns.addWidget(self._build_side_panels(), 0)
        content_layout.addLayout(columns, 1)
        layout.addWidget(content, 1)

        # The inherited artwork pipeline still writes a cover pixmap into
        # this widget. Steam's game page shows no separate boxed cover, so it
        # stays alive but hidden rather than being removed.
        self.cover = previous.CoverLabel()
        self.cover.setParent(page)
        self.cover.hide()
        return page

    def _build_side_panels(self) -> QWidget:
        column = QWidget()
        column.setFixedWidth(320)
        layout = QVBoxLayout(column)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        install_panel = QFrame()
        install_panel.setObjectName("panel")
        install_layout = QVBoxLayout(install_panel)
        install_layout.setContentsMargins(14, 12, 14, 12)
        install_layout.setSpacing(2)
        caption = QLabel("KURULUM")
        caption.setObjectName("panelTitle")
        install_layout.addWidget(caption)
        install_layout.addSpacing(6)
        row, self.panel_state = _panel_row("Durum", "—")
        install_layout.addWidget(row)
        row, self.panel_path = _panel_row("Klasör", "—")
        install_layout.addWidget(row)
        row, self.panel_tag = _panel_row("Etiket", "—")
        install_layout.addWidget(row)
        layout.addWidget(install_panel)

        source_panel = QFrame()
        source_panel.setObjectName("panel")
        source_layout = QVBoxLayout(source_panel)
        source_layout.setContentsMargins(14, 12, 14, 12)
        source_layout.setSpacing(2)
        caption = QLabel("KAYNAK")
        caption.setObjectName("panelTitle")
        source_layout.addWidget(caption)
        source_layout.addSpacing(6)
        row, self.panel_repo = _panel_row("Repo", "—")
        source_layout.addWidget(row)
        row, self.panel_branch = _panel_row("Branch", "—")
        source_layout.addWidget(row)
        layout.addWidget(source_panel)

        layout.addStretch()
        return column

    def _build_downloads_page(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ---- banner with the live transfer panel over the artwork ----------
        self.dlp_hero = DownloadHeroPanel()
        hero_layout = QHBoxLayout(self.dlp_hero)
        hero_layout.setContentsMargins(30, 18, 30, 18)
        hero_layout.addStretch(1)

        panel = QWidget()
        panel.setAttribute(Qt.WA_TranslucentBackground)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(7)
        panel.setMinimumWidth(560)

        metrics = QHBoxLayout()
        metrics.setSpacing(30)
        self.dlp_net = self._metric_column(metrics, "AĞ")
        self.dlp_peak = self._metric_column(metrics, "EN YÜKSEK")
        self.dlp_streams = self._metric_column(metrics, "AKIŞ")
        metrics.addStretch()
        panel_layout.addLayout(metrics)

        self.dlp_limit = QLabel("BAĞLANTI: raw.githubusercontent.com + GitHub Releases")
        self.dlp_limit.setObjectName("statName")
        panel_layout.addWidget(self.dlp_limit)
        panel_layout.addSpacing(4)

        data_row = QHBoxLayout()
        data_caption = QLabel("Veriler İndiriliyor")
        data_caption.setObjectName("rowValue")
        self.dlp_bytes = QLabel("—")
        self.dlp_bytes.setObjectName("rowValue")
        data_row.addWidget(data_caption)
        data_row.addStretch()
        data_row.addWidget(self.dlp_bytes)
        panel_layout.addLayout(data_row)

        self.dlp_bar = QProgressBar()
        self.dlp_bar.setObjectName("fatBar")
        self.dlp_bar.setRange(0, 100)
        self.dlp_bar.setValue(0)
        self.dlp_bar.setTextVisible(False)
        panel_layout.addWidget(self.dlp_bar)

        verify_row = QHBoxLayout()
        verify_caption = QLabel("Dosyalar Doğrulanıyor")
        verify_caption.setObjectName("rowValue")
        self.dlp_percent = QLabel("%0")
        self.dlp_percent.setObjectName("rowValue")
        verify_row.addWidget(verify_caption)
        verify_row.addStretch()
        verify_row.addWidget(self.dlp_percent)
        panel_layout.addLayout(verify_row)

        bottom_row = QHBoxLayout()
        self.dlp_eta = QLabel("Kalan tahmini süre: —")
        self.dlp_eta.setObjectName("muted")
        bottom_row.addWidget(self.dlp_eta)
        bottom_row.addStretch()
        self.dlp_pause = QPushButton("DURAKLAT")
        self.dlp_pause.setObjectName("secondary")
        self.dlp_pause.clicked.connect(self.toggle_pause)
        self.dlp_pause.hide()
        bottom_row.addWidget(self.dlp_pause)
        panel_layout.addLayout(bottom_row)

        hero_layout.addWidget(panel, 0)
        outer.addWidget(self.dlp_hero)

        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(30, 18, 30, 18)
        layout.setSpacing(0)

        self.dlp_title = QLabel("Etkin indirme yok")
        self.dlp_title.setObjectName("gameTitle")
        layout.addWidget(self.dlp_title)
        self.dlp_detail = QLabel("Kütüphaneden bir oyun seçip YÜKLE ile indirmeyi başlat.")
        self.dlp_detail.setObjectName("muted")
        self.dlp_detail.setWordWrap(True)
        layout.addWidget(self.dlp_detail)
        layout.addSpacing(20)

        queue_head = QHBoxLayout()
        self.dlp_queue_caption = QLabel("SIRADAKİ (0)")
        self.dlp_queue_caption.setObjectName("panelTitle")
        queue_note = QLabel("Tek seferde bir indirme çalışır")
        queue_note.setObjectName("muted")
        queue_head.addWidget(self.dlp_queue_caption)
        queue_head.addStretch()
        queue_head.addWidget(queue_note)
        layout.addLayout(queue_head)
        layout.addWidget(_hairline())
        layout.addSpacing(8)
        self.dlp_queue_body = QLabel("Kuyrukta indirme yok.")
        self.dlp_queue_body.setObjectName("muted")
        layout.addWidget(self.dlp_queue_body)
        layout.addSpacing(22)

        done_head = QHBoxLayout()
        self.dlp_done_caption = QLabel("TAMAMLANDI (0)")
        self.dlp_done_caption.setObjectName("panelTitle")
        done_head.addWidget(self.dlp_done_caption)
        done_head.addStretch()
        layout.addLayout(done_head)
        layout.addWidget(_hairline())
        layout.addSpacing(8)

        self.dlp_done_empty = QLabel("Henüz tamamlanmış kurulum yok.")
        self.dlp_done_empty.setObjectName("muted")
        layout.addWidget(self.dlp_done_empty)

        self.dlp_rows_layout = QVBoxLayout()
        self.dlp_rows_layout.setSpacing(6)
        layout.addLayout(self.dlp_rows_layout)
        layout.addStretch(1)

        scroller = QScrollArea()
        scroller.setWidgetResizable(True)
        scroller.setFrameShape(QFrame.NoFrame)
        scroller.setWidget(body)
        outer.addWidget(scroller, 1)
        self._completed_rows: list[CompletedRow] = []
        return page

    @staticmethod
    def _metric_column(row: QHBoxLayout, caption_text: str) -> QLabel:
        box = QWidget()
        box_layout = QVBoxLayout(box)
        box_layout.setContentsMargins(0, 0, 0, 0)
        box_layout.setSpacing(2)
        caption = QLabel(caption_text)
        caption.setObjectName("statName")
        value = QLabel("—")
        value.setObjectName("rowValue")
        box_layout.addWidget(caption)
        box_layout.addWidget(value)
        row.addWidget(box)
        return value

    # -- runtime wiring ------------------------------------------------------

    def _wire_runtime(self):
        self._detail_opacity = QGraphicsOpacityEffect(self.info_card)
        self._detail_opacity.setOpacity(1.0)
        self.info_card.setGraphicsEffect(self._detail_opacity)
        self._detail_fade = QPropertyAnimation(self._detail_opacity, b"opacity", self)
        self._detail_fade.setDuration(220)
        self._detail_fade.setEasingCurve(QEasingCurve.OutCubic)

        self._tile_cover_cache: dict[str, QPixmap] = {}
        self._screenshot_pixmap_cache: dict[str, QPixmap] = {}
        self._screenshot_token = ""

        for view in (self.library_grid, self.library_grid_bp):
            view.tileActivated.connect(self.library.setCurrentRow)
            view.coverRequested.connect(self._on_cover_requested)
            view.show_loading_skeleton(10 if view is self.library_grid_bp else 12)

        self.screenshot_gallery.thumbRequested.connect(self._on_screenshot_requested)

        self.big_picture.search.textChanged.connect(self._mirror_bp_search)
        self.big_picture.tabChanged.connect(self._on_bp_tab_changed)

        # Big Picture actions reuse the inherited flows verbatim, so the
        # couch experience and the desktop one cannot drift apart.
        self.big_picture.bp_install.clicked.connect(self.install_current_game)
        self.big_picture.bp_verify.clicked.connect(self.verify_current_game)
        self.big_picture.bp_uninstall.clicked.connect(self.uninstall_current_game)
        self.big_picture.bp_pause.clicked.connect(self.toggle_pause)
        self.big_picture.bp_cancel.clicked.connect(self.cancel_download)

        self._big_picture = False
        self._pre_big_picture_geometry = None
        self.big_picture_button.clicked.connect(self._toggle_big_picture)
        self._bp_shortcut = QShortcut(QKeySequence("F11"), self)
        self._bp_shortcut.activated.connect(self._toggle_big_picture)
        self._esc_shortcut = QShortcut(QKeySequence("Esc"), self)
        self._esc_shortcut.activated.connect(self._exit_big_picture)

        self._gamepad = None
        if GamepadPoller is not None:
            self._gamepad = GamepadPoller(self, is_active=self.isActiveWindow)
            self._gamepad.action.connect(self._on_gamepad_action)
            self._gamepad.start()

        self.library_grid.setFocus()

    # -- navigation ----------------------------------------------------------

    def _show_right_page(self, index: int):
        self.right_stack.setCurrentIndex(index)
        self.nav_library.setObjectName("navActive" if index == 0 else "nav")
        self.nav_downloads.setObjectName("navActive" if index == 1 else "nav")
        for label in (self.nav_library, self.nav_downloads):
            label.style().unpolish(label)
            label.style().polish(label)
        if index == 1:
            self._refresh_downloads_page()

    def _show_detail_tab(self, index: int):
        self.detail_stack.setCurrentIndex(index)
        self.tab_overview.setObjectName("tabActive" if index == 0 else "tab")
        self.tab_shots.setObjectName("tabActive" if index == 1 else "tab")
        for label in (self.tab_overview, self.tab_shots):
            label.style().unpolish(label)
            label.style().polish(label)

    def _mirror_bp_search(self, text: str):
        if self.search.text() != text:
            self.search.setText(text)

    def _on_bp_tab_changed(self, index: int):
        if index == BigPictureView.TAB_DOWNLOADS:
            self._refresh_downloads_page()
        else:
            self.render_library()

    # -- library sync --------------------------------------------------------

    def _installed_keys(self) -> set[str]:
        keys = set()
        for row in range(self.library.count()):
            payload = self.library.item(row).data(Qt.UserRole)
            if not payload:
                continue
            game, channel = payload
            record = self._record(game, channel)
            if record and self._record_path_exists(record):
                keys.add(self._key(game, channel))
        return keys

    @staticmethod
    def _is_recent(data: dict) -> bool:
        raw = str(data.get("published_at") or "")
        if not raw:
            return False
        try:
            published = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return False
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - published < timedelta(days=14)

    def render_library(self):
        super().render_library()
        if not hasattr(self, "library_grid"):
            return

        rows = []
        badges: dict[str, str] = {}
        for row in range(self.library.count()):
            payload = self.library.item(row).data(Qt.UserRole)
            if not payload:
                continue
            game, channel = payload
            key = self._key(game, channel)
            rows.append((key, game, channel))
            data = (game.get("channels") or {}).get(channel) or {}
            if self._is_recent(data):
                badges[key] = "YENİ"

        installed = self._installed_keys()
        bp_rows = rows
        if self.big_picture.tab_index == BigPictureView.TAB_INSTALLED:
            bp_rows = [item for item in rows if item[0] in installed]

        self.library_grid.set_items(rows)
        self.library_grid_bp.set_items(bp_rows)
        for key, text in badges.items():
            self.library_grid_bp.set_tile_badge(key, text)
        for view in (self.library_grid, self.library_grid_bp):
            view.set_current_row(self.library.currentRow())
        self.big_picture.set_tab_counts(len(rows), len(installed))

    def library_selection_changed(self, current, previous_item):
        super().library_selection_changed(current, previous_item)
        if hasattr(self, "library_grid"):
            for view in (self.library_grid, self.library_grid_bp):
                view.set_current_row(self.library.currentRow())
        self._load_screenshot_gallery()
        self._refresh_side_panels()
        self._sync_big_picture_game()

    def _sync_big_picture_game(self):
        """Mirror the current selection onto the Big Picture game page and
        keep its action buttons in step with the desktop ones."""
        bp = getattr(self, "big_picture", None)
        if bp is None:
            return

        if not self.current_game:
            bp.game_title.setText("Oyun seçilmedi")
            bp.game_meta.setText("")
            bp.game_description.setText("")
            bp.game_hero.set_hero(None)
            return

        bp.game_title.setText(str(self.current_game.get("title") or "—"))
        bp.game_meta.setText(self.meta.text())
        bp.game_description.setText(str(self.current_game.get("description") or ""))
        bp.game_hero.set_hero(self.hero.hero if not self.hero.hero.isNull() else None)
        self._sync_big_picture_actions()

    def _sync_big_picture_actions(self):
        bp = getattr(self, "big_picture", None)
        if bp is None:
            return
        downloading = self.download_control is not None

        bp.bp_install.setText(self.install_button.text())
        bp.bp_install.setEnabled(self.install_button.isEnabled())
        bp.bp_install.setVisible(not downloading)
        bp.bp_verify.setEnabled(self.verify_button.isEnabled())
        bp.bp_verify.setVisible(not downloading)
        bp.bp_uninstall.setEnabled(self.uninstall_button.isEnabled())
        bp.bp_uninstall.setVisible(not downloading)
        bp.bp_pause.setVisible(downloading)
        bp.bp_cancel.setVisible(downloading)
        bp.game_progress.setVisible(downloading)
        bp.game_status.setVisible(downloading)

    def update_install_state_ui(self):
        super().update_install_state_ui()
        self._sync_big_picture_actions()

    def _refresh_side_panels(self):
        if not hasattr(self, "panel_state"):
            return
        self.panel_repo.setText(f"{self.owner}/{self.repo}")
        self.panel_branch.setText(str(self.branch or "main"))

        if not self.current_game:
            for label in (self.panel_state, self.panel_path, self.panel_tag):
                label.setText("—")
            return

        data = (self.current_game.get("channels") or {}).get(self.current_channel) or {}
        record = self._record()
        if record and self._record_path_exists(record):
            self.panel_state.setText("Kurulu")
            self.panel_path.setText(str(record.get("install_path") or "—"))
        else:
            partial = self._valid_partial()
            self.panel_state.setText("Yarım indirme" if partial else "Kurulu değil")
            self.panel_path.setText(str((partial or {}).get("install_path") or "—"))
        self.panel_tag.setText(str(data.get("tag") or "—"))

    # -- artwork -------------------------------------------------------------

    def _on_cover_requested(self, key: str, url: str):
        cached = self._tile_cover_cache.get(url)
        if cached is not None:
            self._apply_cover(key, cached)
            return
        task = TileCoverTask(key, url)
        task.signals.done.connect(self._cover_loaded)
        self.pool.start(task)

    def _apply_cover(self, key: str, pixmap: QPixmap):
        for view in (self.library_grid, self.library_grid_bp):
            view.set_tile_cover(key, pixmap)

    def _cover_loaded(self, key: str, url: str, raw):
        if not raw:
            return
        pixmap = QPixmap()
        if not pixmap.loadFromData(raw):
            return
        self._tile_cover_cache[url] = pixmap
        self._apply_cover(key, pixmap)

    def _load_screenshot_gallery(self):
        if not hasattr(self, "screenshot_gallery"):
            return
        self._screenshot_token = uuid.uuid4().hex
        urls = []
        if self.current_game:
            urls = list((self.current_game.get("artwork") or {}).get("screenshots") or [])
        self.screenshot_gallery.set_urls(urls)

    def _on_screenshot_requested(self, index: int, url: str):
        cached = self._screenshot_pixmap_cache.get(url)
        if cached is not None:
            self.screenshot_gallery.set_thumb_pixmap(index, cached)
            return
        task = ScreenshotTask(self._screenshot_token, index, url)
        task.signals.done.connect(self._screenshot_loaded)
        self.pool.start(task)

    def _screenshot_loaded(self, token: str, index: int, url: str, raw):
        if not raw:
            return
        pixmap = QPixmap()
        if not pixmap.loadFromData(raw):
            return
        self._screenshot_pixmap_cache[url] = pixmap
        if token != self._screenshot_token:
            return
        self.screenshot_gallery.set_thumb_pixmap(index, pixmap)

    # -- download mirroring --------------------------------------------------

    def _active_key(self) -> str:
        return str((getattr(self, "_active_install_context", None) or {}).get("key") or "")

    def _set_tile_progress(self, key: str, percent: int | None):
        if not key or not hasattr(self, "library_grid"):
            return
        for view in (self.library_grid, self.library_grid_bp):
            view.set_tile_progress(key, percent)

    def install_progress(self, percent: int, text: str):
        super().install_progress(percent, text)
        percent = max(0, min(int(percent), 100))
        self._set_tile_progress(self._active_key(), percent)

        context = getattr(self, "_active_install_context", None) or {}
        title = str(context.get("title") or "İndiriliyor")
        channel = str(context.get("channel") or "—")
        sizes, speed, streams = split_progress_text(text)
        paused = self.download_control is not None and self.download_control.paused
        state_text = "Duraklatıldı" if paused else "İndiriliyor"

        speed_bytes = parse_speed_bytes(speed)
        if speed_bytes > self._dl_peak_bytes:
            self._dl_peak_bytes = speed_bytes
            self._dl_peak_text = speed

        # Status bar: icon, "İndiriliyor: <game>", long bar, percentage.
        self.status.setText(f"{state_text}: {title}")
        self.progress_text.setText(f"%{percent}")

        # Game page action bar.
        self.action_dl_caption.setText(state_text.upper())
        self.action_dl_value.setText(f"%{percent} Tamamlandı")
        self.action_dl_bar.setValue(percent)

        # Downloads page transfer panel.
        self.dlp_title.setText(title)
        self.dlp_detail.setText(text)
        self.dlp_bar.setValue(percent)
        self.dlp_percent.setText(f"%{percent}")
        self.dlp_bytes.setText(sizes or "—")
        self.dlp_net.setText(speed or "—")
        self.dlp_peak.setText(self._dl_peak_text or "—")
        self.dlp_streams.setText(streams or "—")
        self.dlp_eta.setText(f"Kalan tahmini süre: {self._eta_text(percent, paused)}")

        # Big Picture downloads tab.
        self.big_picture.dl_title.setText(title)
        self.big_picture.dl_meta.setText(text)
        self.big_picture.dl_progress.setValue(percent)
        self.big_picture.dl_metric_progress.setText(f"%{percent}")
        self.big_picture.dl_metric_state.setText(state_text)
        self.big_picture.dl_metric_channel.setText(channel.upper())
        self.big_picture.game_progress.setValue(percent)
        self.big_picture.game_status.setText(f"{state_text}  •  %{percent}  •  {sizes}")

    def _eta_text(self, percent: int, paused: bool) -> str:
        if paused:
            return "duraklatıldı"
        if self._dl_started_at is None or percent <= 0:
            return "hesaplanıyor…"
        elapsed = time.monotonic() - self._dl_started_at
        if elapsed <= 0:
            return "hesaplanıyor…"
        return format_eta(elapsed * (100 - percent) / percent)

    def _set_download_controls(self, active: bool):
        super()._set_download_controls(active)
        if not hasattr(self, "action_dl"):
            return
        self.action_dl.setVisible(active)
        self.dlp_pause.setVisible(active)
        self.status_icon.setVisible(active)
        self.progress.setVisible(active or self.progress.value() > 0)
        if active:
            self._dl_started_at = time.monotonic()
            self._dl_peak_bytes = 0.0
            self._dl_peak_text = ""
            context = getattr(self, "_active_install_context", None) or {}
            self.status_icon.set_icon(self._icon_pixmap_for(context.get("key")))
            self.dlp_hero.set_hero(self.hero.hero if not self.hero.hero.isNull() else None)
        else:
            self._dl_started_at = None

    def toggle_pause(self):
        super().toggle_pause()
        paused = self.download_control is not None and self.download_control.paused
        label = "DEVAM ET" if paused else "DURAKLAT"
        for button in (self.action_pause, self.dlp_pause):
            button.setText(label)

    def _icon_pixmap_for(self, key) -> QPixmap | None:
        """Prefer the dedicated icon artwork, fall back to the cover so the
        status bar still shows something for catalog entries published before
        icons existed."""
        if not key:
            return None
        for row in range(self.library.count()):
            payload = self.library.item(row).data(Qt.UserRole)
            if not payload:
                continue
            game, channel = payload
            if self._key(game, channel) != key:
                continue
            artwork = game.get("artwork") or {}
            for kind in ("icon", "cover"):
                url = str(artwork.get(kind) or "")
                cached = self._tile_cover_cache.get(url)
                if cached is not None:
                    return cached
                if url:
                    self._request_image(url)
            return None
        return None

    def _request_image(self, url: str):
        if url in self._requested_images:
            return
        self._requested_images.add(url)
        task = TileCoverTask("", url)
        task.signals.done.connect(self._loose_image_loaded)
        self.pool.start(task)

    def _loose_image_loaded(self, _key: str, url: str, raw):
        if not raw:
            return
        pixmap = QPixmap()
        if pixmap.loadFromData(raw):
            self._tile_cover_cache[url] = pixmap

    def _clear_active_download_ui(self, message: str):
        self.dlp_title.setText("Etkin indirme yok")
        self.dlp_bar.setValue(0)
        self.dlp_detail.setText(message)
        self.big_picture.dl_title.setText("Etkin indirme yok")
        self.big_picture.dl_meta.setText(message)
        self.big_picture.dl_progress.setValue(0)
        for metric in (
            self.big_picture.dl_metric_progress,
            self.big_picture.dl_metric_state,
            self.big_picture.dl_metric_channel,
        ):
            metric.setText("—")

    def _refresh_downloads_page(self):
        if not hasattr(self, "dlp_done_caption"):
            return

        for row in self._completed_rows:
            self.dlp_rows_layout.removeWidget(row)
            row.setParent(None)
            row.deleteLater()
        self._completed_rows.clear()

        records = [
            dict(record, key=key)
            for key, record in (self.install_registry.get("games") or {}).items()
            if self._record_path_exists(record)
        ]
        records.sort(key=lambda r: str(r.get("title") or "").lower())

        self.dlp_done_caption.setText(f"TAMAMLANDI ({len(records)})")
        self.dlp_done_empty.setVisible(not records)

        for record in records:
            row = CompletedRow(record)
            row.openRequested.connect(self._open_install_folder)
            row.removeRequested.connect(self._forget_install_record)
            row.icon.set_icon(self._icon_pixmap_for(record.get("key")))
            self.dlp_rows_layout.addWidget(row)
            self._completed_rows.append(row)

        self.big_picture.dl_installed.setText(
            "\n".join(f"{r.get('title', '?')}   v{r.get('version', '?')}" for r in records)
            or "Henüz kurulu oyun yok."
        )

    def _open_install_folder(self, key: str):
        record = (self.install_registry.get("games") or {}).get(key) or {}
        path = str(record.get("install_path") or "")
        if path and Path(path).is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        else:
            QMessageBox.warning(
                self,
                "Klasör bulunamadı",
                f"Kayıtlı kurulum klasörü artık mevcut değil:\n{path}",
            )

    def _forget_install_record(self, key: str):
        """Remove the row from the completed list only. Game files on disk are
        never touched here; deleting files stays behind the KALDIR flow with
        its typed confirmation."""
        record = (self.install_registry.get("games") or {}).get(key) or {}
        answer = QMessageBox.question(
            self,
            "Listeden kaldırılsın mı?",
            f"{record.get('title', 'Bu kayıt')} indirme listesinden çıkarılacak.\n\n"
            "Oyun dosyaları silinmez; yalnız Launcher kaydı temizlenir.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        (self.install_registry.get("games") or {}).pop(key, None)
        registry_base.save_registry(self.install_registry)
        self._refresh_downloads_page()
        self.render_library()
        self.update_install_state_ui()

    def install_done(self):
        key = self._active_key()
        super().install_done()
        self._set_tile_progress(key, None)
        self._clear_active_download_ui("Kurulum tamamlandı ve doğrulandı.")
        self._refresh_downloads_page()
        self._refresh_side_panels()

    def install_cancelled(self):
        key = self._active_key()
        super().install_cancelled()
        self._set_tile_progress(key, None)
        self._clear_active_download_ui("İndirme iptal edildi; tamamlanan parçalar korundu.")
        self._refresh_side_panels()

    def install_error(self, message: str):
        key = self._active_key()
        super().install_error(message)
        self._set_tile_progress(key, None)
        self._clear_active_download_ui("İndirme kesildi; DEVAM ET ile sürdürülebilir.")
        self._refresh_side_panels()

    def uninstall_done(self, removed_path: str):
        super().uninstall_done(removed_path)
        self._refresh_downloads_page()
        self._refresh_side_panels()

    # -- Big Picture ---------------------------------------------------------

    def _toggle_big_picture(self):
        if self._big_picture:
            self._exit_big_picture()
        else:
            self._enter_big_picture()

    def _enter_big_picture(self):
        if self._big_picture:
            return
        self._big_picture = True
        self._pre_big_picture_geometry = self.geometry()
        for widget in self._chrome_widgets:
            widget.hide()
        self.main_stack.setCurrentIndex(1)
        self.big_picture.search.setText(self.search.text())
        self.big_picture.show_grid()
        self.render_library()
        self._sync_big_picture_game()
        self.showFullScreen()
        self.library_grid_bp.focus_selection()

    def _exit_big_picture(self):
        if not self._big_picture:
            return
        self._big_picture = False
        for widget in self._chrome_widgets:
            widget.show()
        self.main_stack.setCurrentIndex(0)
        self.showNormal()
        if self._pre_big_picture_geometry is not None:
            self.setGeometry(self._pre_big_picture_geometry)
        self.library_grid.focus_selection()

    # -- gamepad -------------------------------------------------------------

    def _active_library_view(self):
        return self.library_grid_bp if self._big_picture else self.library_grid

    def _on_gamepad_action(self, action: str):
        if action == "toggle_big_picture":
            self._toggle_big_picture()
            return

        # ---- Big Picture game page: a self-contained controller surface ----
        if self._big_picture and self.big_picture.on_game_page:
            if action == "back":
                self.big_picture.show_grid()
                self.library_grid_bp.focus_selection()
            elif action == "activate":
                self.big_picture.activate_focused_action()
            elif action in ("left", "up"):
                self.big_picture.move_action_focus(-1)
            elif action in ("right", "down"):
                self.big_picture.move_action_focus(1)
            elif action == "switch_view":
                self.big_picture.show_grid()
                self.big_picture.cycle_tab(1)
            return

        if action == "switch_view":
            if self._big_picture:
                self.big_picture.cycle_tab(1)
            else:
                self._show_right_page(1 if self.right_stack.currentIndex() == 0 else 0)
            return

        view = self._active_library_view()

        if action == "back":
            focused = self.focusWidget()
            if focused in (self.install_button, self.verify_button, getattr(self, "uninstall_button", None)):
                view.focus_selection()
            elif self._big_picture:
                self._exit_big_picture()
            return

        target = self.focusWidget()
        if not isinstance(target, QPushButton):
            target = view

        if action == "activate":
            if self._big_picture:
                # Picking a capsule opens the couch game page rather than
                # only moving the desktop selection.
                QApplication.sendEvent(view, QKeyEvent(QEvent.KeyPress, Qt.Key_Return, Qt.NoModifier))
                if self.current_game:
                    self.big_picture.show_game_page()
                return
            if isinstance(target, QPushButton):
                if target.isEnabled():
                    target.click()
            else:
                QApplication.sendEvent(view, QKeyEvent(QEvent.KeyPress, Qt.Key_Return, Qt.NoModifier))
            return

        if action in _GAMEPAD_DIRECTION_KEYS:
            # Walking off the bottom of the library hands focus to the action
            # row, so a controller-only user can start an install.
            if target is view and action == "down" and view.is_selection_on_last_row() and not self._big_picture:
                self.install_button.setFocus()
                return
            QApplication.sendEvent(target, QKeyEvent(QEvent.KeyPress, _GAMEPAD_DIRECTION_KEYS[action], Qt.NoModifier))


def _splash_pixmap() -> QPixmap:
    pixmap = QPixmap(460, 260)
    pixmap.fill(QColor("#171a21"))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    glow = QLinearGradient(0, 0, 0, pixmap.height())
    glow.setColorAt(0.0, QColor(27, 40, 56, 255))
    glow.setColorAt(1.0, QColor(13, 19, 25, 255))
    painter.fillRect(pixmap.rect(), glow)
    painter.setPen(QColor("#66c0f4"))
    font = painter.font()
    font.setPointSize(28)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignCenter, "DROWNED")
    painter.setPen(QColor("#67707b"))
    small = painter.font()
    small.setPointSize(9)
    small.setBold(False)
    painter.setFont(small)
    painter.drawText(
        pixmap.rect().adjusted(0, 0, 0, -26), Qt.AlignBottom | Qt.AlignHCenter, "Kütüphane hazırlanıyor"
    )
    painter.end()
    return pixmap


def main():
    base.install_exception_hook()
    app = QApplication(sys.argv)
    app.setApplicationName("Drowned Launcher")
    app.setOrganizationName("Drowned")
    app.setStyle("Fusion")
    app.setStyleSheet(STEAM_STYLE)

    splash = QSplashScreen(_splash_pixmap())
    splash.show()
    app.processEvents()

    win = Launcher()
    win.show()
    splash.finish(win)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
