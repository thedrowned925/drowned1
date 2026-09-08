"""Native desktop presentation widgets. No storage or network access."""
from __future__ import annotations

from collections import deque

from PySide6.QtCore import QEasingCurve, QRectF, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QFrame, QGraphicsOpacityEffect, QStackedWidget, QPushButton


STYLE = r"""
QWidget { color:#dce3ed; font-family:'Segoe UI'; font-size:13px; }
QMainWindow, QDialog, QWidget#steamRoot { background:#171d25; }
QFrame#steamHeader { background:#171d25; border-bottom:1px solid #303946; }
QLabel#brand { color:#edf4fc; font-size:19px; font-weight:800; letter-spacing:3px; }
QLabel#brandMark { background:#66c0f4; color:#142436; border-radius:6px; font-size:24px; font-weight:900; }
QLabel#eyebrow, QLabel#sectionLabel, QLabel#statName { color:#8696a9; font-size:10px; font-weight:700; letter-spacing:1px; }
QLabel#heading { color:#f4f7fb; font-size:25px; font-weight:600; }
QLabel#gameTitle { color:#f4f7fb; font-size:28px; font-weight:700; }
QLabel#muted, QLabel#metaLine, QLabel#description { color:#a5b3c4; }
QLabel#description { font-size:14px; }
QLabel#panelTitle { color:#b9c7d8; font-size:11px; font-weight:700; letter-spacing:1px; }
QLabel#statValue, QLabel#rowValue { color:#e3edf8; font-size:15px; font-weight:600; }
QLabel#connectionOnline { color:#8fb5cb; font-size:11px; }
QFrame#steamSidebar { background:#202630; border-right:1px solid #303947; }
QFrame#steamBody, QWidget#steamBody { background:#1b2330; }
QFrame#actionBar { background:#242f3e; border-top:1px solid #38495d; border-bottom:1px solid #17202d; }
QFrame#panel { background:#202b3a; border:1px solid #324052; border-radius:4px; }
QFrame#statusRail { background:#171d25; border-top:1px solid #303b4b; }
QFrame#hairline { background:#344154; border:0; }
QLabel { background:transparent; }
QPushButton { background:#303c4d; color:#d7e3f2; padding:9px 14px; border:1px solid transparent; border-radius:3px; }
QPushButton:hover { background:#41556d; color:white; }
QPushButton:pressed { background:#1b2d42; }
QPushButton:focus { border:1px solid #66c0f4; }
QPushButton:disabled { background:#252d38; color:#657184; }
QPushButton#nav, QPushButton#navActive { background:transparent; padding:18px 12px; font-size:15px; font-weight:700; border-radius:0; }
QPushButton#nav { color:#9daabd; border-bottom:3px solid transparent; }
QPushButton#navActive { color:#66c0f4; border-bottom:3px solid #66c0f4; }
QPushButton#nav:hover { color:#fff; }
QPushButton#quiet { background:transparent; color:#94a8bd; }
QPushButton#quiet:hover { color:white; background:#2f3a4a; }
QPushButton#tab, QPushButton#tabActive { border-radius:3px; padding:7px 12px; }
QPushButton#tab { background:transparent; color:#95a7bb; }
QPushButton#tabActive { background:#34465b; color:#e8f2ff; }
QPushButton#install, QPushButton#play { background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #6fa51e,stop:1 #91bf32); color:white; font-size:16px; font-weight:700; min-width:112px; padding:12px 20px; }
QPushButton#install:hover, QPushButton#play:hover { background:#9bce3b; }
QPushButton#install:disabled, QPushButton#play:disabled { background:#314333; color:#82957c; }
QPushButton#danger { background:#3a2d38; color:#d9a7ae; }
QPushButton#danger:hover { background:#603540; color:white; }
QPushButton#danger:disabled { background:#282a33; color:#706775; }
QPushButton#pauseButton { background:#31577a; color:#deefff; }
QLineEdit, QComboBox, QPlainTextEdit { background:#151c25; border:1px solid #344050; border-radius:3px; padding:8px; selection-background-color:#386b91; }
QLineEdit:focus, QComboBox:focus { border-color:#66c0f4; }
QComboBox::drop-down { border:0; width:18px; }
QComboBox QAbstractItemView { background:#202b3a; color:#e1ecf9; selection-background-color:#375575; }
QListWidget { background:transparent; border:0; outline:0; }
QListWidget::item { padding:8px; border-radius:3px; }
QListWidget::item:selected { background:#385773; color:white; }
QListWidget::item:hover { background:#2d3b4e; }
QScrollArea { background:transparent; border:0; }
QWidget#gameListContent, QWidget#gameGridContent { background:#202630; }
QWidget#completedContent { background:#1b2330; }
QScrollBar:vertical { background:transparent; width:7px; margin:2px; }
QScrollBar::handle:vertical { background:#465369; min-height:28px; border-radius:2px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background:transparent; }
QScrollBar:horizontal { background:transparent; height:7px; }
QScrollBar::handle:horizontal { background:#465369; min-width:28px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width:0; }
QProgressBar { background:#111b26; border:0; border-radius:2px; min-height:5px; max-height:5px; }
QProgressBar::chunk { background:#66c0f4; border-radius:2px; }
QProgressBar#fatBar { min-height:10px; max-height:10px; }
QToolTip { background:#344b64; color:white; border:1px solid #607e9e; padding:6px; }
QCheckBox { spacing:9px; padding:4px; }
QCheckBox::indicator { width:17px; height:17px; border:1px solid #60748e; background:#172230; border-radius:3px; }
QCheckBox::indicator:checked { background:#66c0f4; border:3px solid #315978; }
"""


