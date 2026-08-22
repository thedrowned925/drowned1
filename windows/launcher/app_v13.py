from __future__ import annotations

import math
import sys

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QObject,
    QPointF,
    QPropertyAnimation,
    QRectF,
    Qt,
    QTimer,
    QVariantAnimation,
)
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QRadialGradient
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QPushButton,
    QSplashScreen,
    QWidget,
)

import app_v12 as previous

APP_VERSION = "0.13.0"

# ---------------------------------------------------------------------------
# IMPORTANT: this module is presentation-only.
#
# app_v12 remains the complete functional implementation.  No downloader,
# installer, verification, optional-package, registry, catalog, controller,
# settings or network method is replaced here.  The v0.13 class only adds a
# Steam-inspired presentation layer and motion around those existing widgets.
# ---------------------------------------------------------------------------

PREMIUM_STEAM_STYLE = previous.previous.previous.STEAM_STYLE + r"""
/* ========================================================================
   DROWNED LAUNCHER v0.13 — STEAM-INSPIRED PREMIUM PRESENTATION LAYER
   Presentation only. Existing object names and widget contracts are kept.
   ======================================================================== */

QWidget {
    font-family: "Segoe UI Variable", "Segoe UI", "Arial";
    color: #d6e2ee;
}
QMainWindow, QWidget#root {
    background: #0d151f;
}

/* ---- layered Steam-like chrome ---------------------------------------- */
QFrame#menubar {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #101923, stop:0.45 #151f2b, stop:1 #0d151e);
    border: 0;
}
QFrame#navbar {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #111a25, stop:0.55 #172330, stop:1 #101822);
    border-bottom: 1px solid #26394d;
}
QLabel#navActive {
    color: #ffffff;
    font-size: 14px;
    font-weight: 750;
    padding: 13px 15px 11px 15px;
    border-bottom: 3px solid #66c0f4;
    background: rgba(102, 192, 244, 10);
}
QLabel#nav {
    color: #8798a8;
    font-size: 14px;
    font-weight: 700;
    padding: 13px 15px;
}
QLabel#nav:hover { color: #e9f6ff; background: rgba(102,192,244,8); }
QLabel#menuItem { color: #8996a4; }
QLabel#menuItem:hover { color: #ffffff; }
QLabel#navUser { color: #b8c5d0; }

/* ---- sidebar ---------------------------------------------------------- */
QFrame#sidebar {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #111a24, stop:0.88 #152231, stop:1 #172737);
    border-right: 1px solid #26394d;
}
QLabel#sectionLabel {
    color: #60788e;
    font-size: 10px;
    font-weight: 800;
    letter-spacing: 2px;
}
QListWidget {
    background: transparent;
    border: 0;
    outline: 0;
    padding: 5px 0;
}
QListWidget::item {
    color: #aebdca;
    padding: 8px 10px;
    margin: 1px 4px;
    border-radius: 4px;
    border-left: 3px solid transparent;
}
QListWidget::item:hover {
    color: #f0f8ff;
    background: rgba(60, 94, 123, 90);
    border-left-color: #3d6c93;
}
QListWidget::item:selected {
    color: #ffffff;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 rgba(52, 91, 124, 220), stop:1 rgba(35, 61, 83, 155));
    border-left: 3px solid #66c0f4;
}

/* ---- detail / hero surround ------------------------------------------ */
QFrame#detail {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #14202c, stop:0.34 #111b26, stop:1 #0d151f);
}
QFrame#actionBar {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 rgba(18,31,43,245), stop:0.55 rgba(23,39,54,245), stop:1 rgba(15,26,37,245));
    border-top: 1px solid #2a3e52;
    border-bottom: 1px solid #0a1017;
}
QFrame#panel {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 rgba(24, 39, 54, 242), stop:1 rgba(17, 29, 41, 242));
    border: 1px solid #2a4056;
    border-radius: 9px;
}
QFrame#panel:hover {
    border-color: #385b78;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 rgba(28, 47, 65, 245), stop:1 rgba(18, 32, 45, 245));
}
QFrame#infoCard {
    background: transparent;
    border: 0;
}
QFrame#hairline { background: #284158; }

QLabel#gameTitle {
    color: #ffffff;
    font-size: 30px;
    font-weight: 800;
}
QLabel#metaLine { color: #67c1f5; font-size: 12px; font-weight: 700; }
QLabel#description { color: #afbecb; font-size: 13px; }
QLabel#panelTitle {
    color: #87a0b6;
    font-size: 10px;
    font-weight: 850;
    letter-spacing: 2px;
}
QLabel#statName { color: #60788d; font-weight: 800; letter-spacing: 1px; }
QLabel#statValue { color: #e4edf5; font-weight: 750; }
QLabel#rowKey { color: #698097; }
QLabel#rowValue { color: #d7e3ee; font-weight: 650; }
QLabel#muted { color: #71889b; }
QLabel#connectionOnline {
    color: #a8e26d;
    background: rgba(50, 92, 31, 35);
    border: 1px solid rgba(125, 184, 41, 80);
    border-radius: 10px;
    padding: 4px 8px;
}

/* ---- inputs ----------------------------------------------------------- */
QLineEdit, QComboBox {
    min-height: 20px;
    background: rgba(7, 13, 20, 205);
    border: 1px solid #263b50;
    border-radius: 7px;
    padding: 7px 10px;
    color: #dbe8f3;
    selection-background-color: #2f6f9e;
}
QLineEdit:hover, QComboBox:hover { border-color: #3a5a76; }
QLineEdit:focus, QComboBox:focus {
    border-color: #66c0f4;
    background: rgba(8, 16, 24, 235);
}
QComboBox QAbstractItemView {
    background: #101b27;
    color: #d8e5ef;
    border: 1px solid #34516d;
    selection-background-color: #294c68;
    padding: 4px;
}

/* ---- buttons: Steam client depth without changing actions ------------ */
QPushButton {
    min-height: 21px;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #334c64, stop:1 #24394d);
    color: #d5e3ee;
    border: 1px solid #41617e;
    border-radius: 7px;
    padding: 8px 16px;
    font-weight: 750;
}
QPushButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #4a789d, stop:1 #315b7b);
    color: #ffffff;
    border-color: #66a7d5;
}
QPushButton:pressed {
    background: #20394e;
    border-color: #315b78;
    padding-top: 9px;
    padding-bottom: 7px;
}
QPushButton:disabled {
    background: #151f2a;
    color: #536575;
    border-color: #263544;
}
QPushButton#install {
    min-height: 28px;
    padding: 10px 32px;
    font-size: 15px;
    font-weight: 850;
    color: #f4ffe8;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #5c9617, stop:0.52 #75b022, stop:1 #4f8412);
    border: 1px solid #8dca35;
    border-radius: 8px;
}
QPushButton#install:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #70ad20, stop:0.52 #8bc53f, stop:1 #63a016);
    border-color: #a8e54d;
}
QPushButton#secondary {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #31495f, stop:1 #22374a);
    border-color: #3b5871;
}
QPushButton#danger {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #48262d, stop:1 #321c22);
    border-color: #6b3943;
    color: #efbdc4;
}
QPushButton#danger:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #63313c, stop:1 #45232a);
    border-color: #9b5261;
    color: #ffe3e7;
}
QPushButton#iconButton {
    min-width: 32px; max-width: 32px;
    min-height: 32px; max-height: 32px;
    border-radius: 7px;
    padding: 0;
}
QPushButton#linkButton {
    background: transparent;
    border: 0;
    color: #67c1f5;
    padding: 5px 7px;
}
QPushButton#linkButton:hover { color: #ffffff; background: rgba(102,192,244,10); }

/* ---- optional content ------------------------------------------------- */
QCheckBox {
    spacing: 10px;
    color: #d9e5ef;
    font-weight: 700;
    padding: 3px 2px;
}
QCheckBox:disabled { color: #647789; }
QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border-radius: 4px;
    border: 1px solid #45627d;
    background: #0c151f;
}
QCheckBox::indicator:hover { border-color: #67c1f5; background: #132638; }
QCheckBox::indicator:checked {
    border: 1px solid #8ad3ff;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #67c1f5, stop:1 #2b78a7);
}
QCheckBox::indicator:checked:disabled {
    border-color: #4c6c81;
    background: #31536a;
}

/* ---- tabs ------------------------------------------------------------- */
QLabel#tabActive {
    color: #ffffff;
    font-weight: 800;
    padding: 11px 17px 9px 17px;
    border-bottom: 3px solid #66c0f4;
    background: rgba(102,192,244,8);
}
QLabel#tab {
    color: #8397a9;
    font-weight: 750;
    padding: 11px 17px 9px 17px;
    border-bottom: 3px solid transparent;
}
QLabel#tab:hover { color: #ffffff; background: rgba(102,192,244,6); }

/* ---- progress / logs -------------------------------------------------- */
QProgressBar {
    min-height: 7px;
    max-height: 7px;
    background: #070d13;
    border: 1px solid #172736;
    border-radius: 3px;
    color: transparent;
}
QProgressBar::chunk {
    border-radius: 3px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #2f86ba, stop:0.5 #66c0f4, stop:1 #8edcff);
}
QProgressBar#fatBar { min-height: 11px; max-height: 11px; }
QPlainTextEdit {
    background: rgba(6, 11, 17, 220);
    border: 1px solid #24384c;
    border-radius: 7px;
    color: #8fa8bc;
    padding: 8px 10px;
    selection-background-color: #2c5c7f;
}

/* ---- download/status bars -------------------------------------------- */
QFrame#statusbar, QFrame#downloadBar {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #0d151e, stop:0.5 #111c27, stop:1 #0c141d);
    border-top: 1px solid #26394d;
}
QFrame#downloadCard {
    background: rgba(20, 34, 47, 170);
    border: 1px solid rgba(61, 97, 125, 90);
    border-radius: 7px;
}
QLabel#progressText { color: #75cbfa; font-weight: 700; }
QLabel#downloadDot { color: #67c1f5; }

/* ---- scroll bars ------------------------------------------------------ */
QScrollBar:vertical {
    background: #0d1721;
    width: 10px;
    margin: 1px;
}
QScrollBar::handle:vertical {
    background: #29455e;
    min-height: 32px;
    border-radius: 4px;
}
QScrollBar::handle:vertical:hover { background: #3a6687; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QScrollBar:horizontal { background: #0d1721; height: 10px; }
QScrollBar::handle:horizontal { background: #29455e; min-width: 32px; border-radius: 4px; }
QScrollBar::handle:horizontal:hover { background: #3a6687; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }
QSplitter::handle { background: #26394d; width: 1px; }

/* ---- Big Picture gets the same material language --------------------- */
QWidget#bigPictureRoot {
    background: qradialgradient(cx:0.5, cy:0.16, radius:1.1,
        stop:0 #20384c, stop:0.48 #121f2b, stop:1 #091018);
}
QFrame#bpHeader {
    background: rgba(10, 17, 24, 155);
    border-bottom: 1px solid rgba(78, 116, 145, 85);
}
QLineEdit#bpSearch {
    background: rgba(25, 39, 52, 225);
    border: 1px solid #4c6c87;
    border-radius: 18px;
    padding: 10px 17px;
    color: #ffffff;
}
QLineEdit#bpSearch:focus { border-color: #71c9fa; background: rgba(31,49,65,245); }
QLabel#bpTabActive {
    color: #ffffff;
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 #345a77, stop:1 #284963);
    border: 1px solid #4f7796;
    border-radius: 18px;
    padding: 9px 21px;
}
QLabel#bpTab { color: #a4b5c4; padding: 9px 21px; }
QLabel#bpTab:hover { color: #ffffff; background: rgba(70,104,131,80); border-radius:18px; }
QLabel#bpShoulder {
    color: #d9e8f3;
    background: rgba(48, 70, 89, 205);
    border: 1px solid #58758d;
    border-radius: 6px;
}
QFrame#bpFooter {
    background: rgba(6, 11, 16, 238);
    border-top: 1px solid #274056;
}
QLabel#bpSteamPill {
    color: #081019;
    background: #dcebf5;
    border-radius: 11px;
}
QLabel#bpGlyph { color:#081019; background:#dcebf5; border-radius:10px; }
"""


