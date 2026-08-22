from __future__ import annotations

import math
import sys

from PySide6.QtCore import QEasingCurve, QEvent, QObject, QPointF, QPropertyAnimation, Qt, QTimer, QVariantAnimation
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPixmap, QRadialGradient
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
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

import app_v12 as previous

APP_VERSION = "0.14.0"
BASE = previous.previous.previous  # app_v10: UI contracts/helpers only


NEXT_STYLE = r"""
* {
    font-family: "Segoe UI Variable", "Segoe UI", sans-serif;
    outline: 0;
}
QWidget { color: #d7e4ef; font-size: 13px; }
QMainWindow, QWidget#nextRoot { background: #08111a; }
QToolTip { background:#172838; color:#edf8ff; border:1px solid #35556f; padding:6px 9px; }

/* top shell */
QFrame#nextTop {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #09131d,stop:.48 #102131,stop:1 #09131c);
    border-bottom: 1px solid #21384d;
}
QLabel#brandCube {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #79d5ff,stop:1 #278cc5);
    color:#06111a; border-radius:8px; font-size:17px; font-weight:900;
}
QLabel#brandTitle { color:#f4fbff; font-size:17px; font-weight:850; }
QLabel#brandSub { color:#5f7d94; font-size:9px; font-weight:800; letter-spacing:2px; }
QLabel#nav, QLabel#navActive {
    padding:18px 16px 14px 16px; font-size:13px; font-weight:800;
    border-bottom:3px solid transparent; color:#71899c;
}
QLabel#nav:hover { color:#e9f7ff; background:rgba(65,133,177,18); }
QLabel#navActive { color:#ffffff; border-bottom-color:#67c6f6; background:rgba(74,164,219,15); }
QLabel#connectionOnline {
    color:#b9ef79; background:#13271b; border:1px solid #315b35;
    border-radius:11px; padding:5px 9px; font-size:10px; font-weight:800;
}

/* icon/top buttons */
QPushButton#iconButton {
    min-width:34px; max-width:34px; min-height:34px; max-height:34px;
    padding:0; border-radius:9px; font-size:14px;
    background:#132435; border:1px solid #29465e; color:#b9cddd;
}
QPushButton#iconButton:hover { background:#1d3950; border-color:#4c84a8; color:#ffffff; }
QPushButton#iconButton:pressed { background:#0d1b27; }

/* library rail */
QFrame#nextSidebar {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #09131d,stop:1 #0c1a27);
    border-right:1px solid #1d3448;
}
QLabel#libraryTitle { color:#f1f7fb; font-size:15px; font-weight:850; }
QLabel#libraryCount { color:#6e8aa0; font-size:10px; font-weight:700; }
QLabel#sectionLabel { color:#607f96; font-size:9px; font-weight:850; letter-spacing:2px; }
QLineEdit, QComboBox {
    min-height:22px; background:#071019; border:1px solid #223d52; border-radius:8px;
    color:#d7e5ef; padding:7px 10px; selection-background-color:#2d7097;
}
QLineEdit:hover, QComboBox:hover { border-color:#355d78; }
QLineEdit:focus, QComboBox:focus { border-color:#67c6f6; background:#091622; }
QComboBox QAbstractItemView { background:#0d1b27; border:1px solid #31526b; selection-background-color:#274a63; }
QListWidget { background:transparent; border:0; }

/* detail surface */
QFrame#nextDetail { background:#0a1520; }
QScrollArea { background:#0a1520; border:0; }
QScrollArea > QWidget > QWidget { background:#0a1520; }
QFrame#nextActionDeck {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #0c1a27,stop:.55 #12283a,stop:1 #0b1925);
    border-top:1px solid #28475f; border-bottom:1px solid #152a3b;
}
QFrame#infoCard { background:transparent; border:0; }
QFrame#nextContent { background:#0a1520; }
QFrame#nextCard {
    background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #102131,stop:1 #0d1b28);
    border:1px solid #203b50; border-radius:12px;
}
QFrame#nextCard:hover { border-color:#315f7c; }
QFrame#panel {
    background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #112536,stop:1 #0d1c29);
    border:1px solid #28465e; border-radius:10px;
}
QFrame#hairline { background:#203a50; }

QLabel#gameTitle { color:#ffffff; font-size:30px; font-weight:900; }
QLabel#metaLine { color:#6ecbfa; font-size:11px; font-weight:800; }
QLabel#description { color:#aebfcb; font-size:13px; line-height:1.4; }
QLabel#panelTitle { color:#6f91a8; font-size:9px; font-weight:900; letter-spacing:2px; }
QLabel#statName { color:#5d7d94; font-size:9px; font-weight:850; letter-spacing:1px; }
QLabel#statValue { color:#f0f7fb; font-size:13px; font-weight:850; }
QLabel#rowKey { color:#69869b; font-size:11px; }
QLabel#rowValue { color:#dbe8f1; font-size:11px; font-weight:700; }
QLabel#muted { color:#6d879a; font-size:11px; }
QLabel#downloadTitle { color:#e8f4fb; font-size:12px; font-weight:800; }
QLabel#downloadDot { color:#67c6f6; font-size:14px; }
QLabel#progressText { color:#7ad2ff; font-size:11px; font-weight:850; }

/* detail tabs */
QLabel#tab, QLabel#tabActive {
    color:#718ca0; font-size:10px; font-weight:900; letter-spacing:1px;
    padding:10px 14px; border-bottom:3px solid transparent;
}
QLabel#tab:hover { color:#e9f7ff; background:rgba(62,133,179,12); }
QLabel#tabActive { color:#ffffff; border-bottom-color:#67c6f6; background:rgba(64,151,205,12); }

/* action buttons - intentionally high contrast and always visible */
QPushButton {
    min-height:25px; padding:8px 16px; border-radius:8px;
    background:#183149; border:1px solid #315a77; color:#d9e8f2; font-weight:800;
}
QPushButton:hover { background:#245274; border-color:#69b7e5; color:#ffffff; }
QPushButton:pressed { background:#11283b; }
QPushButton:disabled { background:#111c25; border-color:#22313d; color:#4f6271; }
QPushButton#install {
    min-width:150px; min-height:38px; padding:9px 26px; border-radius:9px;
    background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #5b9b1b,stop:.52 #76b72a,stop:1 #4f8617);
    border:1px solid #95cf46; color:#f6ffe9; font-size:14px; font-weight:900;
}
QPushButton#install:hover {
    background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #70b626,stop:.52 #8dce3d,stop:1 #62a41d);
    border-color:#b2ea61;
}
QPushButton#secondary { background:#183149; border-color:#315a77; color:#d9e8f2; }
QPushButton#pauseButton { background:#163d5b; border-color:#3e83aa; color:#e2f5ff; }
QPushButton#danger { background:#3a1d28; border-color:#6e3548; color:#efbbc8; }
QPushButton#danger:hover { background:#5a2636; border-color:#a64d68; color:#ffe5eb; }
QPushButton#linkButton { background:transparent; border:0; color:#73cdfa; padding:5px 7px; }
QPushButton#linkButton:hover { color:#ffffff; background:rgba(102,198,246,12); }

/* optional packages */
QCheckBox { spacing:10px; color:#d8e5ed; font-weight:750; padding:4px; }
QCheckBox::indicator { width:18px; height:18px; border-radius:5px; background:#07131d; border:1px solid #3b627e; }
QCheckBox::indicator:hover { border-color:#71cfff; background:#0d2536; }
QCheckBox::indicator:checked { background:#3d9dcc; border-color:#8cdbff; }
QCheckBox:disabled { color:#526879; }

/* progress / logs */
QProgressBar { min-height:7px; max-height:7px; background:#061019; border:1px solid #172b3b; border-radius:3px; color:transparent; }
QProgressBar::chunk { border-radius:3px; background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #2c8fc5,stop:.55 #69ccfb,stop:1 #9be4ff); }
QProgressBar#fatBar { min-height:12px; max-height:12px; border-radius:5px; }
QPlainTextEdit { background:#061019; border:1px solid #1e384d; border-radius:8px; color:#86a2b7; padding:8px; }

/* status rail */
QFrame#nextStatus { background:#08131d; border-top:1px solid #20384b; }

/* scrollbars */
QScrollBar:vertical { background:#09131d; width:9px; margin:2px; }
QScrollBar::handle:vertical { background:#284960; min-height:30px; border-radius:4px; }
QScrollBar::handle:vertical:hover { background:#3b6d8d; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background:transparent; }
QSplitter::handle { background:#1a3144; width:1px; }

/* Big Picture - same new material language, original controls/contracts */
QWidget#bigPictureRoot { background:qradialgradient(cx:.55,cy:.15,radius:1.0,stop:0 #17354b,stop:.48 #0d1c29,stop:1 #061019); }
QFrame#bpHeader { background:rgba(7,16,24,220); border-bottom:1px solid #27465e; }
QLineEdit#bpSearch { background:#14283a; border:1px solid #41647d; border-radius:17px; padding:9px 16px; color:#fff; }
QLabel#bpTab, QLabel#bpTabActive { color:#8ca3b5; padding:9px 20px; font-weight:800; }
QLabel#bpTabActive { color:#fff; background:#244a65; border:1px solid #477898; border-radius:17px; }
QFrame#bpFooter { background:#061019; border-top:1px solid #243e53; }
QLabel#bpSteamPill, QLabel#bpGlyph { color:#07121b; background:#e2f3fd; }
"""


