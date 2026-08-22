from __future__ import annotations

import math
import sys

from PySide6.QtCore import QEasingCurve, QPointF, QPropertyAnimation, QRect, Qt, QTimer, QVariantAnimation
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSplashScreen,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

import app_v14 as previous

APP_VERSION = "0.15.0"
BASE = previous.BASE


VIRTUAL_STYLE = r"""
* {
    font-family: "Segoe UI Variable", "Segoe UI", sans-serif;
    outline: 0;
}
QWidget { color:#f5f7f8; font-size:12px; }
QMainWindow, QWidget#virtualRoot { background:#17191a; }
QToolTip {
    background:#111415; color:#f7f8f8; border:1px solid rgba(255,255,255,45);
    padding:6px 9px; border-radius:6px;
}

/* application shell */
QFrame#virtualShell { background:#17191a; }
QFrame#leftRail, QFrame#socialRail {
    background:#101213;
    border:0;
}
QFrame#leftRail { border-right:1px solid rgba(255,255,255,18); }
QFrame#socialRail { border-left:1px solid rgba(255,255,255,18); }
QLabel#brandOrb {
    min-width:38px; max-width:38px; min-height:38px; max-height:38px;
    background:#f7f7f4; color:#111313; border-radius:19px;
    font-size:15px; font-weight:900;
}
QLabel#nav, QLabel#navActive {
    min-width:42px; max-width:42px; min-height:42px; max-height:42px;
    border-radius:21px; color:rgba(255,255,255,125); font-size:17px;
    qproperty-alignment: AlignCenter;
}
QLabel#nav:hover { background:rgba(255,255,255,15); color:#ffffff; }
QLabel#navActive {
    background:rgba(255,255,255,235); color:#111313;
    border:1px solid rgba(255,255,255,245);
}
QPushButton#railButton {
    min-width:38px; max-width:38px; min-height:38px; max-height:38px;
    padding:0; border-radius:19px; background:rgba(255,255,255,11);
    border:1px solid rgba(255,255,255,24); color:rgba(255,255,255,170);
    font-size:14px;
}
QPushButton#railButton:hover {
    background:rgba(255,255,255,25); border-color:rgba(255,255,255,58); color:#fff;
}
QLabel#connectionOnline {
    min-width:36px; max-width:36px; min-height:36px; max-height:36px;
    border-radius:18px; background:rgba(255,255,255,10);
    border:1px solid rgba(255,255,255,22); color:#62ded8;
    font-size:13px; font-weight:900; qproperty-alignment: AlignCenter;
}

/* right worlds rail */
QFrame#worldPanel {
    background:#101213;
    border-left:1px solid rgba(255,255,255,18);
}
QLabel#worldTitle { color:#ffffff; font-size:14px; font-weight:850; }
QLabel#worldCount { color:rgba(255,255,255,88); font-size:9px; font-weight:750; }
QLabel#sectionLabel {
    color:rgba(255,255,255,82); font-size:9px; font-weight:850; letter-spacing:2px;
}
QLineEdit, QComboBox {
    min-height:20px; background:rgba(255,255,255,8);
    border:1px solid rgba(255,255,255,22); border-radius:10px;
    color:#f6f7f7; padding:7px 10px; selection-background-color:#296f73;
}
QLineEdit:hover, QComboBox:hover { border-color:rgba(255,255,255,46); }
QLineEdit:focus, QComboBox:focus { border-color:#5fded8; background:rgba(255,255,255,12); }
QComboBox QAbstractItemView {
    background:#171a1b; color:#fff; border:1px solid rgba(255,255,255,30);
    selection-background-color:#2b4647;
}
QListWidget { background:transparent; border:0; }
QScrollArea { background:transparent; border:0; }
QScrollArea > QWidget > QWidget { background:transparent; }
QWidget#gameListContent { background:transparent; }

/* hero / glass surfaces */
QFrame#heroActionBar, QFrame#glassCard, QFrame#panel, QFrame#nextCard {
    background:rgba(10,12,13,205);
    border:1px solid rgba(255,255,255,27);
    border-radius:12px;
}
QFrame#heroActionBar { border-radius:16px; }
QFrame#infoCard { background:transparent; border:0; }
QFrame#detailSurface { background:#17191a; }
QFrame#hairline { background:rgba(255,255,255,20); }
QLabel#heroEyebrow {
    color:rgba(255,255,255,165); font-size:9px; font-weight:900; letter-spacing:2px;
    border:1px solid rgba(255,255,255,70); border-radius:9px; padding:3px 8px;
}
QLabel#gameTitle { color:#ffffff; font-size:29px; font-weight:900; }
QLabel#metaLine { color:#73ddd9; font-size:10px; font-weight:850; }
QLabel#description { color:rgba(255,255,255,190); font-size:12px; }
QLabel#panelTitle { color:rgba(255,255,255,92); font-size:9px; font-weight:900; letter-spacing:2px; }
QLabel#statName { color:rgba(255,255,255,82); font-size:8px; font-weight:900; letter-spacing:1px; }
QLabel#statValue { color:#ffffff; font-size:11px; font-weight:800; }
QLabel#rowKey { color:rgba(255,255,255,88); font-size:10px; }
QLabel#rowValue { color:rgba(255,255,255,210); font-size:10px; font-weight:700; }
QLabel#muted { color:rgba(255,255,255,95); font-size:10px; }
QLabel#downloadTitle { color:#ffffff; font-size:11px; font-weight:800; }
QLabel#downloadDot { color:#61ddd8; font-size:13px; }
QLabel#progressText { color:#67dfda; font-size:10px; font-weight:850; }
QLabel#statePill {
    color:#d8fbf9; background:rgba(47,116,116,110); border:1px solid rgba(95,222,216,100);
    border-radius:10px; padding:4px 8px; font-size:9px; font-weight:850;
}
QFrame#topPill {
    background:rgba(8,10,11,205); border:1px solid rgba(255,255,255,26); border-radius:17px;
}
QLabel#topPillText { color:rgba(255,255,255,180); font-size:9px; font-weight:850; letter-spacing:1px; }
QLabel#accentDot { color:#62ded8; font-size:12px; }

/* tabs */
QLabel#tab, QLabel#tabActive {
    color:rgba(255,255,255,92); font-size:9px; font-weight:900; letter-spacing:1px;
    padding:9px 12px; border-bottom:2px solid transparent;
}
QLabel#tab:hover { color:#fff; }
QLabel#tabActive { color:#fff; border-bottom-color:#62ded8; }

/* buttons */
QPushButton {
    min-height:24px; padding:8px 14px; border-radius:16px;
    background:rgba(255,255,255,12); border:1px solid rgba(255,255,255,30);
    color:rgba(255,255,255,205); font-weight:800;
}
QPushButton:hover { background:rgba(255,255,255,24); border-color:rgba(255,255,255,58); color:#fff; }
QPushButton:pressed { background:rgba(255,255,255,9); }
QPushButton:disabled { background:rgba(255,255,255,6); border-color:rgba(255,255,255,13); color:rgba(255,255,255,55); }
QPushButton#install {
    min-width:142px; min-height:34px; padding:7px 24px; border-radius:18px;
    background:#f6f6f2; color:#111313; border:1px solid #ffffff;
    font-size:11px; font-weight:950;
}
QPushButton#install:hover { background:#ffffff; color:#000000; }
QPushButton#secondary {
    background:transparent; border:1px solid rgba(255,255,255,36); color:rgba(255,255,255,205);
}
QPushButton#pauseButton { background:rgba(43,112,115,170); border-color:rgba(98,222,216,105); color:#f5ffff; }
QPushButton#danger { background:rgba(117,42,55,105); border-color:rgba(210,86,106,85); color:#ffdbe1; }
QPushButton#linkButton { background:transparent; border:0; color:#6bdfda; padding:4px 6px; }

/* optional content */
QCheckBox { spacing:8px; color:rgba(255,255,255,210); font-weight:700; padding:3px; }
QCheckBox::indicator {
    width:16px; height:16px; border-radius:5px; background:rgba(255,255,255,8);
    border:1px solid rgba(255,255,255,45);
}
QCheckBox::indicator:checked { background:#4ebbb7; border-color:#7ce5df; }

/* transfer rail */
QFrame#statusRail {
    background:#101213; border-top:1px solid rgba(255,255,255,18);
}
QProgressBar {
    min-height:5px; max-height:5px; background:rgba(255,255,255,12); border:0; border-radius:2px; color:transparent;
}
QProgressBar::chunk {
    border-radius:2px; background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #3a8f8c,stop:1 #68e3dd);
}
QProgressBar#fatBar { min-height:9px; max-height:9px; }
QPlainTextEdit {
    background:#0c0e0f; border:1px solid rgba(255,255,255,20); border-radius:8px;
    color:rgba(255,255,255,125); padding:7px;
}

QScrollBar:vertical { background:transparent; width:7px; margin:2px; }
QScrollBar::handle:vertical { background:rgba(255,255,255,32); min-height:28px; border-radius:3px; }
QScrollBar::handle:vertical:hover { background:rgba(255,255,255,55); }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background:transparent; }

/* existing Big Picture keeps its behaviour, receives the same palette */
QWidget#bigPictureRoot { background:#17191a; }
QFrame#bpHeader, QFrame#bpFooter { background:#101213; border-color:rgba(255,255,255,20); }
QLineEdit#bpSearch { background:rgba(255,255,255,10); border:1px solid rgba(255,255,255,28); border-radius:17px; padding:9px 16px; }
QLabel#bpTab, QLabel#bpTabActive { color:rgba(255,255,255,120); padding:9px 20px; font-weight:800; }
QLabel#bpTabActive { color:#fff; background:rgba(255,255,255,14); border:1px solid rgba(255,255,255,35); border-radius:17px; }
QLabel#bpSteamPill, QLabel#bpGlyph { color:#111313; background:#f5f5f1; }
"""