def cover_crop(painter: QPainter, rect: QRectF, pixmap: QPixmap, zoom: float = 1.0):
    if pixmap.isNull() or rect.isEmpty():
        return
    scale = max(rect.width() / pixmap.width(), rect.height() / pixmap.height()) * zoom
    width, height = rect.width() / scale, rect.height() / scale
    source = QRectF((pixmap.width() - width) / 2, (pixmap.height() - height) / 2, width, height)
    painter.drawPixmap(rect, pixmap, source)


class MotionButton(QPushButton):
    """A subtle animated highlight that leaves native keyboard/button semantics intact."""
    def __init__(self, text='', parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.PointingHandCursor)
        self._glow = 0.0
        self.motion_enabled = True
        self._motion = QVariantAnimation(self)
        self._motion.setDuration(150)
        self._motion.setEasingCurve(QEasingCurve.OutCubic)
        self._motion.valueChanged.connect(self._frame)

    def _frame(self, value):
        self._glow = float(value)
        self.update()

    def _hover(self, value):
        self._motion.stop()
        if not self.motion_enabled:
            self._frame(value)
            return
        self._motion.setStartValue(self._glow)
        self._motion.setEndValue(value)
        self._motion.start()

    def enterEvent(self, event):
        self._hover(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover(0.0)
        super().leaveEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.isEnabled() and self._glow:
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(130, 195, 245, int(self._glow * 18)))
            p.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 3, 3)