class CinematicHero(previous.previous.previous.SteamHeroView):
    """Adds a low-cost cinematic light sweep on top of the existing hero.

    The inherited hero still owns artwork, logo, zoom and reveal behaviour.
    This class only paints translucent motion after that work is complete.
    """

    def __init__(self):
        super().__init__()
        self._cinema_phase = 0.0
        self._cinema = QVariantAnimation(self)
        self._cinema.setStartValue(0.0)
        self._cinema.setEndValue(1.0)
        self._cinema.setDuration(9000)
        self._cinema.setLoopCount(-1)
        self._cinema.setEasingCurve(QEasingCurve.InOutSine)
        self._cinema.valueChanged.connect(self._set_cinema_phase)
        self._cinema.start()

    def _set_cinema_phase(self, value):
        self._cinema_phase = float(value)
        if self.isVisible():
            self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.width() <= 0 or self.height() <= 0:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # A broad, almost invisible studio-light sweep.
        x = (-0.35 + self._cinema_phase * 1.7) * self.width()
        beam = QLinearGradient(x - self.width() * 0.22, 0, x + self.width() * 0.22, 0)
        beam.setColorAt(0.0, QColor(102, 192, 244, 0))
        beam.setColorAt(0.48, QColor(126, 211, 255, 5))
        beam.setColorAt(0.50, QColor(170, 229, 255, 17))
        beam.setColorAt(0.52, QColor(126, 211, 255, 5))
        beam.setColorAt(1.0, QColor(102, 192, 244, 0))
        painter.fillRect(self.rect(), beam)

        # A gentle cool glow near the upper-right corner keeps dark hero art
        # from feeling flat without altering the artwork itself.
        glow = QRadialGradient(
            QPointF(self.width() * 0.82, self.height() * 0.12),
            max(self.width(), self.height()) * 0.48,
        )
        glow.setColorAt(0.0, QColor(102, 192, 244, 20))
        glow.setColorAt(0.38, QColor(66, 145, 194, 7))
        glow.setColorAt(1.0, QColor(30, 73, 105, 0))
        painter.fillRect(self.rect(), QBrush(glow))
        painter.end()