class VirtualWorldRow(BASE.GameListView.ITEM_CLASS):
    """Dribbble-style compact world card while preserving GameListView's API."""

    BASE_H = 58

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        rect = self.rect().adjusted(3, 3, -3, -3)

        if self._selected:
            bg = QColor(47, 62, 63, 225)
            border = QColor(255, 255, 255, 45)
        elif self._hover > 0.0:
            bg = QColor(255, 255, 255, int(11 + 9 * self._hover))
            border = QColor(255, 255, 255, int(22 + 20 * self._hover))
        else:
            bg = QColor(255, 255, 255, 7)
            border = QColor(255, 255, 255, 17)

        painter.setPen(QPen(border, 1))
        painter.setBrush(bg)
        painter.drawRoundedRect(rect, 9, 9)

        icon = max(34, int(40 * self._scale))
        icon_rect = QRect(rect.x() + 6, rect.y() + (rect.height() - icon) // 2, icon, icon)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(24, 27, 28))
        painter.drawRoundedRect(icon_rect, 7, 7)
        if not self._loading and not self._cover.isNull():
            scaled = self._cover.scaled(icon_rect.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            sx = max((scaled.width() - icon_rect.width()) // 2, 0)
            sy = max((scaled.height() - icon_rect.height()) // 2, 0)
            painter.save()
            painter.setClipRect(icon_rect)
            painter.setOpacity(self._reveal)
            painter.drawPixmap(icon_rect, scaled, QRect(sx, sy, icon_rect.width(), icon_rect.height()))
            painter.restore()

        tx = icon_rect.right() + 10
        title_rect = QRect(tx, rect.y() + 22, max(0, rect.right() - tx - 8), 20)
        tag_rect = QRect(tx, rect.y() + 6, max(0, rect.right() - tx - 8), 14)

        painter.setPen(QColor(255, 255, 255, 105))
        tag_font = painter.font(); tag_font.setPointSize(7); tag_font.setBold(True); painter.setFont(tag_font)
        channel = str(self._channel or "stable").upper()
        painter.drawText(tag_rect, Qt.AlignLeft | Qt.AlignVCenter, channel)

        painter.setPen(QColor("#ffffff") if self._selected else QColor(235, 238, 238))
        font = painter.font(); font.setPointSize(max(8, int(8.5 * self._scale))); font.setBold(True); painter.setFont(font)
        metrics = painter.fontMetrics()
        title = metrics.elidedText(str(self._game.get("title") or ""), Qt.ElideRight, max(0, title_rect.width()))
        painter.drawText(title_rect, Qt.AlignLeft | Qt.AlignVCenter, title)

        if self._progress is not None:
            bar = QRect(rect.x() + 7, rect.bottom() - 3, rect.width() - 14, 2)
            painter.fillRect(bar, QColor(255, 255, 255, 18))
            fill = int(bar.width() * max(0, min(100, self._progress)) / 100.0)
            painter.fillRect(QRect(bar.x(), bar.y(), fill, bar.height()), QColor("#62ded8"))
        painter.end()


class VirtualWorldList(BASE.GameListView):
    ITEM_CLASS = VirtualWorldRow


class VirtualHero(previous.CinematicHero):
    """Full-bleed artwork surface with neutral cinematic vignette."""

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(620)
        self.setMaximumHeight(16777215)

    def paintEvent(self, event):
        QFrame.paintEvent(self, event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        rect = self.rect()

        if not self.hero.isNull() and rect.width() > 0 and rect.height() > 0:
            phase = math.sin(self._camera * math.tau)
            zoom = 1.055 + 0.012 * math.cos(self._camera * math.tau)
            target_w = max(int(rect.width() * zoom), rect.width())
            target_h = max(int(rect.height() * zoom), rect.height())
            scaled = self.hero.scaled(target_w, target_h, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            overflow_x = max(scaled.width() - rect.width(), 0)
            overflow_y = max(scaled.height() - rect.height(), 0)
            sx = int(overflow_x * (0.50 + 0.10 * phase))
            sy = int(overflow_y * 0.45)
            source = scaled.rect().adjusted(sx, sy, -(overflow_x - sx), -(overflow_y - sy))
            painter.drawPixmap(rect, scaled, source)
        else:
            bg = QLinearGradient(0, 0, rect.width(), rect.height())
            bg.setColorAt(0, QColor("#232729")); bg.setColorAt(1, QColor("#111314"))
            painter.fillRect(rect, bg)

        side = QLinearGradient(0, 0, max(rect.width() * 0.78, 1), 0)
        side.setColorAt(0.0, QColor(7, 9, 10, 235))
        side.setColorAt(0.42, QColor(7, 9, 10, 135))
        side.setColorAt(1.0, QColor(7, 9, 10, 8))
        painter.fillRect(rect, side)

        bottom = QLinearGradient(0, rect.height() * 0.38, 0, rect.height())
        bottom.setColorAt(0.0, QColor(15, 17, 18, 0))
        bottom.setColorAt(1.0, QColor(15, 17, 18, 238))
        painter.fillRect(rect, bottom)

        glow = QRadialGradient(QPointF(rect.width() * 0.78, rect.height() * 0.20), max(rect.width(), rect.height()) * 0.50)
        glow.setColorAt(0.0, QColor(94, 222, 216, 16))
        glow.setColorAt(1.0, QColor(94, 222, 216, 0))
        painter.fillRect(rect, QBrush(glow))

        if not self.logo.isNull():
            target = self.logo.scaled(440, 165, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            painter.drawPixmap(34, max(rect.height() - target.height() - 190, 88), target)
        else:
            painter.setPen(QColor("#ffffff"))
            font = painter.font(); font.setPointSize(26); font.setBold(True); painter.setFont(font)
            painter.drawText(36, max(rect.height() - 235, 90), self.fallback_title)

        if getattr(self, "_reveal", 1.0) < 1.0:
            painter.fillRect(rect, QColor(7, 9, 10, int((1.0 - self._reveal) * 180)))
        painter.end()


class Launcher(previous.Launcher):
    """Virtual Worlds-inspired presentation over the unchanged launcher backend."""

    def __init__(self):
        super().__init__()
        QApplication.instance().setStyleSheet(VIRTUAL_STYLE)
        self.setWindowTitle(f"Drowned Launcher {APP_VERSION} • Virtual Worlds UI")
        self.resize(max(self.width(), 1480), max(self.height(), 900))

    def _build_ui(self):
        QApplication.instance().setStyleSheet(VIRTUAL_STYLE)
        root = QWidget()
        root.setObjectName("virtualRoot")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self._chrome_widgets = []

        self.main_stack = previous.FadeStack()
        self.main_stack.addWidget(self._build_desktop_shell())
        self.library_grid_bp = BASE.GameGridView()
        self.big_picture = BASE.BigPictureView(self.library_grid_bp)
        self.main_stack.addWidget(self.big_picture)
        outer.addWidget(self.main_stack, 1)

        status_shell = QFrame()
        status_shell.setObjectName("statusRail")
        status_shell.setMinimumHeight(48)
        status_shell.setMaximumHeight(138)
        s_outer = QVBoxLayout(status_shell)
        s_outer.setContentsMargins(18, 7, 18, 7)
        s_outer.setSpacing(4)
        self.download_card = QFrame()
        dl = QVBoxLayout(self.download_card)
        dl.setContentsMargins(0, 0, 0, 0)
        dl.setSpacing(4)
        row = QHBoxLayout(); row.setSpacing(9)
        self.download_dot = QLabel("●"); self.download_dot.setObjectName("downloadDot")
        self.status_icon = BASE.IconLabel(25, 25); self.status_icon.hide()
        self.status = QLabel("Hazır"); self.status.setObjectName("downloadTitle")
        self.progress = QProgressBar(); self.progress.setRange(0, 100); self.progress.setValue(0); self.progress.setTextVisible(False); self.progress.setMinimumWidth(260)
        self.progress_text = QLabel(""); self.progress_text.setObjectName("progressText")
        row.addWidget(self.download_dot); row.addWidget(self.status_icon); row.addWidget(self.status)
        row.addSpacing(6); row.addWidget(self.progress, 1); row.addWidget(self.progress_text)
        self._status_row = row
        self.logs = QPlainTextEdit(); self.logs.setReadOnly(True); self.logs.setFixedHeight(68); self.logs.hide()
        dl.addLayout(row); dl.addWidget(self.logs); s_outer.addWidget(self.download_card)
        outer.addWidget(status_shell)
        self._chrome_widgets.append(status_shell)

        self._wire_runtime()

    def _build_desktop_shell(self):
        shell = QFrame(); shell.setObjectName("virtualShell")
        layout = QHBoxLayout(shell); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(0)

        layout.addWidget(self._build_left_rail())

        self.right_stack = previous.FadeStack()
        self.right_stack.addWidget(self._build_game_page())
        self.right_stack.addWidget(previous.Launcher._build_downloads_page(self))
        layout.addWidget(self.right_stack, 1)

        layout.addWidget(self._build_sidebar())
        layout.addWidget(self._build_social_rail())
        self.main_splitter = shell
        return shell

    def _build_left_rail(self):
        rail = QFrame(); rail.setObjectName("leftRail"); rail.setFixedWidth(72)
        lay = QVBoxLayout(rail); lay.setContentsMargins(15, 16, 15, 16); lay.setSpacing(12)
        brand = QLabel("D"); brand.setObjectName("brandOrb"); brand.setAlignment(Qt.AlignCenter); brand.setToolTip("Drowned Launcher")
        lay.addWidget(brand, 0, Qt.AlignHCenter); lay.addSpacing(18)

        self.nav_library = BASE.ClickableLabel("⌂"); self.nav_library.setObjectName("navActive"); self.nav_library.setAlignment(Qt.AlignCenter); self.nav_library.setToolTip("Kütüphane")
        self.nav_downloads = BASE.ClickableLabel("⇩"); self.nav_downloads.setObjectName("nav"); self.nav_downloads.setAlignment(Qt.AlignCenter); self.nav_downloads.setToolTip("İndirmeler")
        self.nav_library.clicked.connect(lambda: self._show_right_page(0))
        self.nav_downloads.clicked.connect(lambda: self._show_right_page(1))
        lay.addWidget(self.nav_library, 0, Qt.AlignHCenter); lay.addWidget(self.nav_downloads, 0, Qt.AlignHCenter)
        lay.addStretch()
        return rail

    def _build_social_rail(self):
        rail = QFrame(); rail.setObjectName("socialRail"); rail.setFixedWidth(62)
        lay = QVBoxLayout(rail); lay.setContentsMargins(12, 16, 12, 16); lay.setSpacing(11)

        self.connection = QLabel("●"); self.connection.setObjectName("connectionOnline"); self.connection.setAlignment(Qt.AlignCenter); self.connection.setToolTip("GitHub RAW bağlantısı")
        lay.addWidget(self.connection, 0, Qt.AlignHCenter)
        lay.addSpacing(8)

        self.big_picture_button = QPushButton("⛶"); self.big_picture_button.setObjectName("railButton"); self.big_picture_button.setToolTip("Big Picture (F11)")
        refresh = QPushButton("↻"); refresh.setObjectName("railButton"); refresh.setToolTip("Kataloğu yenile"); refresh.clicked.connect(self.load_catalog)
        settings = QPushButton("⚙"); settings.setObjectName("railButton"); settings.setToolTip("Ayarlar"); settings.clicked.connect(self.open_settings)
        lay.addWidget(self.big_picture_button, 0, Qt.AlignHCenter)
        lay.addWidget(refresh, 0, Qt.AlignHCenter)
        lay.addStretch()
        lay.addWidget(settings, 0, Qt.AlignHCenter)
        return rail

    def _build_sidebar(self):
        panel = QFrame(); panel.setObjectName("worldPanel"); panel.setFixedWidth(318)
        side = QVBoxLayout(panel); side.setContentsMargins(13, 16, 13, 14); side.setSpacing(9)

        head = QHBoxLayout()
        title = QLabel("WORLDS"); title.setObjectName("worldTitle")
        self.game_count = QLabel("0 oyun"); self.game_count.setObjectName("worldCount")
        head.addWidget(title); head.addStretch(); head.addWidget(self.game_count)
        side.addLayout(head)

        self.search = QLineEdit(); self.search.setPlaceholderText("Oyunlarda ara…"); self.search.setClearButtonEnabled(True)
        self._search_debounce = QTimer(self); self._search_debounce.setSingleShot(True); self._search_debounce.setInterval(150)
        self._search_debounce.timeout.connect(self.render_library)
        self.search.textChanged.connect(lambda _text: self._search_debounce.start())
        side.addWidget(self.search)

        filters = QHBoxLayout(); filters.setSpacing(6)
        self.platform = QComboBox(); self.platform.addItem("Tümü")
        self.channel = QComboBox(); self.channel.addItems(["stable", "beta", "dev", "nightly", "archive"])
        self.platform.currentTextChanged.connect(self.render_library); self.channel.currentTextChanged.connect(self.render_library)
        filters.addWidget(self.platform, 1); filters.addWidget(self.channel, 1); side.addLayout(filters)

        label = QLabel("DISCOVER"); label.setObjectName("sectionLabel"); side.addWidget(label)
        self.library = QListWidget(); self.library.currentItemChanged.connect(self.library_selection_changed); self.library.hide(); side.addWidget(self.library)
        self.library_grid = VirtualWorldList(); self.library_grid.setObjectName("virtualWorldList"); side.addWidget(self.library_grid, 1)
        return panel

    def _build_game_page(self):
        scroller = QScrollArea(); scroller.setWidgetResizable(True); scroller.setFrameShape(QFrame.NoFrame)
        surface = QFrame(); surface.setObjectName("detailSurface"); self.game_surface = surface
        page = QVBoxLayout(surface); page.setContentsMargins(0, 0, 0, 24); page.setSpacing(0)

        self.hero = VirtualHero()
        hero_l = QVBoxLayout(self.hero); hero_l.setContentsMargins(30, 22, 30, 28); hero_l.setSpacing(10)

        top = QHBoxLayout(); top.addStretch()
        pill = QFrame(); pill.setObjectName("topPill"); pl = QHBoxLayout(pill); pl.setContentsMargins(12, 4, 12, 4); pl.setSpacing(8)
        dot = QLabel("●"); dot.setObjectName("accentDot"); txt = QLabel("DROWNED  •  LIBRARY"); txt.setObjectName("topPillText")
        pl.addWidget(dot); pl.addWidget(txt); top.addWidget(pill); top.addStretch(); hero_l.addLayout(top)
        hero_l.addStretch()

        self.title = QLabel("Kütüphane yükleniyor…"); self.title.setObjectName("gameTitle"); self.title.hide()
        self.meta = QLabel(""); self.meta.setObjectName("metaLine"); self.meta.setMaximumWidth(500)
        self.description = QLabel("Raw GitHub kataloğundan oyunlar yükleniyor."); self.description.setObjectName("description"); self.description.setWordWrap(True); self.description.setMaximumWidth(500)
        hero_l.addWidget(self.meta, 0, Qt.AlignLeft); hero_l.addWidget(self.description, 0, Qt.AlignLeft)

        action_bar = QFrame(self.hero); action_bar.setObjectName("heroActionBar")
        action = QHBoxLayout(action_bar); action.setContentsMargins(12, 11, 14, 11); action.setSpacing(10)
        self.info_card = QFrame(action_bar); self.info_card.setObjectName("infoCard")
        info = QHBoxLayout(self.info_card); info.setContentsMargins(0, 0, 0, 0); info.setSpacing(8)
        self.install_button = previous.GlowButton("YÜKLE"); self.install_button.setObjectName("install"); self.install_button.clicked.connect(self.install_current_game); self.install_button.setEnabled(False)
        self.verify_button = QPushButton("DOSYALARI DOĞRULA"); self.verify_button.setObjectName("secondary"); self.verify_button.setEnabled(False)
        info.addWidget(self.install_button); info.addWidget(self.verify_button); action.addWidget(self.info_card)

        self.action_dl = QWidget(); dl_l = QHBoxLayout(self.action_dl); dl_l.setContentsMargins(0, 0, 0, 0); dl_l.setSpacing(8)
        self.action_pause = QPushButton("DURAKLAT"); self.action_pause.setObjectName("pauseButton"); self.action_pause.clicked.connect(self.toggle_pause); dl_l.addWidget(self.action_pause)
        dl_text = QVBoxLayout(); dl_text.setSpacing(1)
        self.action_dl_caption = QLabel("İNDİRİLİYOR"); self.action_dl_caption.setObjectName("statName")
        self.action_dl_value = QLabel("%0 Tamamlandı"); self.action_dl_value.setObjectName("rowValue")
        self.action_dl_bar = QProgressBar(); self.action_dl_bar.setRange(0, 100); self.action_dl_bar.setValue(0); self.action_dl_bar.setTextVisible(False); self.action_dl_bar.setFixedWidth(130)
        dl_text.addWidget(self.action_dl_caption); dl_text.addWidget(self.action_dl_value); dl_text.addWidget(self.action_dl_bar); dl_l.addLayout(dl_text)
        self.action_dl.hide(); action.addWidget(self.action_dl); action.addStretch()

        stats = QHBoxLayout(); stats.setSpacing(16)
        for caption, attr in (("PLATFORM", "stat_platform"), ("KANAL", "stat_channel"), ("SÜRÜM", "stat_version"), ("BOYUT", "stat_size")):
            box = QWidget(); b = QVBoxLayout(box); b.setContentsMargins(0, 0, 0, 0); b.setSpacing(1)
            c = QLabel(caption); c.setObjectName("statName"); v = QLabel("—"); v.setObjectName("statValue")
            b.addWidget(c); b.addWidget(v); setattr(self, attr, v); stats.addWidget(box)
        action.addLayout(stats)
        self.state_badge = QLabel("HAZIR"); self.state_badge.setObjectName("statePill"); action.addWidget(self.state_badge, 0, Qt.AlignVCenter)
        hero_l.addWidget(action_bar)
        page.addWidget(self.hero)

        content = QFrame(); content.setObjectName("detailSurface"); self.game_content = content
        c = QVBoxLayout(content); c.setContentsMargins(28, 20, 28, 6); c.setSpacing(0)
        tabs = QHBoxLayout(); tabs.setSpacing(2)
        self.tab_overview = BASE.ClickableLabel("GENEL BAKIŞ"); self.tab_overview.setObjectName("tabActive")
        self.tab_shots = BASE.ClickableLabel("EKRAN GÖRÜNTÜLERİ"); self.tab_shots.setObjectName("tab")
        self.tab_overview.clicked.connect(lambda: self._show_detail_tab(0)); self.tab_shots.clicked.connect(lambda: self._show_detail_tab(1))
        tabs.addWidget(self.tab_overview); tabs.addWidget(self.tab_shots); tabs.addStretch(); c.addLayout(tabs)
        line = QFrame(); line.setObjectName("hairline"); line.setFixedHeight(1); c.addWidget(line); c.addSpacing(14)

        columns = QHBoxLayout(); columns.setSpacing(14); self.detail_stack = previous.FadeStack()
        overview = QFrame(); overview.setObjectName("glassCard"); ov = QVBoxLayout(overview); ov.setContentsMargins(16, 14, 16, 16)
        cap = QLabel("OYUN HAKKINDA"); cap.setObjectName("panelTitle"); self._detail_description = QLabel("Seçili oyunun ayrıntıları yukarıdaki hero alanında gösterilir."); self._detail_description.setObjectName("muted"); self._detail_description.setWordWrap(True)
        ov.addWidget(cap); ov.addSpacing(7); ov.addWidget(self._detail_description); ov.addStretch(); self.detail_stack.addWidget(overview)
        shots = QFrame(); shots.setObjectName("glassCard"); sh = QVBoxLayout(shots); sh.setContentsMargins(12, 12, 12, 12); self.screenshot_gallery = BASE.ScreenshotGallery(); sh.addWidget(self.screenshot_gallery); self.detail_stack.addWidget(shots)
        columns.addWidget(self.detail_stack, 1); columns.addWidget(previous.Launcher._build_side_panels(self), 0); c.addLayout(columns, 1)
        page.addWidget(content)

        self.cover = BASE.previous.CoverLabel(); self.cover.setParent(surface); self.cover.hide()
        scroller.setWidget(surface)
        return scroller


def main():
    BASE.base.install_exception_hook()
    app = QApplication(sys.argv)
    app.setApplicationName("Drowned Launcher")
    app.setOrganizationName("Drowned")
    app.setStyle("Fusion")
    app.setStyleSheet(VIRTUAL_STYLE)
    splash = QSplashScreen(BASE._splash_pixmap())
    splash.show(); app.processEvents()
    win = Launcher(); win.show(); splash.finish(win)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