class FadeStack(QStackedWidget):
    """Single, interruptible page transition; never stack effects on live children."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.motion_enabled = True
        self._effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._effect)
        self._effect.setOpacity(1)
        self._fade = QVariantAnimation(self)
        self._fade.setDuration(180)
        self._fade.setEasingCurve(QEasingCurve.OutCubic)
        self._fade.valueChanged.connect(self._effect.setOpacity)

    def setCurrentIndex(self, index):
        if index == self.currentIndex() or index < 0 or index >= self.count():
            return
        self._fade.stop()
        super().setCurrentIndex(index)
        if self.motion_enabled and self.isVisible():
            self._fade.setStartValue(0.65)
            self._fade.setEndValue(1.0)
            self._fade.start()
        else:
            self._effect.setOpacity(1)


class SteamHero(QFrame):
    """Artwork-aware native hero with bounded, visibility-aware camera motion."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.hero = QPixmap()
        self.logo = QPixmap()
        self._title = 'DROWNED'
        self._phase = 0.0
        self.motion_enabled = True
        self.setMinimumHeight(260)
        self.setMaximumHeight(340)
        self._camera = QVariantAnimation(self)
        self._camera.setStartValue(0.0)
        self._camera.setEndValue(1.0)
        self._camera.setDuration(22000)
        self._camera.setLoopCount(-1)
        self._camera.valueChanged.connect(self._frame)

    def _frame(self, value):
        self._phase = float(value)
        self.update()

    def set_art(self, hero, logo, title):
        self.hero = hero if hero is not None else QPixmap()
        self.logo = logo if logo is not None else QPixmap()
        self._title = title
        self._update_motion()
        self.update()

    def set_hero(self, hero):
        self.set_art(hero, None, self._title)

    def _update_motion(self):
        if self.motion_enabled and self.isVisible() and not self.hero.isNull():
            if self._camera.state() != QVariantAnimation.Running:
                self._camera.start()
        else:
            self._camera.stop()

    def showEvent(self, event):
        super().showEvent(event)
        self._update_motion()

    def hideEvent(self, event):
        self._camera.stop()
        super().hideEvent(event)

    def paintEvent(self, event):
        import math
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        rect = QRectF(self.rect())
        background = QLinearGradient(rect.topLeft(), rect.bottomRight())
        background.setColorAt(0, QColor('#304c68'))
        background.setColorAt(1, QColor('#18212e'))
        p.fillRect(rect, background)
        if not self.hero.isNull():
            zoom = 1.015 + .015 * math.sin(self._phase * 2 * math.pi)
            cover_crop(p, rect, self.hero, zoom if self.motion_enabled else 1)
        else:
            p.setPen(QPen(QColor(110, 168, 214, 18), 1))
            for offset in range(-self.height(), self.width(), 42):
                p.drawLine(offset, self.height(), offset + self.height(), 0)
        shade = QLinearGradient(0, 0, self.width(), 0)
        shade.setColorAt(0, QColor(12, 20, 30, 220))
        shade.setColorAt(.6, QColor(12, 20, 30, 45))
        shade.setColorAt(1, QColor(12, 20, 30, 5))
        p.fillRect(rect, shade)
        bottom = QLinearGradient(0, 0, 0, self.height())
        bottom.setColorAt(0, QColor(27, 35, 48, 0))
        bottom.setColorAt(.55, QColor(27, 35, 48, 15))
        bottom.setColorAt(1, QColor(27, 35, 48, 245))
        p.fillRect(rect, bottom)
        p.setPen(QColor('#9dbad1'))
        p.setFont(QFont('Segoe UI', 9, QFont.DemiBold))
        p.drawText(QRectF(30, self.height() - 143, self.width() - 60, 22), 'KÜTÜPHANENDEN')
        if not self.logo.isNull():
            target = self.logo.size().scaled(min(360, self.width() - 60), 100, Qt.KeepAspectRatio)
            p.drawPixmap(30, self.height() - target.height() - 25, target.width(), target.height(), self.logo)
        else:
            p.setPen(QColor('#f3f7ff'))
            p.setFont(QFont('Segoe UI', 29, QFont.Bold))
            p.drawText(QRectF(28, self.height() - 117, self.width() - 56, 96), Qt.TextWordWrap | Qt.AlignVCenter, self._title)


class LibraryCard(QFrame):
    activated = Signal(str)

    def __init__(self, key, title, parent=None):
        super().__init__(parent)
        self.key, self.title = key, title
        self.pixmap = QPixmap()
        self.installed = False
        self.percent = None
        self.selected = False
        self.motion_enabled = True
        self._lift = 0.0
        self.setFixedSize(166, 254)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAccessibleName(title)
        self.setToolTip(title)
        self._animation = QVariantAnimation(self)
        self._animation.setDuration(170)
        self._animation.setEasingCurve(QEasingCurve.OutCubic)
        self._animation.valueChanged.connect(self._frame)

    def _frame(self, value):
        self._lift = float(value)
        self.update()

    def _hover(self, value):
        self._animation.stop()
        if not self.motion_enabled:
            self._frame(value)
            return
        self._animation.setStartValue(self._lift)
        self._animation.setEndValue(value)
        self._animation.start()

    def enterEvent(self, event):
        self._hover(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover(0.0)
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.rect().contains(event.position().toPoint()):
            self.activated.emit(self.key)
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Enter, Qt.Key_Return, Qt.Key_Space):
            self.activated.emit(self.key)
        else:
            super().keyPressEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        art = QRectF(3, 5 - self._lift * 3, self.width() - 6, 205)
        p.fillRect(art.translated(0, 3), QColor(5, 10, 17, 120))
        p.fillRect(art, QColor('#293b50'))
        p.save()
        p.setClipRect(art)
        if not self.pixmap.isNull():
            cover_crop(p, art, self.pixmap, 1 + .025 * self._lift)
        else:
            p.setPen(QColor('#66839e'))
            p.setFont(QFont('Segoe UI', 34, QFont.Bold))
            p.drawText(art, Qt.AlignCenter, self.title[:1].upper())
        p.restore()
        if self.selected or self.hasFocus():
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor('#66c0f4'), 2))
            p.drawRect(art)
        if self.installed:
            p.fillRect(QRectF(art.left() + 8, art.top() + 9, 51, 19), QColor(15, 34, 26, 225))
            p.setPen(QColor('#b2d77e'))
            p.setFont(QFont('Segoe UI', 7, QFont.Bold))
            p.drawText(QRectF(art.left() + 8, art.top() + 9, 51, 19), Qt.AlignCenter, 'KURULU')
        if self.percent is not None:
            p.fillRect(QRectF(art.left(), art.bottom() - 4, art.width() * self.percent / 100, 4), QColor('#66c0f4'))
        p.setFont(QFont('Segoe UI', 10, QFont.DemiBold))
        p.setPen(QColor('#e1eaf6'))
        p.drawText(QRectF(3, 218, self.width()-6, 21), p.fontMetrics().elidedText(self.title, Qt.ElideRight, self.width()-6))
        p.setFont(QFont('Segoe UI', 8))
        p.setPen(QColor('#879bb1'))
        p.drawText(QRectF(3, 239, self.width()-6, 15), 'Oynamaya hazır' if self.installed else 'Kütüphanede')