class AmbientMotionLayer(QWidget):
    """Very low-opacity atmospheric motes and light pools.

    It is deliberately mouse-transparent. It never participates in layout or
    input routing, so it cannot change Launcher behaviour.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(50)  # 20 fps: deliberately light on CPU/GPU.
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def _tick(self):
        self._phase = (self._phase + 0.0065) % 1.0
        if self.isVisible():
            self.update()

    def paintEvent(self, event):
        if self.width() < 2 or self.height() < 2:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w = float(self.width())
        h = float(self.height())
        t = self._phase * math.tau

        # Two slow moving pools of Steam-blue light.
        pools = (
            (0.72 + math.sin(t * 0.63) * 0.08, 0.18 + math.cos(t * 0.47) * 0.05, 0.42, 18),
            (0.34 + math.cos(t * 0.38) * 0.10, 0.70 + math.sin(t * 0.52) * 0.07, 0.36, 10),
        )
        for px, py, radius_factor, alpha in pools:
            radius = max(w, h) * radius_factor
            grad = QRadialGradient(QPointF(w * px, h * py), radius)
            grad.setColorAt(0.0, QColor(74, 169, 223, alpha))
            grad.setColorAt(0.42, QColor(42, 112, 158, max(2, alpha // 3)))
            grad.setColorAt(1.0, QColor(18, 52, 77, 0))
            painter.setBrush(QBrush(grad))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(QPointF(w * px, h * py), radius, radius)

        # Small drifting motes. Their positions are deterministic, avoiding
        # random allocations in the paint loop.
        for index in range(18):
            seed = index * 0.61803398875
            x = ((seed + self._phase * (0.05 + (index % 4) * 0.012)) % 1.0) * w
            y_base = ((index * 0.173) % 1.0) * h
            y = y_base + math.sin(t * (0.35 + index * 0.012) + index) * 18.0
            radius = 0.8 + (index % 3) * 0.55
            alpha = 9 + (index % 5) * 3
            painter.setBrush(QColor(111, 203, 250, alpha))
            painter.drawEllipse(QPointF(x, y), radius, radius)

        painter.end()


class AccentSweep(QWidget):
    """Thin travelling highlight along the top edge of the desktop shell."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(3)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self._phase = 0.0
        self._animation = QVariantAnimation(self)
        self._animation.setStartValue(0.0)
        self._animation.setEndValue(1.0)
        self._animation.setDuration(5200)
        self._animation.setLoopCount(-1)
        self._animation.valueChanged.connect(self._set_phase)
        self._animation.start()

    def _set_phase(self, value):
        self._phase = float(value)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        w = max(1, self.width())
        center = int((-0.20 + self._phase * 1.40) * w)
        gradient = QLinearGradient(0, 0, w, 0)
        left = max(0.0, min(1.0, (center - 160) / w))
        mid = max(0.0, min(1.0, center / w))
        right = max(0.0, min(1.0, (center + 160) / w))
        gradient.setColorAt(0.0, QColor(50, 116, 156, 18))
        if left > 0:
            gradient.setColorAt(left, QColor(57, 133, 178, 20))
        gradient.setColorAt(mid, QColor(119, 211, 255, 155))
        if right < 1:
            gradient.setColorAt(right, QColor(57, 133, 178, 20))
        gradient.setColorAt(1.0, QColor(50, 116, 156, 18))
        painter.fillRect(self.rect(), gradient)
        painter.end()