class FadeStack(QStackedWidget):
    """Cross-fades destination pages without changing page semantics."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._fade_anim = None
        self._fade_effect = None

    def setCurrentIndex(self, index: int):
        if index == self.currentIndex() or index < 0 or index >= self.count():
            return super().setCurrentIndex(index)
        super().setCurrentIndex(index)
        page = self.currentWidget()
        if page is None:
            return
        old = page.graphicsEffect()
        if old is not None and not isinstance(old, QGraphicsOpacityEffect):
            return
        effect = old if isinstance(old, QGraphicsOpacityEffect) else QGraphicsOpacityEffect(page)
        page.setGraphicsEffect(effect)
        effect.setOpacity(0.18)
        anim = QPropertyAnimation(effect, b"opacity", self)
        anim.setDuration(260)
        anim.setStartValue(0.18)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        self._fade_effect = effect
        self._fade_anim = anim
        anim.start()


class GlowButton(QPushButton):
    """A real hover/focus animation rather than a global decorative overlay."""

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setBlurRadius(7)
        self._shadow.setOffset(0, 2)
        self._shadow.setColor(QColor(52, 139, 190, 45))
        self.setGraphicsEffect(self._shadow)
        self._glow = QPropertyAnimation(self._shadow, b"blurRadius", self)
        self._glow.setDuration(150)
        self._glow.setEasingCurve(QEasingCurve.OutCubic)

    def _to(self, radius: float):
        self._glow.stop()
        self._glow.setStartValue(self._shadow.blurRadius())
        self._glow.setEndValue(radius)
        self._glow.start()

    def enterEvent(self, event):
        self._shadow.setColor(QColor(77, 183, 235, 125))
        self._to(24)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._shadow.setColor(QColor(52, 139, 190, 45))
        self._to(7)
        super().leaveEvent(event)

    def focusInEvent(self, event):
        self._to(24)
        super().focusInEvent(event)

    def focusOutEvent(self, event):
        self._to(7)
        super().focusOutEvent(event)


class CinematicHero(BASE.SteamHeroView):
    """Completely repainted hero with slow camera drift and light parallax."""

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(370)
        self.setMaximumHeight(430)
        self._camera = 0.0
        self._camera_anim = QVariantAnimation(self)
        self._camera_anim.setStartValue(0.0)
        self._camera_anim.setEndValue(1.0)
        self._camera_anim.setDuration(18000)
        self._camera_anim.setLoopCount(-1)
        self._camera_anim.setEasingCurve(QEasingCurve.InOutSine)
        self._camera_anim.valueChanged.connect(self._camera_step)
        self._camera_anim.start()

    def _camera_step(self, value):
        self._camera = float(value)
        if self.isVisible():
            self.update()

    def paintEvent(self, event):
        QFrame.paintEvent(self, event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        rect = self.rect()

        if not self.hero.isNull() and rect.width() > 0 and rect.height() > 0:
            phase = math.sin(self._camera * math.tau)
            zoom = 1.075 + 0.018 * math.cos(self._camera * math.tau)
            target_w = max(int(rect.width() * zoom), rect.width())
            target_h = max(int(rect.height() * zoom), rect.height())
            scaled = self.hero.scaled(target_w, target_h, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            overflow_x = max(scaled.width() - rect.width(), 0)
            overflow_y = max(scaled.height() - rect.height(), 0)
            sx = int(overflow_x * (0.50 + 0.18 * phase))
            sy = int(overflow_y * (0.42 + 0.08 * math.cos(self._camera * math.tau)))
            source = scaled.rect().adjusted(sx, sy, -(overflow_x - sx), -(overflow_y - sy))
            painter.drawPixmap(rect, scaled, source)
        else:
            bg = QLinearGradient(0, 0, rect.width(), rect.height())
            bg.setColorAt(0, QColor("#142b3d"))
            bg.setColorAt(1, QColor("#07111a"))
            painter.fillRect(rect, bg)

        # cinematic left/bottom scrim
        side = QLinearGradient(0, 0, max(rect.width() * 0.72, 1), 0)
        side.setColorAt(0.0, QColor(5, 12, 18, 225))
        side.setColorAt(0.48, QColor(5, 12, 18, 105))
        side.setColorAt(1.0, QColor(5, 12, 18, 8))
        painter.fillRect(rect, side)
        bottom = QLinearGradient(0, rect.height() * 0.45, 0, rect.height())
        bottom.setColorAt(0.0, QColor(8, 17, 26, 0))
        bottom.setColorAt(1.0, QColor(8, 17, 26, 245))
        painter.fillRect(rect, bottom)

        # moving cool rim light tied to camera phase
        x = int(rect.width() * (0.66 + 0.08 * math.sin(self._camera * math.tau)))
        glow = QRadialGradient(QPointF(x, rect.height() * 0.18), max(rect.width(), rect.height()) * 0.43)
        glow.setColorAt(0.0, QColor(91, 191, 239, 30))
        glow.setColorAt(0.48, QColor(50, 126, 168, 8))
        glow.setColorAt(1.0, QColor(20, 70, 100, 0))
        painter.fillRect(rect, QBrush(glow))

        if not self.logo.isNull():
            target = self.logo.scaled(430, 150, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            painter.drawPixmap(34, max(rect.height() - target.height() - 34, 18), target)
        else:
            painter.setPen(QColor("#ffffff"))
            font = painter.font()
            font.setPointSize(25)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(36, max(rect.height() - 54, 50), self.fallback_title)

        if getattr(self, "_reveal", 1.0) < 1.0:
            painter.fillRect(rect, QColor(5, 12, 18, int((1.0 - self._reveal) * 190)))
        painter.end()


class DownloadScene(BASE.DownloadHeroPanel):
    """Downloads hero with a moving network-light sweep."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(245)
        self._phase = 0.0
        self._anim = QVariantAnimation(self)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setDuration(6200)
        self._anim.setLoopCount(-1)
        self._anim.valueChanged.connect(self._step)
        self._anim.start()

    def _step(self, value):
        self._phase = float(value)
        if self.isVisible():
            self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        x = int((-0.15 + 1.3 * self._phase) * self.width())
        beam = QLinearGradient(x - 180, 0, x + 180, 0)
        beam.setColorAt(0, QColor(95, 199, 247, 0))
        beam.setColorAt(.5, QColor(112, 211, 255, 22))
        beam.setColorAt(1, QColor(95, 199, 247, 0))
        painter.fillRect(self.rect(), beam)
        painter.end()


