from __future__ import annotations

import math
import sys

from PySide6.QtCore import QEasingCurve, QEvent, QObject, QPointF, QPropertyAnimation, Qt, QTimer, QVariantAnimation
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QRadialGradient
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QPushButton,
    QSplashScreen,
    QWidget,
)

import app_v12 as previous

APP_VERSION = "0.13.0"

# Presentation-only wrapper. app_v12 remains the functional implementation.
# No download/install/repair/add-on/catalog/settings/controller method is
# replaced in this module.

PREMIUM_STEAM_STYLE = previous.previous.previous.STEAM_STYLE + r"""
/* Drowned Launcher v0.13 — Steam-inspired premium presentation layer */
QWidget { font-family:"Segoe UI Variable","Segoe UI","Arial"; color:#d7e3ee; }
QMainWindow { background:#0c141d; }

QFrame#menubar {
    background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #0d151e,stop:.5 #15212d,stop:1 #0d151e);
}
QFrame#navbar {
    background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #101923,stop:.52 #182633,stop:1 #0f1821);
    border-bottom:1px solid #294158;
}
QLabel#navActive {
    color:#fff; font-weight:800; padding:13px 15px 10px 15px;
    border-bottom:3px solid #66c0f4; background:rgba(102,192,244,9);
}
QLabel#nav { color:#899aa9; font-weight:700; padding:13px 15px; }
QLabel#nav:hover { color:#fff; background:rgba(102,192,244,7); }
QLabel#menuItem { color:#8c9aa7; }
QLabel#menuItem:hover { color:#fff; }

QFrame#sidebar {
    background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #101923,stop:.9 #152432,stop:1 #172838);
    border-right:1px solid #294158;
}
QLabel#sectionLabel { color:#617a90; font-size:10px; font-weight:850; letter-spacing:2px; }
QListWidget { background:transparent; border:0; outline:0; padding:5px 0; }
QListWidget::item {
    color:#adbdca; padding:8px 10px; margin:1px 4px; border-radius:5px;
    border-left:3px solid transparent;
}
QListWidget::item:hover { color:#fff; background:rgba(57,91,119,100); border-left-color:#3d6c93; }
QListWidget::item:selected {
    color:#fff;
    background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 rgba(53,94,128,220),stop:1 rgba(28,52,72,155));
    border-left:3px solid #66c0f4;
}

QFrame#detail {
    background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #14212d,stop:.35 #111b26,stop:1 #0c141d);
}
QFrame#actionBar {
    background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 rgba(17,30,42,245),stop:.55 rgba(24,41,56,245),stop:1 rgba(14,25,35,245));
    border-top:1px solid #2d465e; border-bottom:1px solid #090f15;
}
QFrame#panel {
    background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 rgba(25,42,58,242),stop:1 rgba(16,29,41,242));
    border:1px solid #2b455d; border-radius:9px;
}
QFrame#panel:hover { border-color:#416b8d; }
QFrame#infoCard { background:transparent; border:0; }
QFrame#hairline { background:#29455d; }

QLabel#gameTitle { color:#fff; font-size:30px; font-weight:850; }
QLabel#metaLine { color:#69c7fb; font-weight:700; }
QLabel#description { color:#afbecb; }
QLabel#panelTitle { color:#86a0b7; font-size:10px; font-weight:850; letter-spacing:2px; }
QLabel#statName { color:#60798f; font-weight:850; }
QLabel#statValue { color:#e5eef6; font-weight:750; }
QLabel#rowKey { color:#6a8298; }
QLabel#rowValue { color:#d7e4ef; font-weight:650; }
QLabel#muted { color:#71899d; }
QLabel#connectionOnline {
    color:#a7df6b; background:rgba(73,118,38,35); border:1px solid rgba(126,185,45,90);
    border-radius:10px; padding:4px 8px;
}

QLineEdit,QComboBox {
    min-height:20px; background:rgba(6,12,18,210); border:1px solid #294158; border-radius:7px;
    padding:7px 10px; color:#dce9f4; selection-background-color:#2e709f;
}
QLineEdit:hover,QComboBox:hover { border-color:#3f6484; }
QLineEdit:focus,QComboBox:focus { border-color:#69c7fb; background:rgba(8,16,24,238); }
QComboBox QAbstractItemView { background:#101c28; color:#dbe8f2; border:1px solid #365673; selection-background-color:#2b506d; }

QPushButton {
    min-height:21px; padding:8px 16px; border-radius:7px; font-weight:750;
    color:#d7e5f0; border:1px solid #41627f;
    background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #355069,stop:1 #23394d);
}
QPushButton:hover {
    color:#fff; border-color:#69aadb;
    background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #4b7da3,stop:1 #315d7e);
}
QPushButton:pressed { background:#203a50; }
QPushButton:disabled { color:#526474; background:#151f29; border-color:#263645; }
QPushButton#install {
    min-height:28px; padding:10px 32px; font-size:15px; font-weight:850; color:#f4ffe8;
    border:1px solid #91ce39; border-radius:8px;
    background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #5a9417,stop:.52 #75b022,stop:1 #4e8312);
}
QPushButton#install:hover {
    border-color:#adeb52;
    background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #70ad20,stop:.52 #8bc53f,stop:1 #63a016);
}
QPushButton#secondary { border-color:#3c5972; background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #314b62,stop:1 #22384b); }
QPushButton#danger { color:#efbdc4; border-color:#703b46; background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #49262e,stop:1 #321c22); }
QPushButton#danger:hover { color:#ffe3e7; border-color:#a05565; background:#562932; }
QPushButton#iconButton { min-width:32px; max-width:32px; min-height:32px; max-height:32px; padding:0; border-radius:7px; }
QPushButton#linkButton { background:transparent; border:0; color:#69c7fb; }
QPushButton#linkButton:hover { color:#fff; background:rgba(102,192,244,10); }

QCheckBox { spacing:10px; color:#d9e6ef; font-weight:700; padding:3px 2px; }
QCheckBox:disabled { color:#65788a; }
QCheckBox::indicator { width:18px; height:18px; border-radius:4px; border:1px solid #46657f; background:#0b151f; }
QCheckBox::indicator:hover { border-color:#6bcaff; background:#13283a; }
QCheckBox::indicator:checked {
    border:1px solid #8dd8ff;
    background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #69c7fb,stop:1 #2b79a9);
}

QLabel#tabActive { color:#fff; font-weight:800; padding:11px 17px 9px 17px; border-bottom:3px solid #69c7fb; background:rgba(102,192,244,8); }
QLabel#tab { color:#8399ab; font-weight:750; padding:11px 17px 9px 17px; border-bottom:3px solid transparent; }
QLabel#tab:hover { color:#fff; background:rgba(102,192,244,6); }

QProgressBar { min-height:7px; max-height:7px; background:#070d13; border:1px solid #192a39; border-radius:3px; color:transparent; }
QProgressBar::chunk { border-radius:3px; background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #2f86ba,stop:.52 #69c7fb,stop:1 #92dfff); }
QProgressBar#fatBar { min-height:11px; max-height:11px; }
QPlainTextEdit { background:rgba(5,10,16,225); border:1px solid #263c51; border-radius:7px; color:#90a9bd; padding:8px 10px; }

QFrame#statusbar,QFrame#downloadBar {
    background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #0c141d,stop:.5 #111d28,stop:1 #0b131c);
    border-top:1px solid #294158;
}
QFrame#downloadCard { background:rgba(20,35,48,175); border:1px solid rgba(62,99,128,95); border-radius:7px; }
QLabel#progressText { color:#77cffd; font-weight:700; }

QScrollBar:vertical { background:#0c1620; width:10px; margin:1px; }
QScrollBar::handle:vertical { background:#2b4963; min-height:32px; border-radius:4px; }
QScrollBar::handle:vertical:hover { background:#3d6b8e; }
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical { height:0; }
QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical { background:transparent; }
QScrollBar:horizontal { background:#0c1620; height:10px; }
QScrollBar::handle:horizontal { background:#2b4963; min-width:32px; border-radius:4px; }
QScrollBar::add-line:horizontal,QScrollBar::sub-line:horizontal { width:0; }
QScrollBar::add-page:horizontal,QScrollBar::sub-page:horizontal { background:transparent; }
QSplitter::handle { background:#294158; width:1px; }

QWidget#bigPictureRoot { background:qradialgradient(cx:.5,cy:.16,radius:1.08,stop:0 #213b50,stop:.48 #12202c,stop:1 #081018); }
QFrame#bpHeader { background:rgba(9,16,23,160); border-bottom:1px solid rgba(78,119,150,90); }
QLineEdit#bpSearch { background:rgba(24,39,52,228); border:1px solid #4d6f8b; border-radius:18px; padding:10px 17px; color:#fff; }
QLineEdit#bpSearch:focus { border-color:#72ccfc; background:rgba(31,50,67,245); }
QLabel#bpTabActive { color:#fff; border:1px solid #527a99; border-radius:18px; padding:9px 21px; background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #355d7b,stop:1 #294b66); }
QLabel#bpTab { color:#a6b7c6; padding:9px 21px; }
QLabel#bpTab:hover { color:#fff; background:rgba(70,106,134,85); border-radius:18px; }
QLabel#bpShoulder { color:#dceaf4; background:rgba(48,71,91,210); border:1px solid #5a7891; border-radius:6px; }
QFrame#bpFooter { background:rgba(5,10,15,240); border-top:1px solid #29445b; }
"""