class MotionDirector(QObject):
    """Hover/focus glow animator for existing controls.

    No clicks, signals, enabled states or action wiring are modified.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._watched: set[int] = set()
        self._effects: dict[int, QGraphicsDropShadowEffect] = {}
        self._animations: dict[int, QPropertyAnimation] = {}

    def watch_all(self, root: QWidget):
        for widget in root.findChildren((QPushButton, QCheckBox)):
            self.watch(widget)

    def watch(self, widget: QWidget):
        key = id(widget)
        if key in self._watched:
            return
        self._watched.add(key)
        widget.installEventFilter(self)
        if isinstance(widget, QPushButton):
            widget.setCursor(Qt.PointingHandCursor)
        # The green install/play button has its own breathing glow.
        if widget.objectName() == "install":
            return
        effect = QGraphicsDropShadowEffect(widget)
        effect.setBlurRadius(5.0)
        effect.setOffset(0.0, 1.0)
        effect.setColor(QColor(66, 159, 213, 55))
        widget.setGraphicsEffect(effect)
        self._effects[key] = effect

    def _animate(self, widget: QWidget, target: float):
        effect = self._effects.get(id(widget))
        if effect is None:
            return
        old = self._animations.pop(id(widget), None)
        if old is not None:
            old.stop()
        animation = QPropertyAnimation(effect, b"blurRadius", self)
        animation.setDuration(170)
        animation.setStartValue(effect.blurRadius())
        animation.setEndValue(target)
        animation.setEasingCurve(QEasingCurve.OutCubic)
        self._animations[id(widget)] = animation
        animation.start()

    def eventFilter(self, watched, event):
        if isinstance(watched, (QPushButton, QCheckBox)):
            if event.type() in (QEvent.Enter, QEvent.FocusIn):
                self._animate(watched, 26.0)
            elif event.type() in (QEvent.Leave, QEvent.FocusOut):
                self._animate(watched, 5.0)
        return False


class Launcher(previous.Launcher):
    """app_v12 functionality with a presentation-only v0.13 skin."""

    def __init__(self):
        # app_v10 constructs the desktop hero from its module-global class.
        # Replacing only that UI class before the inherited build gives us the
        # cinematic painter while preserving the entire artwork contract.
        previous.previous.previous.SteamHeroView = CinematicHero

        self._ui_motion: MotionDirector | None = None
        self._ambient_layer: AmbientMotionLayer | None = None
        self._accent_sweep: AccentSweep | None = None
        self._window_reveal: QPropertyAnimation | None = None
        self._card_effects: dict[int, QGraphicsOpacityEffect] = {}
        self._card_animations: list[QPropertyAnimation] = []
        self._play_glow_effect: QGraphicsDropShadowEffect | None = None
        self._play_glow_anim: QVariantAnimation | None = None

        super().__init__()
        self.setWindowTitle(f"Drowned Launcher {APP_VERSION} • Steam Motion UI")
        self.resize(max(self.width(), 1440), max(self.height(), 860))
        self._install_presentation_layer()

    def _install_presentation_layer(self):
        QApplication.instance().setStyleSheet(PREMIUM_STEAM_STYLE)

        central = self.centralWidget()
        if central is not None:
            self._ambient_layer = AmbientMotionLayer(central)
            self._ambient_layer.setGeometry(central.rect())
            self._ambient_layer.raise_()

            self._accent_sweep = AccentSweep(central)
            self._accent_sweep.setGeometry(0, 0, central.width(), 3)
            self._accent_sweep.raise_()

        self._ui_motion = MotionDirector(self)
        self._ui_motion.watch_all(self)

        # When a game selection rebuilds add-on checkboxes, discover the new
        # UI controls a moment later. This observes presentation only.
        if hasattr(self, "library"):
            self.library.currentRowChanged.connect(self._selection_motion)

        self._setup_play_button_glow()
        self._add_static_card_shadows()

        # A short initial card cascade makes the shell feel assembled rather
        # than simply appearing. No geometry is changed.
        QTimer.singleShot(80, self._animate_content_cards)

    def _setup_play_button_glow(self):
        button = getattr(self, "install_button", None)
        if button is None:
            return
        effect = QGraphicsDropShadowEffect(button)
        effect.setOffset(0.0, 3.0)
        effect.setBlurRadius(18.0)
        effect.setColor(QColor(123, 190, 42, 125))
        button.setGraphicsEffect(effect)
        self._play_glow_effect = effect

        animation = QVariantAnimation(self)
        animation.setStartValue(0.0)
        animation.setKeyValueAt(0.5, 1.0)
        animation.setEndValue(0.0)
        animation.setDuration(2600)
        animation.setLoopCount(-1)
        animation.setEasingCurve(QEasingCurve.InOutSine)

        def pulse(value):
            if self._play_glow_effect is None:
                return
            amount = float(value)
            self._play_glow_effect.setBlurRadius(15.0 + amount * 15.0)
            self._play_glow_effect.setColor(QColor(124, 194, 43, int(70 + amount * 80)))

        animation.valueChanged.connect(pulse)
        animation.start()
        self._play_glow_anim = animation

    def _add_static_card_shadows(self):
        # Only large structural cards get shadows; list/grid entries are left
        # untouched so scrolling stays inexpensive.
        candidates = []
        for name in ("addon_panel", "info_card"):
            widget = getattr(self, name, None)
            if isinstance(widget, QWidget):
                candidates.append(widget)
        for widget in candidates:
            if widget.graphicsEffect() is not None:
                continue
            shadow = QGraphicsDropShadowEffect(widget)
            shadow.setBlurRadius(30.0)
            shadow.setOffset(0.0, 8.0)
            shadow.setColor(QColor(0, 0, 0, 115))
            widget.setGraphicsEffect(shadow)

    def _opacity_effect(self, widget: QWidget) -> QGraphicsOpacityEffect | None:
        # Do not replace a shadow or another effect owned by the inherited UI.
        current = widget.graphicsEffect()
        if isinstance(current, QGraphicsOpacityEffect):
            return current
        if current is not None:
            return None
        key = id(widget)
        effect = self._card_effects.get(key)
        if effect is None:
            effect = QGraphicsOpacityEffect(widget)
            effect.setOpacity(1.0)
            widget.setGraphicsEffect(effect)
            self._card_effects[key] = effect
        return effect

    def _animate_content_cards(self):
        self._card_animations.clear()
        candidates = []
        # These are all pre-existing presentation widgets. No action widget is
        # reparented and no layout position changes.
        for name in ("addon_panel", "logs"):
            widget = getattr(self, name, None)
            if isinstance(widget, QWidget) and widget.isVisible():
                candidates.append(widget)

        for index, widget in enumerate(candidates):
            effect = self._opacity_effect(widget)
            if effect is None:
                continue
            effect.setOpacity(0.22)
            animation = QPropertyAnimation(effect, b"opacity", self)
            animation.setDuration(300 + index * 70)
            animation.setStartValue(0.22)
            animation.setEndValue(1.0)
            animation.setEasingCurve(QEasingCurve.OutCubic)
            self._card_animations.append(animation)
            QTimer.singleShot(index * 45, animation.start)

    def _selection_motion(self, row: int):
        del row
        # app_v12 has already processed the selection through its own signal
        # chain. This delayed callback only animates whatever it rendered.
        QTimer.singleShot(35, self._after_selection_render)

    def _after_selection_render(self):
        if self._ui_motion is not None:
            self._ui_motion.watch_all(self)
        self._animate_content_cards()

    def showEvent(self, event):
        super().showEvent(event)
        if self._window_reveal is None:
            self.setWindowOpacity(0.0)
            animation = QPropertyAnimation(self, b"windowOpacity", self)
            animation.setDuration(520)
            animation.setStartValue(0.0)
            animation.setEndValue(1.0)
            animation.setEasingCurve(QEasingCurve.OutCubic)
            self._window_reveal = animation
            QTimer.singleShot(0, animation.start)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        central = self.centralWidget()
        if central is not None:
            if self._ambient_layer is not None:
                self._ambient_layer.setGeometry(central.rect())
                self._ambient_layer.raise_()
            if self._accent_sweep is not None:
                self._accent_sweep.setGeometry(0, 0, central.width(), 3)
                self._accent_sweep.raise_()


def main():
    previous.previous.previous.base.install_exception_hook()
    app = QApplication(sys.argv)
    app.setApplicationName("Drowned Launcher")
    app.setOrganizationName("Drowned")
    app.setStyle("Fusion")
    app.setStyleSheet(PREMIUM_STEAM_STYLE)

    splash = QSplashScreen(previous.previous.previous._splash_pixmap())
    splash.show()
    app.processEvents()

    win = Launcher()
    win.show()
    splash.finish(win)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