class StatusRail(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("nextStatus")
        self._phase = 0.0
        self._anim = QVariantAnimation(self)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setDuration(4800)
        self._anim.setLoopCount(-1)
        self._anim.valueChanged.connect(self._step)
        self._anim.start()

    def _step(self, value):
        self._phase = float(value)
        if self.isVisible():
            self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        w = max(self.width(), 1)
        x = int((-0.25 + 1.5 * self._phase) * w)
        grad = QLinearGradient(x - 220, 0, x + 220, 0)
        grad.setColorAt(0, QColor(70, 170, 220, 0))
        grad.setColorAt(.5, QColor(76, 185, 238, 10))
        grad.setColorAt(1, QColor(70, 170, 220, 0))
        painter.fillRect(self.rect(), grad)
        painter.end()


class Launcher(previous.Launcher):
    """v0.12 behaviour with a ground-up v0.14 desktop presentation."""

    def __init__(self):
        self._game_fade = None
        self._game_fade_effect = None
        super().__init__()
        self.setWindowTitle(f"Drowned Launcher {APP_VERSION} • Next Library UI")
        self.resize(max(self.width(), 1460), max(self.height(), 900))
        if hasattr(self, "library"):
            self.library.currentRowChanged.connect(self._animate_game_surface)
        QTimer.singleShot(0, self._animate_game_surface)

    # ------------------------------------------------------------------
    # COMPLETE DESKTOP REBUILD. Functional methods remain inherited.
    # ------------------------------------------------------------------
    def _build_ui(self):
        QApplication.instance().setStyleSheet(NEXT_STYLE)
        root = QWidget()
        root.setObjectName("nextRoot")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self._chrome_widgets = []

        # New 62px application header.
        top = QFrame()
        top.setObjectName("nextTop")
        top.setFixedHeight(62)
        top_l = QHBoxLayout(top)
        top_l.setContentsMargins(16, 0, 14, 0)
        top_l.setSpacing(8)

        cube = QLabel("D")
        cube.setObjectName("brandCube")
        cube.setAlignment(Qt.AlignCenter)
        cube.setFixedSize(34, 34)
        top_l.addWidget(cube)
        brand = QVBoxLayout()
        brand.setSpacing(0)
        title = QLabel("DROWNED")
        title.setObjectName("brandTitle")
        sub = QLabel("GAME LIBRARY")
        sub.setObjectName("brandSub")
        brand.addWidget(title)
        brand.addWidget(sub)
        top_l.addLayout(brand)
        top_l.addSpacing(24)

        self.nav_library = BASE.ClickableLabel("KÜTÜPHANE")
        self.nav_library.setObjectName("navActive")
        self.nav_downloads = BASE.ClickableLabel("İNDİRMELER")
        self.nav_downloads.setObjectName("nav")
        self.nav_library.clicked.connect(lambda: self._show_right_page(0))
        self.nav_downloads.clicked.connect(lambda: self._show_right_page(1))
        top_l.addWidget(self.nav_library)
        top_l.addWidget(self.nav_downloads)
        top_l.addStretch()

        self.connection = QLabel("RAW • bağlanıyor")
        self.connection.setObjectName("connectionOnline")
        top_l.addWidget(self.connection)
        top_l.addSpacing(8)
        self.big_picture_button = QPushButton("⛶")
        self.big_picture_button.setObjectName("iconButton")
        self.big_picture_button.setToolTip("Big Picture (F11)")
        refresh = QPushButton("↻")
        refresh.setObjectName("iconButton")
        refresh.setToolTip("Kataloğu yenile")
        refresh.clicked.connect(self.load_catalog)
        settings = QPushButton("⚙")
        settings.setObjectName("iconButton")
        settings.setToolTip("Ayarlar")
        settings.clicked.connect(self.open_settings)
        top_l.addWidget(self.big_picture_button)
        top_l.addWidget(refresh)
        top_l.addWidget(settings)
        outer.addWidget(top)
        self._chrome_widgets.append(top)

        self.main_stack = FadeStack()
        self.main_stack.addWidget(self._build_desktop_shell())
        self.library_grid_bp = BASE.GameGridView()
        self.big_picture = BASE.BigPictureView(self.library_grid_bp)
        self.main_stack.addWidget(self.big_picture)
        outer.addWidget(self.main_stack, 1)

        # New live transfer rail. Keep exact legacy attribute contracts.
        status_shell = StatusRail()
        status_shell.setFixedHeight(58)
        s_outer = QVBoxLayout(status_shell)
        s_outer.setContentsMargins(16, 8, 16, 8)
        s_outer.setSpacing(4)
        self.download_card = QFrame()
        dl = QVBoxLayout(self.download_card)
        dl.setContentsMargins(0, 0, 0, 0)
        dl.setSpacing(3)
        row = QHBoxLayout()
        row.setSpacing(10)
        self.download_dot = QLabel("●")
        self.download_dot.setObjectName("downloadDot")
        self.status_icon = BASE.IconLabel(27, 27)
        self.status_icon.hide()
        self.status = QLabel("Hazır")
        self.status.setObjectName("downloadTitle")
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setMinimumWidth(280)
        self.progress_text = QLabel("")
        self.progress_text.setObjectName("progressText")
        row.addWidget(self.download_dot)
        row.addWidget(self.status_icon)
        row.addWidget(self.status, 0)
        row.addSpacing(8)
        row.addWidget(self.progress, 1)
        row.addWidget(self.progress_text)
        self._status_row = row
        self.logs = QPlainTextEdit()
        self.logs.setReadOnly(True)
        self.logs.setFixedHeight(68)
        self.logs.hide()
        dl.addLayout(row)
        dl.addWidget(self.logs)
        s_outer.addWidget(self.download_card)
        outer.addWidget(status_shell)
        self._chrome_widgets.append(status_shell)

        self._wire_runtime()

    def _build_desktop_shell(self):
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        self.main_splitter = splitter
        splitter.addWidget(self._build_sidebar())

        detail = QFrame()
        detail.setObjectName("nextDetail")
        detail_l = QVBoxLayout(detail)
        detail_l.setContentsMargins(0, 0, 0, 0)
        detail_l.setSpacing(0)
        self.right_stack = FadeStack()
        self.right_stack.addWidget(self._build_game_page())
        self.right_stack.addWidget(self._build_downloads_page())
        detail_l.addWidget(self.right_stack)
        splitter.addWidget(detail)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([310, 1180])
        return splitter

    def _build_sidebar(self):
        sidebar = QFrame()
        sidebar.setObjectName("nextSidebar")
        sidebar.setMinimumWidth(270)
        sidebar.setMaximumWidth(390)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(14, 16, 10, 12)
        side.setSpacing(9)

        head = QHBoxLayout()
        title = QLabel("OYUNLAR")
        title.setObjectName("libraryTitle")
        self.game_count = QLabel("0 oyun")
        self.game_count.setObjectName("libraryCount")
        head.addWidget(title)
        head.addStretch()
        head.addWidget(self.game_count)
        side.addLayout(head)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Kütüphanede ara…")
        self.search.setClearButtonEnabled(True)
        self._search_debounce = QTimer(self)
        self._search_debounce.setSingleShot(True)
        self._search_debounce.setInterval(150)
        self._search_debounce.timeout.connect(self.render_library)
        self.search.textChanged.connect(lambda _text: self._search_debounce.start())
        side.addWidget(self.search)

        filters = QHBoxLayout()
        filters.setSpacing(7)
        self.platform = QComboBox()
        self.platform.addItem("Tümü")
        self.channel = QComboBox()
        self.channel.addItems(["stable", "beta", "dev", "nightly", "archive"])
        self.platform.currentTextChanged.connect(self.render_library)
        self.channel.currentTextChanged.connect(self.render_library)
        filters.addWidget(self.platform, 1)
        filters.addWidget(self.channel, 1)
        side.addLayout(filters)

        label = QLabel("KÜTÜPHANE")
        label.setObjectName("sectionLabel")
        side.addWidget(label)

        self.library = QListWidget()
        self.library.currentItemChanged.connect(self.library_selection_changed)
        self.library.hide()
        side.addWidget(self.library)
        self.library_grid = BASE.GameListView()
        self.library_grid.setObjectName("nextLibraryGrid")
        side.addWidget(self.library_grid, 1)
        return sidebar

    def _build_game_page(self):
        # A scrollable Steam-like game surface. The action deck stays a direct
        # child so app_v12 can insert Optional Packages beneath it unchanged.
        scroller = QScrollArea()
        scroller.setWidgetResizable(True)
        scroller.setFrameShape(QFrame.NoFrame)
        surface = QFrame()
        surface.setObjectName("nextContent")
        self.game_surface = surface
        layout = QVBoxLayout(surface)
        layout.setContentsMargins(0, 0, 0, 28)
        layout.setSpacing(0)

        self.hero = CinematicHero()
        layout.addWidget(self.hero)

        action_bar = QFrame()
        action_bar.setObjectName("nextActionDeck")
        action = QHBoxLayout(action_bar)
        action.setContentsMargins(28, 17, 28, 17)
        action.setSpacing(16)

        self.info_card = QFrame(action_bar)
        self.info_card.setObjectName("infoCard")
        info = QHBoxLayout(self.info_card)
        info.setContentsMargins(0, 0, 0, 0)
        info.setSpacing(9)
        self.install_button = GlowButton("YÜKLE")
        self.install_button.setObjectName("install")
        self.install_button.clicked.connect(self.install_current_game)
        self.install_button.setEnabled(False)
        self.verify_button = GlowButton("DOSYALARI DOĞRULA")
        self.verify_button.setObjectName("secondary")
        self.verify_button.setEnabled(False)
        info.addWidget(self.install_button)
        info.addWidget(self.verify_button)
        action.addWidget(self.info_card)

        self.action_dl = QWidget()
        dl_l = QHBoxLayout(self.action_dl)
        dl_l.setContentsMargins(0, 0, 0, 0)
        dl_l.setSpacing(12)
        self.action_pause = GlowButton("DURAKLAT")
        self.action_pause.setObjectName("pauseButton")
        self.action_pause.clicked.connect(self.toggle_pause)
        dl_l.addWidget(self.action_pause)
        dl_text = QVBoxLayout()
        dl_text.setSpacing(2)
        self.action_dl_caption = QLabel("İNDİRİLİYOR")
        self.action_dl_caption.setObjectName("statName")
        self.action_dl_value = QLabel("%0 Tamamlandı")
        self.action_dl_value.setObjectName("rowValue")
        self.action_dl_bar = QProgressBar()
        self.action_dl_bar.setRange(0, 100)
        self.action_dl_bar.setValue(0)
        self.action_dl_bar.setTextVisible(False)
        self.action_dl_bar.setFixedWidth(160)
        dl_text.addWidget(self.action_dl_caption)
        dl_text.addWidget(self.action_dl_value)
        dl_text.addWidget(self.action_dl_bar)
        dl_l.addLayout(dl_text)
        self.action_dl.hide()
        action.addWidget(self.action_dl)
        action.addSpacing(12)

        stats = QHBoxLayout()
        stats.setSpacing(24)
        for caption, attr in (("PLATFORM", "stat_platform"), ("KANAL", "stat_channel"), ("SÜRÜM", "stat_version"), ("BOYUT", "stat_size")):
            box = QWidget()
            b = QVBoxLayout(box)
            b.setContentsMargins(0, 0, 0, 0)
            b.setSpacing(2)
            c = QLabel(caption)
            c.setObjectName("statName")
            v = QLabel("—")
            v.setObjectName("statValue")
            b.addWidget(c)
            b.addWidget(v)
            setattr(self, attr, v)
            stats.addWidget(box)
        action.addLayout(stats)
        action.addStretch()
        self.state_badge = QLabel("HAZIR")
        self.state_badge.setObjectName("connectionOnline")
        action.addWidget(self.state_badge, 0, Qt.AlignVCenter)
        layout.addWidget(action_bar)

        content = QFrame()
        content.setObjectName("nextContent")
        self.game_content = content
        c = QVBoxLayout(content)
        c.setContentsMargins(28, 22, 28, 8)
        c.setSpacing(0)
        self.title = QLabel("Kütüphane yükleniyor…")
        self.title.setObjectName("gameTitle")
        self.meta = QLabel("")
        self.meta.setObjectName("metaLine")
        c.addWidget(self.title)
        c.addWidget(self.meta)
        c.addSpacing(14)

        tabs = QHBoxLayout()
        tabs.setSpacing(2)
        self.tab_overview = BASE.ClickableLabel("GENEL BAKIŞ")
        self.tab_overview.setObjectName("tabActive")
        self.tab_shots = BASE.ClickableLabel("EKRAN GÖRÜNTÜLERİ")
        self.tab_shots.setObjectName("tab")
        self.tab_overview.clicked.connect(lambda: self._show_detail_tab(0))
        self.tab_shots.clicked.connect(lambda: self._show_detail_tab(1))
        tabs.addWidget(self.tab_overview)
        tabs.addWidget(self.tab_shots)
        tabs.addStretch()
        c.addLayout(tabs)
        line = QFrame(); line.setObjectName("hairline"); line.setFixedHeight(1)
        c.addWidget(line)
        c.addSpacing(16)

        columns = QHBoxLayout()
        columns.setSpacing(18)
        self.detail_stack = FadeStack()

        overview = QFrame()
        overview.setObjectName("nextCard")
        ov = QVBoxLayout(overview)
        ov.setContentsMargins(18, 16, 18, 18)
        cap = QLabel("OYUN HAKKINDA")
        cap.setObjectName("panelTitle")
        self.description = QLabel("Raw GitHub kataloğundan oyunlar yükleniyor.")
        self.description.setObjectName("description")
        self.description.setWordWrap(True)
        self.description.setAlignment(Qt.AlignTop)
        ov.addWidget(cap)
        ov.addSpacing(8)
        ov.addWidget(self.description, 1)
        self.detail_stack.addWidget(overview)

        shots = QFrame()
        shots.setObjectName("nextCard")
        sh = QVBoxLayout(shots)
        sh.setContentsMargins(14, 14, 14, 14)
        self.screenshot_gallery = BASE.ScreenshotGallery()
        sh.addWidget(self.screenshot_gallery)
        self.detail_stack.addWidget(shots)
        columns.addWidget(self.detail_stack, 1)
        columns.addWidget(self._build_side_panels(), 0)
        c.addLayout(columns, 1)
        layout.addWidget(content, 1)

        self.cover = BASE.previous.CoverLabel()
        self.cover.setParent(surface)
        self.cover.hide()
        scroller.setWidget(surface)
        return scroller

    def _build_side_panels(self):
        col = QWidget()
        col.setFixedWidth(330)
        lay = QVBoxLayout(col)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)

        install = QFrame(); install.setObjectName("panel")
        il = QVBoxLayout(install); il.setContentsMargins(15, 13, 15, 13); il.setSpacing(5)
        cap = QLabel("KURULUM"); cap.setObjectName("panelTitle"); il.addWidget(cap); il.addSpacing(4)
        for key, attr in (("Durum", "panel_state"), ("Klasör", "panel_path"), ("Etiket", "panel_tag")):
            row = QWidget(); rl = QHBoxLayout(row); rl.setContentsMargins(0, 3, 0, 3)
            k = QLabel(key); k.setObjectName("rowKey")
            v = QLabel("—"); v.setObjectName("rowValue"); v.setAlignment(Qt.AlignRight | Qt.AlignVCenter); v.setWordWrap(True)
            rl.addWidget(k); rl.addStretch(); rl.addWidget(v, 1)
            setattr(self, attr, v); il.addWidget(row)
        lay.addWidget(install)

        source = QFrame(); source.setObjectName("panel")
        sl = QVBoxLayout(source); sl.setContentsMargins(15, 13, 15, 13); sl.setSpacing(5)
        cap = QLabel("KAYNAK"); cap.setObjectName("panelTitle"); sl.addWidget(cap); sl.addSpacing(4)
        for key, attr in (("Repo", "panel_repo"), ("Branch", "panel_branch")):
            row = QWidget(); rl = QHBoxLayout(row); rl.setContentsMargins(0, 3, 0, 3)
            k = QLabel(key); k.setObjectName("rowKey")
            v = QLabel("—"); v.setObjectName("rowValue"); v.setAlignment(Qt.AlignRight | Qt.AlignVCenter); v.setWordWrap(True)
            rl.addWidget(k); rl.addStretch(); rl.addWidget(v, 1)
            setattr(self, attr, v); sl.addWidget(row)
        lay.addWidget(source)
        lay.addStretch()
        return col

    def _build_downloads_page(self):
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.dlp_hero = DownloadScene()
        hero_l = QHBoxLayout(self.dlp_hero)
        hero_l.setContentsMargins(30, 24, 34, 24)
        hero_l.addStretch()
        live = QFrame(); live.setObjectName("nextCard"); live.setMinimumWidth(610)
        ll = QVBoxLayout(live); ll.setContentsMargins(20, 16, 20, 16); ll.setSpacing(8)
        metrics = QHBoxLayout(); metrics.setSpacing(34)
        self.dlp_net = BASE.Launcher._metric_column(metrics, "AĞ")
        self.dlp_peak = BASE.Launcher._metric_column(metrics, "EN YÜKSEK")
        self.dlp_streams = BASE.Launcher._metric_column(metrics, "AKIŞ")
        metrics.addStretch(); ll.addLayout(metrics)
        self.dlp_limit = QLabel("GitHub Releases • Direct download")
        self.dlp_limit.setObjectName("statName"); ll.addWidget(self.dlp_limit)
        data = QHBoxLayout(); a = QLabel("AKTARILAN"); a.setObjectName("rowKey"); self.dlp_bytes = QLabel("—"); self.dlp_bytes.setObjectName("rowValue")
        data.addWidget(a); data.addStretch(); data.addWidget(self.dlp_bytes); ll.addLayout(data)
        self.dlp_bar = QProgressBar(); self.dlp_bar.setObjectName("fatBar"); self.dlp_bar.setRange(0,100); self.dlp_bar.setValue(0); self.dlp_bar.setTextVisible(False); ll.addWidget(self.dlp_bar)
        vr = QHBoxLayout(); vcap = QLabel("İLERLEME"); vcap.setObjectName("rowKey"); self.dlp_percent = QLabel("%0"); self.dlp_percent.setObjectName("rowValue"); vr.addWidget(vcap); vr.addStretch(); vr.addWidget(self.dlp_percent); ll.addLayout(vr)
        bottom = QHBoxLayout(); self.dlp_eta = QLabel("Kalan tahmini süre: —"); self.dlp_eta.setObjectName("muted"); bottom.addWidget(self.dlp_eta); bottom.addStretch(); self.dlp_pause = GlowButton("DURAKLAT"); self.dlp_pause.setObjectName("secondary"); self.dlp_pause.clicked.connect(self.toggle_pause); self.dlp_pause.hide(); bottom.addWidget(self.dlp_pause); ll.addLayout(bottom)
        hero_l.addWidget(live)
        outer.addWidget(self.dlp_hero)

        body = QWidget(); bl = QVBoxLayout(body); bl.setContentsMargins(30, 24, 30, 24); bl.setSpacing(10)
        self.dlp_title = QLabel("Etkin indirme yok"); self.dlp_title.setObjectName("gameTitle"); bl.addWidget(self.dlp_title)
        self.dlp_detail = QLabel("Kütüphaneden bir oyun seçip YÜKLE ile indirmeyi başlat."); self.dlp_detail.setObjectName("muted"); self.dlp_detail.setWordWrap(True); bl.addWidget(self.dlp_detail); bl.addSpacing(16)

        queue = QFrame(); queue.setObjectName("nextCard"); ql = QVBoxLayout(queue); ql.setContentsMargins(16,14,16,14)
        qh = QHBoxLayout(); self.dlp_queue_caption = QLabel("SIRADAKİ (0)"); self.dlp_queue_caption.setObjectName("panelTitle"); note = QLabel("Tek seferde bir indirme çalışır"); note.setObjectName("muted"); qh.addWidget(self.dlp_queue_caption); qh.addStretch(); qh.addWidget(note); ql.addLayout(qh)
        self.dlp_queue_body = QLabel("Kuyrukta indirme yok."); self.dlp_queue_body.setObjectName("muted"); ql.addWidget(self.dlp_queue_body); bl.addWidget(queue)

        done = QFrame(); done.setObjectName("nextCard"); dl = QVBoxLayout(done); dl.setContentsMargins(16,14,16,14); dl.setSpacing(7)
        self.dlp_done_caption = QLabel("TAMAMLANDI (0)"); self.dlp_done_caption.setObjectName("panelTitle"); dl.addWidget(self.dlp_done_caption)
        self.dlp_done_empty = QLabel("Henüz tamamlanmış kurulum yok."); self.dlp_done_empty.setObjectName("muted"); dl.addWidget(self.dlp_done_empty)
        self.dlp_rows_layout = QVBoxLayout(); self.dlp_rows_layout.setSpacing(7); dl.addLayout(self.dlp_rows_layout)
        bl.addWidget(done); bl.addStretch()
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.NoFrame); scroll.setWidget(body); outer.addWidget(scroll,1)
        self._completed_rows = []
        return page

    def _animate_game_surface(self, *_args):
        target = getattr(self, "game_content", None)
        if target is None:
            return
        if self._game_fade_effect is None:
            self._game_fade_effect = QGraphicsOpacityEffect(target)
            target.setGraphicsEffect(self._game_fade_effect)
        if self._game_fade is not None:
            self._game_fade.stop()
        self._game_fade_effect.setOpacity(0.30)
        anim = QPropertyAnimation(self._game_fade_effect, b"opacity", self)
        anim.setDuration(330)
        anim.setStartValue(0.30)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        self._game_fade = anim
        anim.start()


def main():
    BASE.base.install_exception_hook()
    app = QApplication(sys.argv)
    app.setApplicationName("Drowned Launcher")
    app.setOrganizationName("Drowned")
    app.setStyle("Fusion")
    app.setStyleSheet(NEXT_STYLE)
    splash = QSplashScreen(BASE._splash_pixmap())
    splash.show()
    app.processEvents()
    win = Launcher()
    win.show()
    splash.finish(win)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