class CinematicHero(previous.previous.previous.SteamHeroView):
    """Existing hero plus a translucent cinematic light sweep."""

    def __init__(self):
        super().__init__()
        self._cinema_phase = 0.0
        self._cinema = QVariantAnimation(self)
        self._cinema.setStartValue(0.0)
        self._cinema.setEndValue(1.0)
        self._cinema.setDuration(9000)
        self._cinema.setLoopCount(-1)
        self._cinema.setEasingCurve(QEasingCurve.InOutSine)
        self._cinema.valueChanged.connect(self._set_phase)
        self._cinema.start()

    def _set_phase(self, value):
        self._cinema_phase = float(value)
        if self.isVisible():
            self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.width() <= 0 or self.height() <= 0:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        x = (-0.35 + self._cinema_phase * 1.7) * self.width()
        beam = QLinearGradient(x - self.width() * .22, 0, x + self.width() * .22, 0)
        beam.setColorAt(0.0, QColor(102, 192, 244, 0))
        beam.setColorAt(.48, QColor(126, 211, 255, 5))
        beam.setColorAt(.50, QColor(170, 229, 255, 18))
        beam.setColorAt(.52, QColor(126, 211, 255, 5))
        beam.setColorAt(1.0, QColor(102, 192, 244, 0))
        painter.fillRect(self.rect(), beam)
        glow = QRadialGradient(QPointF(self.width() * .82, self.height() * .12), max(self.width(), self.height()) * .48)
        glow.setColorAt(0.0, QColor(102, 192, 244, 20))
        glow.setColorAt(.4, QColor(66, 145, 194, 7))
        glow.setColorAt(1.0, QColor(30, 73, 105, 0))
        painter.fillRect(self.rect(), QBrush(glow))
        painter.end()