class TransferGraph(QFrame):
    """Only real transfer samples; an idle graph never invents activity."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.samples = deque(maxlen=100)
        self.setMinimumHeight(100)
        self.setMaximumHeight(140)
        self.setAccessibleName('İndirme hızı grafiği')

    def add_sample(self, speed):
        self.samples.append(max(0, float(speed)))
        self.update()

    def clear(self):
        self.samples.clear()
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(12, 12, -12, -12)
        p.fillRect(self.rect(), QColor('#172230'))
        p.setPen(QPen(QColor('#29394c'), 1))
        for i in range(5):
            y = r.top() + r.height() * i / 4
            p.drawLine(r.left(), y, r.right(), y)
        if len(self.samples) < 2:
            p.setPen(QColor('#8195ab'))
            p.drawText(r, Qt.AlignCenter, 'İndirme başladığında hız grafiği burada görünür')
            return
        peak = max(max(self.samples), 1)
        path = QPainterPath()
        for index, value in enumerate(self.samples):
            x = r.left() + r.width() * index / (self.samples.maxlen - 1)
            y = r.bottom() - r.height() * value / peak
            if index == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)
        p.setPen(QPen(QColor('#66c0f4'), 2))
        p.drawPath(path)
        fill = QPainterPath(path)
        fill.lineTo(x, r.bottom())
        fill.lineTo(r.left(), r.bottom())
        fill.closeSubpath()
        p.fillPath(fill, QColor(65, 151, 213, 35))


# Keep the corrected keyboard/controller selection contract while limiting the
# legacy skeleton timers to visible rows. No global monkey-patching of v18.
from library_navigation import GameListView as _GameListView, GameGridView as _GameGridView


class _ViewportMotion:
    motion_enabled = True

    def set_items(self, rows):
        for key, game, _ in rows:
            item = self._items.get(key)
            url = str((game.get('artwork') or {}).get('cover') or '')
            if item is not None and item.cover_url != url:
                item.set_cover(None)
                item.cover_requested = False
        super().set_items(rows)

    def set_motion_enabled(self, enabled):
        self.motion_enabled = enabled
        self._sync_item_motion()

    def _sync_item_motion(self):
        viewport = self.viewport()
        for item in self._items.values():
            pos = item.mapTo(viewport, item.rect().topLeft())
            visible = self.isVisible() and pos.y() + item.height() >= 0 and pos.y() <= viewport.height()
            animate = self.motion_enabled and visible
            shimmer = item._shimmer_anim
            if animate and item._loading:
                if shimmer.state() != QVariantAnimation.Running:
                    shimmer.start()
            else:
                shimmer.stop()
            item._hover_anim.setDuration(110 if self.motion_enabled else 0)
            item._reveal_anim.setDuration(220 if animate else 0)
            if not animate:
                item._reveal_anim.stop()
                item._reveal = 1.0
                item.update()

    def _ensure_visible_covers(self):
        super()._ensure_visible_covers()
        self._sync_item_motion()

    def show_loading_skeleton(self, count=12):
        super().show_loading_skeleton(count)
        self._sync_item_motion()

    def showEvent(self, event):
        super().showEvent(event)
        self._sync_item_motion()

    def hideEvent(self, event):
        super().hideEvent(event)
        self._sync_item_motion()


class DesktopList(_ViewportMotion, _GameListView):
    pass


class ControllerGrid(_ViewportMotion, _GameGridView):
    pass