class AmbientMotionLayer(QWidget):
    """Mouse-transparent atmospheric motion over the existing shell."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def _tick(self):
        self._phase = (self._phase + .0065) % 1.0
        if self.isVisible():
            self.update()

    def paintEvent(self, event):
        if self.width() < 2 or self.height() < 2:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = float(self.width()), float(self.height())
        t = self._phase * math.tau
        for px, py, rf, alpha in (
            (.72 + math.sin(t * .63) * .08, .18 + math.cos(t * .47) * .05, .42, 16),
            (.34 + math.cos(t * .38) * .10, .70 + math.sin(t * .52) * .07, .36, 9),
        ):
            radius = max(w, h) * rf
            grad = QRadialGradient(QPointF(w * px, h * py), radius)
            grad.setColorAt(0.0, QColor(74, 169, 223, alpha))
            grad.setColorAt(.42, QColor(42, 112, 158, max(2, alpha // 3)))
            grad.setColorAt(1.0, QColor(18, 52, 77, 0))
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(grad))
            painter.drawEllipse(QPointF(w * px, h * py), radius, radius)
        for i in range(18):
            seed = i * .61803398875
            x = ((seed + self._phase * (.05 + (i % 4) * .012)) % 1.0) * w
            y = ((i * .173) % 1.0) * h + math.sin(t * (.35 + i * .012) + i) * 18.0
            painter.setBrush(QColor(111, 203, 250, 8 + (i % 5) * 3))
            painter.drawEllipse(QPointF(x, y), .8 + (i % 3) * .55, .8 + (i % 3) * .55)
        painter.end()


class AccentSweep(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(3)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self._phase = 0.0
        self._anim = QVariantAnimation(self)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setDuration(5200)
        self._anim.setLoopCount(-1)
        self._anim.valueChanged.connect(self._set_phase)
        self._anim.start()

    def _set_phase(self, value):
        self._phase = float(value)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        w = max(1, self.width())
        center = (-.20 + self._phase * 1.40) * w
        grad = QLinearGradient(center - 190, 0, center + 190, 0)
        grad.setColorAt(0.0, QColor(69, 151, 201, 0))
        grad.setColorAt(.5, QColor(132, 218, 255, 175))
        grad.setColorAt(1.0, QColor(69, 151, 201, 0))
        painter.fillRect(self.rect(), grad)
        painter.end()


class MotionDirector(QObject):
    """Hover/focus shadows only; action wiring is untouched."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._watched: set[int] = set()
        self._effects: dict[int, QGraphicsDropShadowEffect] = {}
        self._animations: dict[int, QPropertyAnimation] = {}

    def watch_all(self, root: QWidget):
        for cls in (QPushButton, QCheckBox):
            for widget in root.findChildren(cls):
                self.watch(widget)

    def watch(self, widget: QWidget):
        key = id(widget)
        if key in self._watched:
            return
        self._watched.add(key)
        widget.installEventFilter(self)
        if isinstance(widget, QPushButton):
            widget.setCursor(Qt.PointingHandCursor)
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
        anim = QPropertyAnimation(effect, b"blurRadius", self)
        anim.setDuration(170)
        anim.setStartValue(effect.blurRadius())
        anim.setEndValue(target)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        self._animations[id(widget)] = anim
        anim.start()

    def eventFilter(self, watched, event):
        if isinstance(watched, (QPushButton, QCheckBox)):
            if event.type() in (QEvent.Type.Enter, QEvent.Type.FocusIn):
                self._animate(watched, 26.0)
            elif event.type() in (QEvent.Type.Leave, QEvent.Type.FocusOut):
                self._animate(watched, 5.0)
        return False


class Launcher(previous.Launcher):
    """app_v12 unchanged underneath a premium animated presentation layer."""

    def __init__(self):
        previous.previous.previous.SteamHeroView = CinematicHero
        self._motion = None
        self._ambient = None
        self._accent = None
        self._window_anim = None
        self._play_effect = None
        self._play_anim = None
        self._fade_effects = {}
        self._fade_anims = []
        super().__init__()
        self.setWindowTitle(f"Drowned Launcher {APP_VERSION} • Steam Motion UI")
        self.resize(max(self.width(), 1440), max(self.height(), 860))
        self._install_presentation()

    def _install_presentation(self):
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(PREMIUM_STEAM_STYLE)
        central = self.centralWidget()
        if central is not None:
            self._ambient = AmbientMotionLayer(central)
            self._ambient.setGeometry(central.rect())
            self._ambient.raise_()
            self._accent = AccentSweep(central)
            self._accent.setGeometry(0, 0, central.width(), 3)
            self._accent.raise_()
        self._motion = MotionDirector(self)
        self._motion.watch_all(self)
        if hasattr(self, "library"):
            self.library.currentRowChanged.connect(self._selection_motion)
        self._setup_play_glow()
        QTimer.singleShot(90, self._animate_cards)

    def _setup_play_glow(self):
        button = getattr(self, "install_button", None)
        if button is None:
            return
        effect = QGraphicsDropShadowEffect(button)
        effect.setOffset(0.0, 3.0)
        effect.setBlurRadius(18.0)
        effect.setColor(QColor(123, 190, 42, 120))
        button.setGraphicsEffect(effect)
        self._play_effect = effect
        anim = QVariantAnimation(self)
        anim.setStartValue(0.0)
        anim.setKeyValueAt(.5, 1.0)
        anim.setEndValue(0.0)
        anim.setDuration(2600)
        anim.setLoopCount(-1)
        anim.setEasingCurve(QEasingCurve.InOutSine)
        anim.valueChanged.connect(self._pulse_play)
        anim.start()
        self._play_anim = anim

    def _pulse_play(self, value):
        if self._play_effect is None:
            return
        amount = float(value)
        self._play_effect.setBlurRadius(15.0 + amount * 15.0)
        self._play_effect.setColor(QColor(124, 194, 43, int(68 + amount * 82)))

    def _fade_effect(self, widget):
        current = widget.graphicsEffect()
        if isinstance(current, QGraphicsOpacityEffect):
            return current
        if current is not None:
            return None
        key = id(widget)
        effect = self._fade_effects.get(key)
        if effect is None:
            effect = QGraphicsOpacityEffect(widget)
            widget.setGraphicsEffect(effect)
            self._fade_effects[key] = effect
        return effect

    def _animate_cards(self):
        self._fade_anims.clear()
        for index, name in enumerate(("addon_panel", "logs")):
            widget = getattr(self, name, None)
            if not isinstance(widget, QWidget) or not widget.isVisible():
                continue
            effect = self._fade_effect(widget)
            if effect is None:
                continue
            effect.setOpacity(.25)
            anim = QPropertyAnimation(effect, b"opacity", self)
            anim.setDuration(300 + index * 80)
            anim.setStartValue(.25)
            anim.setEndValue(1.0)
            anim.setEasingCurve(QEasingCurve.OutCubic)
            self._fade_anims.append(anim)
            QTimer.singleShot(index * 45, anim.start)

    def _selection_motion(self, row):
        del row
        QTimer.singleShot(40, self._after_selection)

    def _after_selection(self):
        if self._motion is not None:
            self._motion.watch_all(self)
        self._animate_cards()

    def showEvent(self, event):
        super().showEvent(event)
        if self._window_anim is None:
            self.setWindowOpacity(0.0)
            anim = QPropertyAnimation(self, b"windowOpacity", self)
            anim.setDuration(520)
            anim.setStartValue(0.0)
            anim.setEndValue(1.0)
            anim.setEasingCurve(QEasingCurve.OutCubic)
            self._window_anim = anim
            QTimer.singleShot(0, anim.start)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        central = self.centralWidget()
        if central is None:
            return
        if self._ambient is not None:
            self._ambient.setGeometry(central.rect())
            self._ambient.raise_()
        if self._accent is not None:
            self._accent.setGeometry(0, 0, central.width(), 3)
            self._accent.raise_()


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
