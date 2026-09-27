"""Pages of the v0.19 Steam-style launcher: game page, downloads, store,
bottom bar, screenshot viewer and the launch-target picker.

Widgets the inherited backend writes to (hero, stat labels, dlp_* labels,
status/progress, action_dl_* ...) are created here and handed to the
Launcher, which exposes them under their historical attribute names.
"""

from __future__ import annotations

from collections import deque
from pathlib import Path

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QPointF,
    QRectF,
    QSize,
    Qt,
    QTimer,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QFontMetrics,
    QLinearGradient,
    QPainter,
    QPalette,
    QPen,
    QPixmap,
    QRadialGradient,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

import steam_theme as T
from steam_format import find_launch_candidates  # noqa: F401 - re-exported
from steam_theme import G
from steam_widgets import (
    ClickableFrame,
    DashLabel,
    GlyphLabel,
    ImageHub,
    SectionHeader,
    StatBlock,
    SteamActionButton,
    blurred_backdrop,
    clamp,
    cover_crop,
    device_ratio,
    elide,
    human_size,
    icon_button,
    make_label,
    paint_shimmer,
    placeholder_art,
    rounded_path,
)

# ---------------------------------------------------------------------------
# small widgets
# ---------------------------------------------------------------------------


class ElidingLabel(QLabel):
    """QLabel that elides instead of growing the layout; text() stays the
    full string the backend wrote."""

    def __init__(self, text: str = "", parent=None, mode=Qt.ElideRight):
        super().__init__(text, parent)
        self._mode = mode
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)

    def minimumSizeHint(self):  # noqa: N802 - Qt naming
        return QSize(24, super().minimumSizeHint().height())

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.TextAntialiasing)
        painter.setPen(self.palette().color(QPalette.WindowText))
        painter.setFont(self.font())
        metrics = QFontMetrics(self.font())
        text = metrics.elidedText(self.text(), self._mode, max(0, self.width()))
        painter.drawText(self.rect(), int(self.alignment()) | Qt.AlignVCenter, text)
        painter.end()


class PathLabel(ElidingLabel):
    """Install folder value: elided in the middle, full path on hover."""

    def __init__(self, text: str = "-", parent=None):
        super().__init__(text, parent, Qt.ElideMiddle)

    def setText(self, text):  # noqa: N802 - Qt naming
        value = str(text).replace("—", "-")
        super().setText(value)
        self.setToolTip(value if value not in ("", "-") else "")


class IconSquare(QWidget):
    """Status-bar game icon (set_icon contract from app_v10.IconLabel)."""

    def __init__(self, size: int = 24, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._source = QPixmap()
        self._scaled = QPixmap()

    def set_icon(self, pixmap):
        source = pixmap if pixmap is not None and not pixmap.isNull() else QPixmap()
        if source.cacheKey() == self._source.cacheKey():
            return
        self._source = source
        self._scaled = QPixmap()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        rect = QRectF(self.rect())
        painter.setClipPath(rounded_path(rect, 2))
        painter.fillRect(rect, QColor("#23262e"))
        if not self._source.isNull():
            if self._scaled.isNull():
                self._scaled = cover_crop(self._source, self.width(), self.height(), 0.5, 0.3, device_ratio(self))
            painter.drawPixmap(rect, self._scaled, QRectF(self._scaled.rect()))
        painter.end()


class PauseGlyphButton(QPushButton):
    """Blue square pause/resume button of the downloads page. app_v10 and
    app_v16 write "DURAKLAT"/"DEVAM ET" and "Ⅱ"/"▶" into it; those are
    mapped onto the matching icon glyph."""

    def __init__(self, parent=None):
        super().__init__(G.PAUSE_SOLID, parent)
        self.setObjectName("dlPause")
        self.setCursor(Qt.PointingHandCursor)
        self.set_paused(False)

    def setText(self, text):  # noqa: N802 - Qt naming
        value = str(text)
        if value in (G.PLAY, G.PLAY_SOLID, G.PAUSE, G.PAUSE_SOLID):
            super().setText(value)
            return
        self.set_paused(value in ("DEVAM ET", "▶"))

    def set_paused(self, paused: bool):
        super().setText(G.PLAY_SOLID if paused else G.PAUSE_SOLID)
        self.setToolTip("Devam et" if paused else "Duraklat")


class HeaderArt(QWidget):
    """Landscape capsule (hero crop) used by download rows and the store."""

    def __init__(self, width: int, height: int, parent=None):
        super().__init__(parent)
        self.setFixedSize(width, height)
        self._source = QPixmap()
        self._scaled = QPixmap()
        self._title = ""

    def set_art(self, pixmap, title: str = ""):
        source = pixmap if pixmap is not None and not pixmap.isNull() else QPixmap()
        if source.cacheKey() == self._source.cacheKey() and title == self._title:
            return
        self._source = source
        self._scaled = QPixmap()
        self._title = title
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        rect = QRectF(self.rect())
        if self._source.isNull():
            placeholder_art(painter, rect, self._title, self._title, 2)
        else:
            if self._scaled.isNull():
                self._scaled = cover_crop(self._source, self.width(), self.height(), 0.5, 0.35, device_ratio(self))
            painter.setClipPath(rounded_path(rect, 2))
            painter.drawPixmap(rect, self._scaled, QRectF(self._scaled.rect()))
        painter.end()


def _panel(title: str) -> tuple[QFrame, QVBoxLayout]:
    panel = QFrame()
    panel.setObjectName("steamPanel")
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(16, 14, 16, 14)
    layout.setSpacing(8)
    layout.addWidget(make_label(title.upper(), T.SECTION_TEXT, 12, 700, spacing=1.1))
    return panel, layout


def _panel_row(layout: QVBoxLayout, key: str, value: QLabel, wrap: bool = False):
    row = QHBoxLayout()
    row.setSpacing(12)
    key_label = QLabel(key)
    key_label.setObjectName("panelKey")
    value.setObjectName("panelValue")
    value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    value.setWordWrap(wrap)
    value.setTextInteractionFlags(Qt.TextSelectableByMouse)
    row.addWidget(key_label, 0, Qt.AlignTop)
    row.addWidget(value, 1)
    layout.addLayout(row)


# ---------------------------------------------------------------------------
# game page
# ---------------------------------------------------------------------------


class SteamHero(QFrame):
    """Library hero with the logo bottom-left and the collection tags
    top-right. Keeps app_v4's HeroView contract: set_art(hero, logo, title)
    plus the `hero`, `logo` and `fallback_title` attributes."""

    artChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.hero = QPixmap()
        self.logo = QPixmap()
        self.fallback_title = "DROWNED"
        self._tags: list[str] = []
        self._expect = None
        self._shown_for = None
        self._scaled = QPixmap()
        self._scaled_key = None
        self._reveal = 1.0
        self._reveal_anim = QVariantAnimation(self)
        self._reveal_anim.setDuration(360)
        self._reveal_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._reveal_anim.valueChanged.connect(self._on_reveal)
        self.setMinimumHeight(240)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(360)

    def expect(self, token):
        """Owner announces which game the next set_art belongs to, so a
        re-decoded copy of the art already on screen swaps in silently."""
        self._expect = token

    def set_art(self, hero, logo, title: str):
        new_hero = hero if hero is not None and not hero.isNull() else QPixmap()
        new_logo = logo if logo is not None and not logo.isNull() else QPixmap()
        silent = not self.hero.isNull() and self._shown_for is not None and self._shown_for == self._expect
        self.hero, self.logo = new_hero, new_logo
        self.fallback_title = title or "DROWNED"
        self._scaled_key = None
        if not new_hero.isNull():
            if not silent and T.animations_enabled():
                self._reveal_anim.stop()
                self._reveal_anim.setStartValue(0.0)
                self._reveal_anim.setEndValue(1.0)
                self._reveal_anim.start()
            else:
                self._reveal = 1.0
            self._shown_for = self._expect
        self.artChanged.emit()
        self.update()

    def set_tags(self, tags: list[str]):
        if tags != self._tags:
            self._tags = list(tags)
            self.update()

    def _on_reveal(self, value):
        self._reveal = float(value)
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        target = int(clamp(self.width() / 3.1, 250, 430))
        if target != self.height():
            self.setFixedHeight(target)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.setRenderHint(QPainter.TextAntialiasing)
        rect = QRectF(self.rect())
        w, h = self.width(), self.height()
        if not self.hero.isNull():
            ratio = device_ratio(self)
            key = (w, h, self.hero.cacheKey(), ratio)
            if key != self._scaled_key:
                self._scaled = cover_crop(self.hero, w, h, 0.5, 0.25, ratio)
                self._scaled_key = key
            painter.drawPixmap(rect, self._scaled, QRectF(self._scaled.rect()))
        else:
            gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
            gradient.setColorAt(0.0, QColor("#2b3240"))
            gradient.setColorAt(1.0, QColor("#15171c"))
            painter.fillRect(rect, gradient)

        shade = QLinearGradient(0, h * 0.5, 0, h)
        shade.setColorAt(0.0, QColor(0, 0, 0, 0))
        shade.setColorAt(1.0, QColor(0, 0, 0, 120))
        painter.fillRect(rect, shade)

        if not self.logo.isNull():
            max_w, max_h = w * 0.36, h * 0.52
            scale = min(max_w / max(1, self.logo.width()), max_h / max(1, self.logo.height()))
            lw, lh = self.logo.width() * scale, self.logo.height() * scale
            painter.drawPixmap(QRectF(w * 0.035, h - lh - h * 0.1, lw, lh), self.logo, QRectF(self.logo.rect()))
        else:
            font = T.ui_font(clamp(w / 26, 26, 46), 800, display=True)
            painter.setFont(font)
            text_rect = QRectF(w * 0.035, 0, w * 0.6, h - h * 0.1)
            painter.setPen(QColor(0, 0, 0, 150))
            painter.drawText(text_rect.translated(0, 2), Qt.AlignLeft | Qt.AlignBottom | Qt.TextWordWrap,
                             self.fallback_title)
            painter.setPen(QColor("#ffffff"))
            painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignBottom | Qt.TextWordWrap, self.fallback_title)

        if self._tags:
            font = T.ui_font(11, 700, spacing=0.6)
            metrics = QFontMetrics(font)
            painter.setFont(font)
            x = w - 14.0
            for tag in reversed(self._tags):
                tw = metrics.horizontalAdvance(tag) + 20
                pill = QRectF(x - tw, 14, tw, 24)
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(0, 0, 0, 150))
                painter.drawRoundedRect(pill, 2, 2)
                painter.setPen(QColor("#dcdedf"))
                painter.drawText(pill, Qt.AlignCenter, tag)
                x -= tw + 6

        if self._reveal < 1.0:
            base = QColor(T.PAGE_BASE)
            base.setAlpha(int((1.0 - self._reveal) * 255))
            painter.fillRect(rect, base)
        painter.end()


class _GameCanvas(QWidget):
    """Paints the blurred copy of the hero that tints the whole game page."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._backdrop = QPixmap()
        self._scaled = QPixmap()
        self._scaled_key = None

    def set_backdrop(self, pixmap: QPixmap):
        self._backdrop = pixmap if pixmap is not None else QPixmap()
        self._scaled_key = None
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(T.PAGE_BASE))
        depth = 980
        if not self._backdrop.isNull():
            key = (self.width(), depth)
            if key != self._scaled_key:
                self._scaled = self._backdrop.scaled(self.width(), depth, Qt.KeepAspectRatioByExpanding,
                                                     Qt.SmoothTransformation)
                self._scaled_key = key
            sx = max(0, (self._scaled.width() - self.width()) // 2)
            painter.drawPixmap(0, 0, self._scaled, sx, 0, self.width(), depth)
        base = QColor(T.PAGE_BASE)
        overlay = QLinearGradient(0, 0, 0, depth)
        for stop, alpha in ((0.0, 120), (0.35, 175), (0.7, 235), (1.0, 255)):
            color = QColor(base)
            color.setAlpha(alpha)
            overlay.setColorAt(stop, color)
        painter.fillRect(0, 0, self.width(), depth, overlay)
        painter.end()


class ControlBar(QFrame):
    """PLAY button, download readout, stats and the manage buttons."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(86)
        self.layout_ = QHBoxLayout(self)
        self.layout_.setContentsMargins(24, 0, 24, 0)
        self.layout_.setSpacing(22)
        self._stats: list[QWidget] = []
        self._fixed: list[QWidget] = []

    def add_fixed(self, widget: QWidget, stretch: int = 0):
        self._fixed.append(widget)
        self.layout_.addWidget(widget, stretch, Qt.AlignVCenter)

    def add_stat(self, widget: QWidget):
        self._stats.append(widget)
        self.layout_.addWidget(widget, 0, Qt.AlignVCenter)

    def add_stretch(self):
        self.layout_.addStretch(1)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(10, 12, 16, 72))
        painter.fillRect(0, 0, self.width(), 1, QColor(255, 255, 255, 10))
        painter.end()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fit_stats()

    def fit_stats(self):
        used = 48 + sum(w.sizeHint().width() + 22 for w in self._fixed if not w.isHidden())
        room = self.width() - used
        for stat in self._stats:
            need = stat.sizeHint().width() + 22
            fits = room >= need
            stat.setVisible(fits)
            if fits:
                room -= need


class SubNav(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(44)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(0)
        self.links: dict[str, QPushButton] = {}
        self._layout = layout

    def add_link(self, key: str, text: str) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName("subNavLink")
        button.setCursor(Qt.PointingHandCursor)
        self.links[key] = button
        self._layout.addWidget(button)
        return button

    def finish(self):
        self._layout.addStretch(1)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect().adjusted(24, 0, -24, 0), QColor(255, 255, 255, 13))
        painter.end()


class _ShotCanvas(QWidget):
    openRequested = Signal(int)
    THUMB_H = 150
    GAP = 10

    def __init__(self, images: ImageHub, parent=None):
        super().__init__(parent)
        self._images = images
        self._urls: list[str] = []
        self._thumbs: dict[int, QPixmap] = {}
        self._failed: set[int] = set()
        self._hover = -1
        self._shimmer_phase = 0.35
        self._anim = QVariantAnimation(self)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setDuration(1300)
        self._anim.setLoopCount(-1)
        self._anim.valueChanged.connect(self._tick)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WA_Hover, True)

    def thumb_w(self) -> int:
        return int(self.THUMB_H * 16 / 9)

    def set_urls(self, urls: list[str]):
        self._urls = list(urls)
        self._thumbs.clear()
        self._failed.clear()
        self._hover = -1
        width = len(self._urls) * (self.thumb_w() + self.GAP) - (self.GAP if self._urls else 0)
        self.setFixedSize(max(1, width), self.THUMB_H)
        if self._urls and T.animations_enabled():
            self._anim.start()
        else:
            self._anim.stop()
        self.update()

    def _tick(self, value):
        self._shimmer_phase = float(value)
        if len(self._thumbs) + len(self._failed) < len(self._urls):
            self.update()
        else:
            self._anim.stop()

    def _rect(self, index: int) -> QRectF:
        return QRectF(index * (self.thumb_w() + self.GAP), 0, self.thumb_w(), self.THUMB_H)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        ratio = device_ratio(self)
        for index, url in enumerate(self._urls):
            rect = self._rect(index)
            if not rect.intersects(QRectF(event.rect())):
                continue
            thumb = self._thumbs.get(index)
            if thumb is None:
                source = self._images.request("shot", url, lambda _u, _p, i=index: self.update(
                    self._rect(i).toAlignedRect()))
                if source is not None:
                    thumb = cover_crop(source, int(rect.width()), int(rect.height()), 0.5, 0.5, ratio)
                    self._thumbs[index] = thumb
            if thumb is None and self._images.failed("shot", url):
                self._failed.add(index)
            if thumb is None:
                if index in self._failed:
                    placeholder_art(painter, rect, "", url, 2)
                else:
                    paint_shimmer(painter, rect, self._shimmer_phase, 2)
                continue
            painter.save()
            painter.setClipPath(rounded_path(rect, 2))
            painter.drawPixmap(rect, thumb, QRectF(thumb.rect()))
            if index == self._hover:
                painter.fillRect(rect, QColor(255, 255, 255, 22))
            painter.restore()
            if index == self._hover:
                painter.setPen(QPen(QColor(255, 255, 255, 150), 1))
                painter.setBrush(Qt.NoBrush)
                painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), 2, 2)
        painter.end()

    def _index_at(self, pos) -> int:
        for index in range(len(self._urls)):
            if self._rect(index).contains(pos):
                return index
        return -1

    def mouseMoveEvent(self, event):
        index = self._index_at(event.position())
        if index != self._hover:
            self._hover = index
            self.setCursor(Qt.PointingHandCursor if index >= 0 else Qt.ArrowCursor)
            self.update()

    def event(self, event):
        if event.type() == QEvent.HoverLeave and self._hover != -1:
            self._hover = -1
            self.update()
        return super().event(event)

    def mousePressEvent(self, event):
        index = self._index_at(event.position())
        if index >= 0 and event.button() == Qt.LeftButton:
            self.openRequested.emit(index)


class ScreenshotStrip(QScrollArea):
    """Horizontal screenshot strip. Keeps app_v10's ScreenshotGallery API
    (set_urls / thumbRequested / set_thumb_pixmap) but loads through the
    shared ImageHub on worker threads."""

    thumbRequested = Signal(int, str)
    openRequested = Signal(int)
    countChanged = Signal(int)

    def __init__(self, images: ImageHub, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.NoFrame)
        self.setWidgetResizable(False)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFixedHeight(_ShotCanvas.THUMB_H)
        self.canvas = _ShotCanvas(images)
        self.canvas.openRequested.connect(self.openRequested)
        self.setWidget(self.canvas)
        self._urls: list[str] = []
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(380)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(lambda v: self.horizontalScrollBar().setValue(int(v)))

    def set_urls(self, urls):
        self._urls = [str(u) for u in (urls or []) if u]
        self.canvas.set_urls(self._urls)
        self.horizontalScrollBar().setValue(0)
        self.countChanged.emit(len(self._urls))

    def urls(self) -> list[str]:
        return list(self._urls)

    def set_thumb_pixmap(self, index: int, pixmap):
        pass

    def scroll_page(self, direction: int):
        bar = self.horizontalScrollBar()
        step = self.canvas.thumb_w() + self.canvas.GAP
        pages = max(1, self.viewport().width() // step)
        target = int(clamp(bar.value() + direction * pages * step, 0, bar.maximum()))
        if T.animations_enabled():
            self._anim.stop()
            self._anim.setStartValue(bar.value())
            self._anim.setEndValue(target)
            self._anim.start()
        else:
            bar.setValue(target)

    def wheelEvent(self, event):
        if abs(event.angleDelta().y()) > abs(event.angleDelta().x()):
            event.ignore()
            return
        super().wheelEvent(event)


class ScreenshotViewer(QWidget):
    """Full-window screenshot lightbox: arrows, wheel and keyboard to page,
    Esc or a click outside the image to close."""

    def __init__(self, images: ImageHub, parent: QWidget):
        super().__init__(parent)
        self._images = images
        self._urls: list[str] = []
        self._index = 0
        self._fade = 0.0
        self._hover = ""
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)
        self.hide()
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(160)
        self._anim.valueChanged.connect(self._on_fade)

    def is_open(self) -> bool:
        return self.isVisible()

    def open(self, urls: list[str], index: int):
        if not urls:
            return
        self._urls = list(urls)
        self._index = int(clamp(index, 0, len(urls) - 1))
        self.show()
        self.raise_()
        self.setFocus(Qt.OtherFocusReason)
        self._prefetch()
        if T.animations_enabled():
            self._anim.stop()
            self._anim.setStartValue(0.0)
            self._anim.setEndValue(1.0)
            self._anim.start()
        else:
            self._fade = 1.0
        self.update()

    def close_viewer(self):
        self.hide()
        parent = self.parentWidget()
        if parent is not None:
            parent.setFocus()

    def _on_fade(self, value):
        self._fade = float(value)
        self.update()

    def _prefetch(self):
        for offset in (0, 1, -1):
            index = self._index + offset
            if 0 <= index < len(self._urls):
                self._images.request("shot_full", self._urls[index], lambda _u, _p: self.update())

    def step(self, delta: int):
        if not self._urls:
            return
        self._index = (self._index + delta) % len(self._urls)
        self._prefetch()
        self.update()

    def _image_rect(self, pixmap: QPixmap) -> QRectF:
        area = QRectF(self.rect()).adjusted(96, 56, -96, -76)
        if pixmap is None or pixmap.isNull():
            return QRectF(area.center().x() - 320, area.center().y() - 180, 640, 360)
        scale = min(area.width() / pixmap.width(), area.height() / pixmap.height(), 1.0 * 2)
        w, h = pixmap.width() * scale, pixmap.height() * scale
        return QRectF(area.center().x() - w / 2, area.center().y() - h / 2, w, h)

    def _buttons(self) -> dict[str, QRectF]:
        cy = self.height() / 2
        return {
            "prev": QRectF(24, cy - 26, 52, 52),
            "next": QRectF(self.width() - 76, cy - 26, 52, 52),
            "close": QRectF(self.width() - 60, 16, 40, 40),
        }

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.setRenderHint(QPainter.TextAntialiasing)
        painter.fillRect(self.rect(), QColor(6, 8, 10, int(236 * self._fade)))
        if not self._urls:
            painter.end()
            return
        url = self._urls[self._index]
        pixmap = self._images.pixmap("shot_full", url) or self._images.pixmap("shot", url)
        painter.setOpacity(self._fade)
        target = self._image_rect(pixmap)
        if pixmap is not None:
            painter.drawPixmap(target, pixmap, QRectF(pixmap.rect()))
        else:
            paint_shimmer(painter, target, 0.4, 2)
        for name, rect in self._buttons().items():
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(255, 255, 255, 46 if self._hover == name else 22))
            painter.drawEllipse(rect)
            painter.setPen(QColor("#ffffff"))
            painter.setFont(T.icon_font(16 if name != "close" else 12))
            glyph = {"prev": G.CHEVRON_LEFT, "next": G.CHEVRON_RIGHT, "close": G.CLOSE}[name]
            painter.drawText(rect, Qt.AlignCenter, glyph)
        painter.setFont(T.ui_font(13, 600))
        painter.setPen(QColor(T.TEXT))
        painter.drawText(QRectF(0, self.height() - 52, self.width(), 30), Qt.AlignCenter,
                         f"{self._index + 1} / {len(self._urls)}")
        painter.end()

    def mouseMoveEvent(self, event):
        hover = ""
        for name, rect in self._buttons().items():
            if rect.contains(event.position()):
                hover = name
        if hover != self._hover:
            self._hover = hover
            self.setCursor(Qt.PointingHandCursor if hover else Qt.ArrowCursor)
            self.update()

    def mousePressEvent(self, event):
        buttons = self._buttons()
        pos = event.position()
        if buttons["prev"].contains(pos):
            self.step(-1)
        elif buttons["next"].contains(pos):
            self.step(1)
        elif buttons["close"].contains(pos):
            self.close_viewer()
        else:
            url = self._urls[self._index] if self._urls else ""
            pixmap = self._images.pixmap("shot_full", url) or self._images.pixmap("shot", url)
            if not self._image_rect(pixmap).contains(pos):
                self.close_viewer()
        event.accept()

    def wheelEvent(self, event):
        self.step(-1 if event.angleDelta().y() > 0 else 1)
        event.accept()

    def event(self, event):
        if event.type() == QEvent.ShortcutOverride and event.key() in (Qt.Key_Escape, Qt.Key_Left, Qt.Key_Right):
            event.accept()
            return True
        return super().event(event)

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key_Escape:
            self.close_viewer()
        elif key == Qt.Key_Left:
            self.step(-1)
        elif key == Qt.Key_Right:
            self.step(1)
        else:
            super().keyPressEvent(event)


class GamePage(QScrollArea):
    """Steam library game page: hero, control bar, sub navigation, then a
    two-column body (screenshots, about, optional content | install and
    source panels)."""

    def __init__(self, images: ImageHub, parent=None):
        super().__init__(parent)
        self._images = images
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.canvas = _GameCanvas()
        self.setWidget(self.canvas)
        page = QVBoxLayout(self.canvas)
        page.setContentsMargins(0, 0, 0, 0)
        page.setSpacing(0)

        self.hero = SteamHero()
        self.hero.artChanged.connect(self._hero_changed)
        page.addWidget(self.hero)

        # -- control bar -------------------------------------------------
        self.control = ControlBar()
        self.action_button = SteamActionButton()
        self.control.add_fixed(self.action_button)

        self.dl_block = QWidget()
        dl = QVBoxLayout(self.dl_block)
        dl.setContentsMargins(0, 0, 0, 0)
        dl.setSpacing(5)
        caption_row = QHBoxLayout()
        caption_row.setSpacing(10)
        self.action_dl_caption = QLabel("İNDİRİLİYOR")
        self.action_dl_caption.setObjectName("dlCaption")
        self.action_dl_value = QLabel("%0 Tamamlandı")
        self.action_dl_value.setObjectName("dlValue")
        caption_row.addWidget(self.action_dl_caption)
        caption_row.addStretch(1)
        caption_row.addWidget(self.action_dl_value)
        dl.addLayout(caption_row)
        self.action_dl_bar = QProgressBar()
        self.action_dl_bar.setObjectName("actionBar")
        self.action_dl_bar.setRange(0, 100)
        self.action_dl_bar.setTextVisible(False)
        self.action_dl_bar.setFixedWidth(250)
        dl.addWidget(self.action_dl_bar)
        foot = QHBoxLayout()
        foot.setSpacing(8)
        self.dl_bytes = make_label("", T.TEXT_MUTED, 12)
        self.cancel_link = QPushButton("İptal")
        self.cancel_link.setObjectName("inlineCancel")
        self.cancel_link.setCursor(Qt.PointingHandCursor)
        foot.addWidget(self.dl_bytes)
        foot.addStretch(1)
        foot.addWidget(self.cancel_link)
        dl.addLayout(foot)
        self.dl_block.hide()
        self.control.add_fixed(self.dl_block)

        self.blocked_note = QLabel("")
        self.blocked_note.setObjectName("blockedNote")
        self.blocked_note.setWordWrap(True)
        self.blocked_note.setMaximumWidth(220)
        self.blocked_note.hide()
        self.control.add_fixed(self.blocked_note)

        self.status_value = DashLabel("-")
        self.stat_version = DashLabel("-")
        self.stat_size = DashLabel("-")
        self.stat_channel = DashLabel("-")
        self.stat_platform = DashLabel("-")
        self.status_stat = StatBlock(G.CLOUD, "DURUM", self.status_value)
        self.control.add_stat(self.status_stat)
        self.control.add_stat(StatBlock(G.TAG, "SÜRÜM", self.stat_version))
        self.control.add_stat(StatBlock(G.DRIVE, "BOYUT", self.stat_size))
        self.control.add_stat(StatBlock(G.PACKAGE, "KANAL", self.stat_channel))
        self.control.add_stretch()
        self.star_button = icon_button(G.STAR, "squareButton", "Favorilere ekle", 15, T.TEXT_MUTED, "#ffffff")
        self.star_button.setCheckable(True)
        self.gear_button = icon_button(G.SETTINGS, "squareButton", "Yönet", 15, T.TEXT_MUTED, "#ffffff")
        self.gear_menu = QMenu(self.gear_button)
        self.gear_button.setMenu(self.gear_menu)
        self.control.add_fixed(self.star_button)
        self.control.add_fixed(self.gear_button)
        page.addWidget(self.control)

        # -- sub navigation --------------------------------------------------
        self.subnav = SubNav()
        self.subnav.add_link("store", "Mağaza Sayfası")
        self.subnav.add_link("community", "Topluluk Merkezi")
        self.subnav.add_link("discussions", "Tartışmalar")
        self.subnav.add_link("guides", "Rehberler")
        self.subnav.add_link("files", "Yerel Dosyalar")
        self.subnav.finish()
        page.addWidget(self.subnav)

        # -- body --------------------------------------------------------------
        body = QWidget()
        columns = QHBoxLayout(body)
        columns.setContentsMargins(24, 24, 24, 40)
        columns.setSpacing(24)
        left = QVBoxLayout()
        left.setSpacing(26)

        shots = QVBoxLayout()
        shots.setSpacing(10)
        self.shots_header = SectionHeader("EKRAN GÖRÜNTÜLERİ", line=False)
        self.shots_prev = icon_button(G.CHEVRON_LEFT, "chromeFlat", "Önceki", 12)
        self.shots_next = icon_button(G.CHEVRON_RIGHT, "chromeFlat", "Sonraki", 12)
        self.shots_header.add_right(self.shots_prev)
        self.shots_header.add_right(self.shots_next)
        shots.addWidget(self.shots_header)
        shots_panel = QFrame()
        shots_panel.setObjectName("steamPanel")
        shots_layout = QVBoxLayout(shots_panel)
        shots_layout.setContentsMargins(14, 14, 14, 14)
        self.screenshot_strip = ScreenshotStrip(images)
        self.shots_empty = make_label("Bu yayın için ekran görüntüsü eklenmemiş.", T.TEXT_MUTED, 13)
        self.shots_empty.hide()
        shots_layout.addWidget(self.screenshot_strip)
        shots_layout.addWidget(self.shots_empty)
        shots.addWidget(shots_panel)
        left.addLayout(shots)
        self.shots_prev.clicked.connect(lambda: self.screenshot_strip.scroll_page(-1))
        self.shots_next.clicked.connect(lambda: self.screenshot_strip.scroll_page(1))
        self.screenshot_strip.countChanged.connect(self._shots_changed)

        about = QVBoxLayout()
        about.setSpacing(10)
        about.addWidget(SectionHeader("OYUN HAKKINDA", line=False))
        about_panel = QFrame()
        about_panel.setObjectName("steamPanel")
        about_layout = QVBoxLayout(about_panel)
        about_layout.setContentsMargins(18, 16, 18, 18)
        self.description = QLabel("Raw GitHub kataloğundan oyunlar yükleniyor.")
        self.description.setObjectName("gameDescription")
        self.description.setWordWrap(True)
        self.description.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.description.setTextInteractionFlags(Qt.TextSelectableByMouse)
        about_layout.addWidget(self.description)
        about.addWidget(about_panel)
        left.addLayout(about)

        self.dlc_host = QWidget()
        self.dlc_host.setObjectName("dlcHost")
        self.dlc_layout = QVBoxLayout(self.dlc_host)
        self.dlc_layout.setContentsMargins(0, 0, 0, 0)
        self.dlc_layout.setSpacing(10)
        self.dlc_layout.addWidget(SectionHeader("İSTEĞE BAĞLI İÇERİK", line=False))
        self.dlc_host.hide()
        left.addWidget(self.dlc_host)
        left.addStretch(1)
        columns.addLayout(left, 1)

        right = QVBoxLayout()
        right.setSpacing(16)
        install_panel, install_layout = _panel("Kurulum")
        self.panel_state = DashLabel("-")
        self.panel_path = PathLabel("-")
        self.panel_tag = DashLabel("-")
        self.panel_published = DashLabel("-")
        _panel_row(install_layout, "Durum", self.panel_state)
        _panel_row(install_layout, "Klasör", self.panel_path)
        _panel_row(install_layout, "Etiket", self.panel_tag, wrap=True)
        _panel_row(install_layout, "Yayın tarihi", self.panel_published)
        self.open_folder_link = QPushButton("Yerel dosyalara göz at")
        self.open_folder_link.setObjectName("linkButton")
        self.open_folder_link.setCursor(Qt.PointingHandCursor)
        install_layout.addWidget(self.open_folder_link, 0, Qt.AlignLeft)
        right.addWidget(install_panel)
        source_panel, source_layout = _panel("Kaynak")
        self.panel_repo = DashLabel("-")
        self.panel_branch = DashLabel("-")
        _panel_row(source_layout, "Depo", self.panel_repo, wrap=True)
        _panel_row(source_layout, "Dal", self.panel_branch)
        self.repo_link = QPushButton("GitHub'da görüntüle")
        self.repo_link.setObjectName("linkButton")
        self.repo_link.setCursor(Qt.PointingHandCursor)
        source_layout.addWidget(self.repo_link, 0, Qt.AlignLeft)
        right.addWidget(source_panel)
        right.addStretch(1)
        right_host = QWidget()
        right_host.setLayout(right)
        right_host.setFixedWidth(320)
        columns.addWidget(right_host, 0, Qt.AlignTop)
        page.addWidget(body, 1)

    def _hero_changed(self):
        self.canvas.set_backdrop(blurred_backdrop(self.hero.hero, 360, 14) if not self.hero.hero.isNull() else QPixmap())

    def _shots_changed(self, count: int):
        self.shots_header.set_count(count if count else None)
        self.screenshot_strip.setVisible(bool(count))
        self.shots_empty.setVisible(not count)
        self.shots_prev.setVisible(count > 3)
        self.shots_next.setVisible(count > 3)

    def set_status(self, glyph: str, text: str, color: str = "#8b929a"):
        self.status_value.setText(text)
        self.status_stat.set_icon(glyph, color)

    def set_download_visible(self, visible: bool):
        if self.dl_block.isHidden() == visible:
            self.dl_block.setVisible(visible)
            self.control.fit_stats()

    def set_blocked_note(self, text: str):
        if text == self.blocked_note.text() and self.blocked_note.isHidden() != bool(text):
            return
        self.blocked_note.setText(text)
        self.blocked_note.setVisible(bool(text))
        self.control.fit_stats()

    def set_steam_links(self, app_id):
        has = bool(app_id)
        for key in ("store", "community", "discussions", "guides"):
            self.subnav.links[key].setVisible(has)

    def scroll_to_top(self):
        self.verticalScrollBar().setValue(0)


# ---------------------------------------------------------------------------
# downloads page
# ---------------------------------------------------------------------------


class DownloadsHeader(QFrame):
    """Downloads banner: the active game's art, a live network graph fed
    from the downloader's own speed readout, and the stat panel. Keeps the
    DownloadHeroPanel contract (set_hero)."""

    STATS_W = 460

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(196)
        self._hero = QPixmap()
        self._hero_scaled = QPixmap()
        self._hero_key = None
        self._samples: deque[float] = deque(maxlen=120)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addStretch(1)
        panel = QWidget()
        panel.setFixedWidth(self.STATS_W)
        column = QVBoxLayout(panel)
        column.setContentsMargins(24, 18, 24, 16)
        column.setSpacing(12)
        self.title = QLabel("İNDİRME YOK")
        self.title.setObjectName("dlHeaderTitle")
        self.title.setFont(T.ui_font(15, 800, spacing=1.0))
        column.addWidget(self.title)
        grid = QGridLayout()
        grid.setHorizontalSpacing(22)
        grid.setVerticalSpacing(2)
        self.value_labels: list[QLabel] = []
        for col, caption in enumerate(("ANLIK", "EN YÜKSEK", "TOPLAM", "AKIŞ")):
            value = DashLabel("-")
            value.setObjectName("dlStatValue")
            label = QLabel(caption)
            label.setObjectName("dlStatLabel")
            grid.addWidget(value, 0, col)
            grid.addWidget(label, 1, col)
            self.value_labels.append(value)
        column.addLayout(grid)
        column.addStretch(1)
        legend = QHBoxLayout()
        legend.setSpacing(6)
        swatch = QLabel()
        swatch.setFixedSize(10, 10)
        swatch.setStyleSheet(f"background: {T.ACCENT}; border-radius: 1px;")
        legend.addWidget(swatch)
        legend_text = QLabel("AĞ")
        legend_text.setObjectName("dlLegend")
        legend.addWidget(legend_text)
        legend.addSpacing(12)
        self.limit_label = ElidingLabel("GitHub Releases üzerinden doğrudan indirme")
        self.limit_label.setObjectName("dlLegend")
        legend.addWidget(self.limit_label, 1)
        column.addLayout(legend)
        layout.addWidget(panel)

    def set_hero(self, pixmap):
        self._hero = pixmap if pixmap is not None and not pixmap.isNull() else QPixmap()
        self._hero_key = None
        self.update()

    def has_hero(self) -> bool:
        return not self._hero.isNull()

    def push_sample(self, bytes_per_second: float):
        self._samples.append(max(0.0, float(bytes_per_second)))
        self.update()

    def clear_samples(self):
        self._samples.clear()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        w, h = self.width(), self.height()
        painter.fillRect(self.rect(), QColor(T.DL_HEADER))
        art_w = int(w * 0.28)
        graph = QRectF(art_w, 0, max(10, w - art_w - self.STATS_W), h - 1)
        painter.fillRect(graph, QColor(T.DL_GRAPH))
        if not self._hero.isNull():
            ratio = device_ratio(self)
            key = (art_w, h, self._hero.cacheKey(), ratio)
            if key != self._hero_key:
                self._hero_scaled = cover_crop(self._hero, art_w, h, 0.35, 0.3, ratio)
                self._hero_key = key
            painter.drawPixmap(QRectF(0, 0, art_w, h), self._hero_scaled, QRectF(self._hero_scaled.rect()))
        fade = QLinearGradient(art_w * 0.55, 0, art_w + 1, 0)
        fade.setColorAt(0.0, QColor(7, 26, 44, 0))
        fade.setColorAt(1.0, QColor(T.DL_GRAPH))
        painter.fillRect(QRectF(0, 0, art_w + 1, h), fade)

        painter.setPen(QPen(QColor(255, 255, 255, 12), 1))
        for i in range(1, 4):
            y = graph.top() + graph.height() * i / 4
            painter.drawLine(QPointF(graph.left(), y), QPointF(graph.right(), y))
        samples = list(self._samples)
        if samples:
            peak = max(max(samples), 1.0)
            capacity = self._samples.maxlen or 120
            bar_w = graph.width() / capacity
            painter.setPen(Qt.NoPen)
            for index, value in enumerate(samples):
                x = graph.right() - (len(samples) - index) * bar_w
                bar_h = (value / peak) * (graph.height() - 24)
                painter.setBrush(QColor(26, 159, 255, 150))
                painter.drawRect(QRectF(x + 0.5, graph.bottom() - bar_h, max(1.0, bar_w - 1.0), bar_h))
                painter.setBrush(QColor(120, 200, 255, 230))
                painter.drawRect(QRectF(x + 0.5, graph.bottom() - bar_h, max(1.0, bar_w - 1.0), 2))
        painter.fillRect(QRectF(0, h - 1, w, 1), QColor(26, 159, 255, 150))
        painter.end()


class CompletedDownloadRow(QFrame):
    playRequested = Signal(str)
    openRequested = Signal(str)
    removeRequested = Signal(str)

    def __init__(self, key: str, title: str, subtitle: str, finished: str, can_play: bool, parent=None):
        super().__init__(parent)
        self.setObjectName("dlRow")
        self.key = key
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 10, 14, 10)
        layout.setSpacing(16)
        self.art = HeaderArt(142, 66)
        self.art.set_art(None, title)
        layout.addWidget(self.art)
        text = QVBoxLayout()
        text.setSpacing(3)
        text.addWidget(make_label(title, "#ffffff", 14, 700))
        text.addWidget(make_label(subtitle, T.TEXT_MUTED, 12))
        layout.addLayout(text, 1)
        layout.addWidget(make_label(finished, T.TEXT_MUTED, 12))
        play = QPushButton("OYNA")
        play.setObjectName("dlPlay")
        play.setCursor(Qt.PointingHandCursor)
        play.setVisible(can_play)
        play.clicked.connect(lambda: self.playRequested.emit(self.key))
        folder = icon_button(G.FOLDER, "dlIcon", "Yerel dosyalara göz at", 13)
        folder.clicked.connect(lambda: self.openRequested.emit(self.key))
        remove = icon_button(G.CLOSE, "dlIcon", "Bu kaydı listeden kaldır", 10)
        remove.clicked.connect(lambda: self.removeRequested.emit(self.key))
        layout.addWidget(play)
        layout.addWidget(folder)
        layout.addWidget(remove)


def _section_row(title_label: QLabel, count_label: QLabel, note: QWidget | None = None) -> QHBoxLayout:
    row = QHBoxLayout()
    row.setSpacing(8)
    row.addWidget(title_label)
    row.addWidget(count_label)
    line = QFrame()
    line.setFixedHeight(1)
    line.setStyleSheet("background: rgba(255, 255, 255, 22);")
    row.addWidget(line, 1, Qt.AlignVCenter)
    if note is not None:
        row.addWidget(note)
    return row


class _DownloadsCanvas(QWidget):
    def paintEvent(self, event):
        painter = QPainter(self)
        gradient = QLinearGradient(0, 0, 0, max(1, self.height()))
        gradient.setColorAt(0.0, QColor("#2b2d3a"))
        gradient.setColorAt(1.0, QColor("#1f2029"))
        painter.fillRect(self.rect(), gradient)
        painter.end()


class DownloadsPage(QWidget):
    """Steam downloads page (2021+ layout): graph header, active download
    row, Up Next, Completed, plus the operation log."""

    def __init__(self, images: ImageHub, logs: QWidget, parent=None):
        super().__init__(parent)
        self._images = images
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.header = DownloadsHeader()
        outer.addWidget(self.header)

        self.active_row = QFrame()
        self.active_row.setObjectName("dlActiveRow")
        self.active_row.setFixedHeight(112)
        row = QHBoxLayout(self.active_row)
        row.setContentsMargins(24, 16, 24, 16)
        row.setSpacing(18)
        self.active_art = HeaderArt(172, 80)
        row.addWidget(self.active_art)
        text = QVBoxLayout()
        text.setSpacing(4)
        self.title = QLabel("Etkin indirme yok")
        self.title.setObjectName("dlTitle")
        self.detail = ElidingLabel("Kütüphaneden bir oyun seçip YÜKLE ile indirmeyi başlat.")
        self.detail.setObjectName("dlMuted")
        text.addStretch(1)
        text.addWidget(self.title)
        text.addWidget(self.detail)
        text.addStretch(1)
        row.addLayout(text, 1)
        progress = QVBoxLayout()
        progress.setSpacing(6)
        top = QHBoxLayout()
        top.setSpacing(8)
        self.eta = QLabel("Kalan tahmini süre: -")
        self.eta.setObjectName("dlMuted")
        self.state = QLabel("")
        self.state.setObjectName("dlState")
        self.percent = QLabel("%0")
        self.percent.setObjectName("dlPercent")
        top.addWidget(self.eta)
        top.addStretch(1)
        top.addWidget(self.state)
        top.addWidget(self.percent)
        progress.addStretch(1)
        progress.addLayout(top)
        self.bar = QProgressBar()
        self.bar.setObjectName("dlBar")
        self.bar.setRange(0, 100)
        self.bar.setTextVisible(False)
        progress.addWidget(self.bar)
        bottom = QHBoxLayout()
        bottom.addStretch(1)
        self.bytes = QLabel("-")
        self.bytes.setObjectName("dlMuted")
        bottom.addWidget(self.bytes)
        progress.addLayout(bottom)
        progress.addStretch(1)
        progress_host = QWidget()
        progress_host.setLayout(progress)
        progress_host.setFixedWidth(400)
        row.addWidget(progress_host)
        self.pause = PauseGlyphButton()
        self.pause.hide()
        self.cancel = icon_button(G.CLOSE, "dlIcon", "İndirmeyi iptal et", 10)
        self.cancel.hide()
        row.addWidget(self.pause, 0, Qt.AlignVCenter)
        row.addWidget(self.cancel, 0, Qt.AlignVCenter)
        outer.addWidget(self.active_row)

        scroller = QScrollArea()
        scroller.setWidgetResizable(True)
        scroller.setFrameShape(QFrame.NoFrame)
        scroller.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body = _DownloadsCanvas()
        scroller.setWidget(body)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(24, 22, 24, 36)
        layout.setSpacing(12)

        self.queue_caption = QLabel("Sıradaki")
        self.queue_caption.setObjectName("dlSection")
        self.queue_count = QLabel("(0)")
        self.queue_count.setObjectName("dlSectionCount")
        queue_note = QLabel("Tek seferde bir indirme çalışır")
        queue_note.setObjectName("dlMuted")
        layout.addLayout(_section_row(self.queue_caption, self.queue_count, queue_note))
        self.queue_body = QLabel("Kuyrukta indirme yok.")
        self.queue_body.setObjectName("dlMuted")
        layout.addWidget(self.queue_body)
        layout.addSpacing(18)

        self.done_caption = QLabel("Tamamlanan")
        self.done_caption.setObjectName("dlSection")
        self.done_count = QLabel("(0)")
        self.done_count.setObjectName("dlSectionCount")
        layout.addLayout(_section_row(self.done_caption, self.done_count))
        self.done_empty = QLabel("Henüz tamamlanmış kurulum yok.")
        self.done_empty.setObjectName("dlMuted")
        layout.addWidget(self.done_empty)
        self.rows_layout = QVBoxLayout()
        self.rows_layout.setSpacing(6)
        layout.addLayout(self.rows_layout)
        layout.addSpacing(18)

        self.log_section = QWidget()
        log_layout = QVBoxLayout(self.log_section)
        log_layout.setContentsMargins(0, 0, 0, 0)
        log_layout.setSpacing(10)
        log_layout.addWidget(SectionHeader("İşlem günlüğü", line=True))
        logs.setMinimumHeight(150)
        log_layout.addWidget(logs)
        self.log_section.hide()
        layout.addWidget(self.log_section)
        layout.addStretch(1)
        outer.addWidget(scroller, 1)


# ---------------------------------------------------------------------------
# store
# ---------------------------------------------------------------------------


class _StoreCanvas(QWidget):
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(T.STORE_BG))
        glow = QRadialGradient(QPointF(self.width() * 0.5, -40), max(400.0, self.width() * 0.55))
        glow.setColorAt(0.0, QColor(62, 110, 150, 120))
        glow.setColorAt(1.0, QColor(27, 40, 56, 0))
        painter.fillRect(QRectF(0, 0, self.width(), 520), glow)
        painter.end()


class StoreNavBar(QFrame):
    linkClicked = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(40)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 0, 6, 0)
        layout.setSpacing(0)
        for key, text in (("featured", "Öne Çıkanlar"), ("new", "Yeni Eklenenler"), ("all", "Tüm Oyunlar")):
            button = QPushButton(text)
            button.setObjectName("storeNavLink")
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda _c=False, k=key: self.linkClicked.emit(k))
            layout.addWidget(button)
        layout.addStretch(1)
        self.search = QLineEdit()
        self.search.setObjectName("storeSearch")
        self.search.setPlaceholderText("Mağazada ara")
        self.search.setClearButtonEnabled(True)
        self.search.setFixedWidth(240)
        layout.addWidget(self.search)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect())
        gradient = QLinearGradient(rect.topLeft(), rect.topRight())
        gradient.setColorAt(0.1138, QColor(62, 103, 150, 234))
        gradient.setColorAt(0.2523, QColor(58, 120, 177, 204))
        gradient.setColorAt(1.0, QColor(15, 33, 110))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(0, 0, 0, 90))
        painter.drawRoundedRect(rect.adjusted(-1, 1, 1, 2), 3, 3)
        painter.setBrush(gradient)
        painter.drawRoundedRect(rect, 3, 3)
        painter.end()


class FeaturedCarousel(QWidget):
    """"Featured & Recommended" main capsule: art on the left (hovering a
    screenshot previews it), info panel on the right, arrows and dots."""

    openRequested = Signal(str)

    ARROW_W = 46
    MAIN_H = 353

    def __init__(self, images: ImageHub, parent=None):
        super().__init__(parent)
        self._images = images
        self._items: list[dict] = []
        self._index = 0
        self._previous = -1
        self._preview = -1
        self._fade = 1.0
        self._hover = ""
        self._backdrops: dict[str, QPixmap] = {}
        self._crops: dict[tuple, QPixmap] = {}
        self.setFixedHeight(self.MAIN_H + 30)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WA_Hover, True)
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(420)
        self._anim.setEasingCurve(QEasingCurve.InOutCubic)
        self._anim.valueChanged.connect(self._on_fade)
        self._timer = QTimer(self)
        self._timer.setInterval(7000)
        self._timer.timeout.connect(lambda: self.go(self._index + 1))

    def set_items(self, items: list[dict]):
        self._items = items
        self._index = 0
        self._previous = -1
        self._preview = -1
        self._crops.clear()
        self._sync_autoplay()
        self.update()

    def _sync_autoplay(self):
        if self._items and self.isVisible() and T.animations_enabled():
            self._timer.start()
        else:
            self._timer.stop()

    def showEvent(self, event):  # noqa: N802 - Qt naming
        super().showEvent(event)
        self._sync_autoplay()

    def hideEvent(self, event):  # noqa: N802 - Qt naming
        super().hideEvent(event)
        self._timer.stop()

    def go(self, index: int):
        if not self._items:
            return
        index %= len(self._items)
        if index == self._index:
            return
        self._previous = self._index
        self._index = index
        self._preview = -1
        if T.animations_enabled():
            self._anim.stop()
            self._anim.setStartValue(0.0)
            self._anim.setEndValue(1.0)
            self._anim.start()
        else:
            self._fade = 1.0
        self.update()

    def _on_fade(self, value):
        self._fade = float(value)
        self.update()

    # -- geometry ------------------------------------------------------
    def _main_rect(self) -> QRectF:
        inner_w = self.width() - self.ARROW_W * 2
        return QRectF(self.ARROW_W, 0, inner_w * 0.655, self.MAIN_H)

    def _panel_rect(self) -> QRectF:
        main = self._main_rect()
        return QRectF(main.right(), 0, self.width() - self.ARROW_W - main.right(), self.MAIN_H)

    def _thumb_rects(self) -> list[QRectF]:
        panel = self._panel_rect()
        pad, gap = 14.0, 8.0
        tw = (panel.width() - pad * 2 - gap) / 2
        th = tw * 9 / 16
        top = panel.top() + 72
        return [QRectF(panel.left() + pad + (i % 2) * (tw + gap), top + (i // 2) * (th + gap), tw, th)
                for i in range(4)]

    def _arrow_rects(self) -> dict[str, QRectF]:
        return {"prev": QRectF(0, 0, self.ARROW_W, self.MAIN_H),
                "next": QRectF(self.width() - self.ARROW_W, 0, self.ARROW_W, self.MAIN_H)}

    def _dot_rects(self) -> list[QRectF]:
        count = len(self._items)
        width = count * 15 + max(0, count - 1) * 4
        x = (self.width() - width) / 2
        return [QRectF(x + i * 19, self.MAIN_H + 14, 15, 9) for i in range(count)]

    # -- painting ------------------------------------------------------------
    def _art(self, item: dict, preview: int) -> QPixmap | None:
        shots = item.get("shots") or []
        if 0 <= preview < len(shots):
            url, kind = shots[preview], "wide"
        elif shots:
            url, kind = shots[0], "wide"
        else:
            url, kind = item.get("hero_url") or "", "hero"
        if not url:
            return None
        main = self._main_rect()
        ratio = device_ratio(self)
        crop_key = (url, int(main.width()), int(main.height()), ratio)
        cached = self._crops.get(crop_key)
        if cached is not None:
            return cached
        source = self._images.request(kind, url, lambda _u, _p: self.update())
        if source is None:
            return None
        crop = cover_crop(source, int(main.width()), int(main.height()), 0.5, 0.4, ratio)
        if len(self._crops) > 40:
            self._crops.clear()
        self._crops[crop_key] = crop
        return crop

    def _paint_item(self, painter: QPainter, item: dict, preview: int):
        main = self._main_rect()
        panel = self._panel_rect()
        art = self._art(item, preview)
        painter.save()
        painter.setClipRect(main)
        if art is not None:
            painter.drawPixmap(main, art, QRectF(art.rect()))
        else:
            placeholder_art(painter, main, item.get("title", ""), item["key"])
        logo = self._images.request("logo", item.get("logo_url") or "", lambda _u, _p: self.update()) \
            if item.get("logo_url") else None
        if logo is not None and preview < 0:
            shade = QLinearGradient(main.bottomLeft(), QPointF(main.left(), main.top() + main.height() * 0.35))
            shade.setColorAt(0.0, QColor(0, 0, 0, 170))
            shade.setColorAt(1.0, QColor(0, 0, 0, 0))
            painter.fillRect(main, shade)
            scale = min(main.width() * 0.5 / logo.width(), main.height() * 0.34 / logo.height())
            lw, lh = logo.width() * scale, logo.height() * scale
            painter.drawPixmap(QRectF(main.left() + 22, main.bottom() - lh - 22, lw, lh), logo, QRectF(logo.rect()))
        painter.restore()

        backdrop = self._backdrops.get(item["key"])
        if backdrop is None and art is not None:
            backdrop = blurred_backdrop(art, 240, 12)
            self._backdrops[item["key"]] = backdrop
        painter.save()
        painter.setClipRect(panel)
        if backdrop is not None and not backdrop.isNull():
            painter.drawPixmap(panel, backdrop.scaled(int(panel.width()), int(panel.height()),
                                                      Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation),
                               QRectF(0, 0, panel.width(), panel.height()))
        painter.fillRect(panel, QColor(9, 16, 24, 205))
        painter.setPen(QColor("#ffffff"))
        title_font = T.ui_font(22, 400, display=True)
        painter.setFont(title_font)
        painter.drawText(QRectF(panel.left() + 14, panel.top() + 14, panel.width() - 28, 50),
                         Qt.AlignLeft | Qt.AlignTop, elide(item.get("title", ""), title_font, panel.width() - 28))
        shots = item.get("shots") or []
        for index, rect in enumerate(self._thumb_rects()):
            if index >= len(shots):
                break
            source = self._images.request("shot", shots[index], lambda _u, _p: self.update())
            if source is not None:
                thumb = cover_crop(source, int(rect.width()), int(rect.height()), 0.5, 0.5, device_ratio(self))
                painter.drawPixmap(rect, thumb, QRectF(thumb.rect()))
            else:
                painter.fillRect(rect, QColor(255, 255, 255, 18))
            if index == preview:
                painter.setPen(QPen(QColor(255, 255, 255, 190), 1))
                painter.setBrush(Qt.NoBrush)
                painter.drawRect(rect.adjusted(0.5, 0.5, -0.5, -0.5))
        info_top = self._thumb_rects()[2].bottom() + 16 if shots else panel.top() + 80
        painter.setPen(QColor("#ffffff"))
        painter.setFont(T.ui_font(16, 400))
        painter.drawText(QRectF(panel.left() + 14, info_top, panel.width() - 28, 24), Qt.AlignLeft | Qt.AlignVCenter,
                         "Şimdi mevcut")
        x = panel.left() + 14
        tag_font = T.ui_font(11, 400)
        painter.setFont(tag_font)
        metrics = QFontMetrics(tag_font)
        for tag in item.get("tags") or []:
            width = metrics.horizontalAdvance(tag) + 14
            if x + width > panel.right() - 14:
                break
            pill = QRectF(x, info_top + 30, width, 20)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(255, 255, 255, 40))
            painter.drawRoundedRect(pill, 2, 2)
            painter.setPen(QColor("#ffffff"))
            painter.drawText(pill, Qt.AlignCenter, tag)
            x += width + 4
        flag_font = T.ui_font(10, 700, spacing=0.6)
        painter.setFont(flag_font)
        flag = "YÜKLÜ" if item.get("installed") else "KÜTÜPHANEDE"
        flag_w = QFontMetrics(flag_font).horizontalAdvance(flag) + 16
        flag_rect = QRectF(panel.left() + 14, panel.bottom() - 34, flag_w, 20)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#4c6b22"))
        painter.drawRoundedRect(flag_rect, 2, 2)
        painter.setPen(QColor("#d2e885"))
        painter.drawText(flag_rect, Qt.AlignCenter, flag)
        painter.setPen(QColor(T.STORE_TEXT))
        painter.setFont(T.ui_font(13, 400))
        painter.drawText(QRectF(panel.left(), panel.bottom() - 34, panel.width() - 14, 20),
                         Qt.AlignRight | Qt.AlignVCenter, item.get("size_text", ""))
        painter.restore()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.setRenderHint(QPainter.TextAntialiasing)
        if not self._items:
            paint_shimmer(painter, QRectF(self.ARROW_W, 0, self.width() - self.ARROW_W * 2, self.MAIN_H), 0.4, 0,
                          base="#16202d")
            painter.end()
            return
        shadow = QRectF(self.ARROW_W, 0, self.width() - self.ARROW_W * 2, self.MAIN_H)
        painter.fillRect(shadow.adjusted(-2, -2, 2, 4), QColor(0, 0, 0, 90))
        if self._fade < 1.0 and 0 <= self._previous < len(self._items):
            self._paint_item(painter, self._items[self._previous], -1)
            painter.setOpacity(self._fade)
        self._paint_item(painter, self._items[self._index], self._preview)
        painter.setOpacity(1.0)
        for name, rect in self._arrow_rects().items():
            gradient = QLinearGradient(rect.topLeft(), rect.topRight())
            strong = QColor(0, 0, 0, 90 if self._hover == name else 50)
            clear = QColor(0, 0, 0, 0)
            gradient.setColorAt(0.0, strong if name == "prev" else clear)
            gradient.setColorAt(1.0, clear if name == "prev" else strong)
            painter.fillRect(rect, gradient)
            painter.setPen(QColor(255, 255, 255, 230 if self._hover == name else 150))
            painter.setFont(T.icon_font(22))
            painter.drawText(rect, Qt.AlignCenter, G.CHEVRON_LEFT if name == "prev" else G.CHEVRON_RIGHT)
        for index, rect in enumerate(self._dot_rects()):
            painter.fillRect(rect, QColor(255, 255, 255, 110 if index == self._index else 40))
        painter.end()

    # -- input ---------------------------------------------------------------
    def event(self, event):
        if event.type() == QEvent.HoverEnter:
            self._timer.stop()
        elif event.type() == QEvent.HoverLeave:
            self._hover = ""
            if self._preview != -1:
                self._preview = -1
            self._sync_autoplay()
            self.update()
        return super().event(event)

    def mouseMoveEvent(self, event):
        pos = event.position()
        hover = ""
        for name, rect in self._arrow_rects().items():
            if rect.contains(pos):
                hover = name
        preview = -1
        shots = (self._items[self._index].get("shots") or []) if self._items else []
        for index, rect in enumerate(self._thumb_rects()):
            if index < len(shots) and rect.contains(pos):
                preview = index
        clickable = bool(hover) or self._main_rect().contains(pos) or self._panel_rect().contains(pos) or any(
            r.contains(pos) for r in self._dot_rects())
        self.setCursor(Qt.PointingHandCursor if clickable else Qt.ArrowCursor)
        if hover != self._hover or (preview != self._preview and preview >= 0):
            self._hover = hover
            if preview >= 0:
                self._preview = preview
            self.update()

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton or not self._items:
            return
        pos = event.position()
        arrows = self._arrow_rects()
        if arrows["prev"].contains(pos):
            self.go(self._index - 1)
            return
        if arrows["next"].contains(pos):
            self.go(self._index + 1)
            return
        for index, rect in enumerate(self._dot_rects()):
            if rect.adjusted(-2, -4, 2, 4).contains(pos):
                self.go(index)
                return
        if self._main_rect().contains(pos) or self._panel_rect().contains(pos):
            self.openRequested.emit(self._items[self._index]["key"])


class StoreTabList(QWidget):
    """Store tab list with Steam's light-blue focused row and the preview
    panel on the right that shows the focused game's screenshots."""

    openRequested = Signal(str)

    ROW_H = 69
    GAP = 5
    PREVIEW_W = 308
    CAPSULE_W = 184

    def __init__(self, images: ImageHub, parent=None):
        super().__init__(parent)
        self._images = images
        self._items: list[dict] = []
        self._focus = 0
        self._crops: dict[tuple, QPixmap] = {}
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_items(self, items: list[dict]):
        self._items = items
        self._focus = 0 if items else -1
        rows = len(items)
        height = rows * (self.ROW_H + self.GAP)
        self.setFixedHeight(max(height, 80))
        self.update()

    def _row_rect(self, index: int) -> QRectF:
        return QRectF(0, index * (self.ROW_H + self.GAP), self.width() - self.PREVIEW_W, self.ROW_H)

    def _preview_rect(self) -> QRectF:
        return QRectF(self.width() - self.PREVIEW_W, 0, self.PREVIEW_W, self.height() - self.GAP)

    def _crop(self, kind: str, url: str, w: int, h: int) -> QPixmap | None:
        if not url:
            return None
        ratio = device_ratio(self)
        key = (url, w, h, ratio)
        cached = self._crops.get(key)
        if cached is not None:
            return cached
        source = self._images.request(kind, url, lambda _u, _p: self.update())
        if source is None:
            return None
        crop = cover_crop(source, w, h, 0.5, 0.35, ratio)
        self._crops[key] = crop
        return crop

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.setRenderHint(QPainter.TextAntialiasing)
        if not self._items:
            painter.setPen(QColor(T.STORE_MUTED))
            painter.setFont(T.ui_font(13))
            painter.drawText(self.rect(), Qt.AlignCenter, "Aramana uyan oyun bulunamadı.")
            painter.end()
            return
        clip = QRectF(event.rect())
        for index, item in enumerate(self._items):
            rect = self._row_rect(index)
            if not rect.intersects(clip):
                continue
            focused = index == self._focus
            if focused:
                gradient = QLinearGradient(rect.topLeft(), rect.topRight())
                gradient.setColorAt(0.05, QColor(T.STORE_FOCUS_LEFT))
                gradient.setColorAt(0.95, QColor(T.STORE_FOCUS_RIGHT))
                painter.fillRect(rect.adjusted(0, 0, 1, 0), gradient)
            else:
                painter.fillRect(rect, QColor(0, 0, 0, 55))
            cap = QRectF(rect.left(), rect.top(), self.CAPSULE_W, self.ROW_H)
            art = self._crop("wide", item.get("hero_url") or "", self.CAPSULE_W, self.ROW_H)
            if art is not None:
                painter.drawPixmap(cap, art, QRectF(art.rect()))
            else:
                placeholder_art(painter, cap, item.get("title", ""), item["key"])
            dark = QColor(T.STORE_FOCUS_TEXT)
            text_left = cap.right() + 12
            right_w = 150
            title_font = T.ui_font(15, 400)
            painter.setFont(title_font)
            painter.setPen(dark if focused else QColor(T.STORE_TEXT))
            painter.drawText(QRectF(text_left, rect.top() + 12, rect.width() - text_left - right_w, 22),
                             Qt.AlignLeft | Qt.AlignVCenter,
                             elide(item.get("title", ""), title_font, rect.width() - text_left - right_w))
            painter.setFont(T.icon_font(12))
            painter.setPen(QColor("#384959") if focused else QColor(T.STORE_MUTED))
            painter.drawText(QRectF(text_left, rect.top() + 38, 16, 18), Qt.AlignCenter, G.MONITOR)
            painter.setFont(T.ui_font(11, 400))
            painter.drawText(QRectF(text_left + 22, rect.top() + 38, rect.width() - text_left - right_w, 18),
                             Qt.AlignLeft | Qt.AlignVCenter, "  ·  ".join(item.get("tags") or []))
            painter.setPen(dark if focused else QColor(T.STORE_TEXT))
            painter.setFont(T.ui_font(13, 600))
            painter.drawText(QRectF(rect.right() - right_w, rect.top() + 12, right_w - 14, 22),
                             Qt.AlignRight | Qt.AlignVCenter, item.get("size_text", ""))
            painter.setFont(T.ui_font(11))
            painter.setPen(QColor("#4b5d70") if focused else QColor(T.STORE_MUTED))
            painter.drawText(QRectF(rect.right() - right_w, rect.top() + 36, right_w - 14, 20),
                             Qt.AlignRight | Qt.AlignVCenter, item.get("date_text", ""))
        self._paint_preview(painter)
        painter.end()

    def _paint_preview(self, painter: QPainter):
        if not (0 <= self._focus < len(self._items)):
            return
        item = self._items[self._focus]
        rect = self._preview_rect()
        gradient = QLinearGradient(rect.topLeft(), rect.topRight())
        gradient.setColorAt(0.0, QColor(T.STORE_FOCUS_RIGHT))
        gradient.setColorAt(1.0, QColor("#a9cbe0"))
        painter.fillRect(rect, gradient)
        pad = 16.0
        painter.setPen(QColor("#263645"))
        title_font = T.ui_font(19, 400, display=True)
        painter.setFont(title_font)
        painter.drawText(QRectF(rect.left() + pad, rect.top() + 14, rect.width() - pad * 2, 50),
                         Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap, item.get("title", ""))
        painter.setFont(T.ui_font(11))
        painter.setPen(QColor("#4b5d70"))
        painter.drawText(QRectF(rect.left() + pad, rect.top() + 66, rect.width() - pad * 2, 18),
                         Qt.AlignLeft | Qt.AlignVCenter, f"Eklenme: {item.get('long_date', '-')}")
        x = rect.left() + pad
        tag_font = T.ui_font(11)
        metrics = QFontMetrics(tag_font)
        painter.setFont(tag_font)
        for tag in item.get("tags") or []:
            width = metrics.horizontalAdvance(tag) + 14
            pill = QRectF(x, rect.top() + 92, width, 20)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(38, 54, 69, 50))
            painter.drawRoundedRect(pill, 2, 2)
            painter.setPen(QColor("#263645"))
            painter.drawText(pill, Qt.AlignCenter, tag)
            x += width + 4
        shot_w = rect.width() - pad * 2
        shot_h = shot_w * 9 / 16
        y = rect.top() + 126
        for url in (item.get("shots") or [])[:4]:
            if y + shot_h > rect.bottom() - 4:
                break
            shot_rect = QRectF(rect.left() + pad, y, shot_w, shot_h)
            art = self._crop("shot", url, int(shot_w), int(shot_h))
            if art is not None:
                painter.drawPixmap(shot_rect, art, QRectF(art.rect()))
            else:
                painter.fillRect(shot_rect, QColor(38, 54, 69, 40))
            y += shot_h + 8

    def _index_at(self, pos) -> int:
        for index in range(len(self._items)):
            if self._row_rect(index).contains(pos):
                return index
        return -1

    def mouseMoveEvent(self, event):
        index = self._index_at(event.position())
        on_preview = self._preview_rect().contains(event.position())
        self.setCursor(Qt.PointingHandCursor if index >= 0 or on_preview else Qt.ArrowCursor)
        if index >= 0 and index != self._focus:
            self._focus = index
            self.update()

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        index = self._index_at(event.position())
        if index >= 0:
            self.openRequested.emit(self._items[index]["key"])
        elif self._preview_rect().contains(event.position()) and 0 <= self._focus < len(self._items):
            self.openRequested.emit(self._items[self._focus]["key"])


class StorePage(QScrollArea):
    """Catalog storefront in the Steam store's navy palette."""

    openRequested = Signal(str)
    PAGE = 12

    def __init__(self, images: ImageHub, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        canvas = _StoreCanvas()
        self.setWidget(canvas)
        outer = QHBoxLayout(canvas)
        outer.setContentsMargins(24, 0, 24, 0)
        outer.addStretch(1)
        column_host = QWidget()
        column_host.setMaximumWidth(1100)
        column_host.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        column = QVBoxLayout(column_host)
        column.setContentsMargins(0, 22, 0, 48)
        column.setSpacing(14)
        outer.addWidget(column_host, 12)
        outer.addStretch(1)

        self.nav = StoreNavBar()
        column.addWidget(self.nav)
        column.addSpacing(14)
        self.featured_title = make_label("ÖNE ÇIKANLAR VE ÖNERİLENLER", "#ffffff", 14, 500, spacing=0.6)
        column.addWidget(self.featured_title)
        self.carousel = FeaturedCarousel(images)
        column.addWidget(self.carousel)
        column.addSpacing(10)

        list_head = QHBoxLayout()
        self.list_title = make_label("YENİ EKLENENLER", "#ffffff", 14, 500, spacing=0.6)
        list_head.addWidget(self.list_title)
        list_head.addStretch(1)
        self.more_button = QPushButton("Daha fazla göster")
        self.more_button.setObjectName("storeMore")
        self.more_button.setCursor(Qt.PointingHandCursor)
        list_head.addWidget(self.more_button)
        column.addLayout(list_head)
        self.tab_list = StoreTabList(images)
        column.addWidget(self.tab_list)
        column.addStretch(1)

        self._entries: list[dict] = []
        self._limit = self.PAGE
        self.carousel.openRequested.connect(self.openRequested)
        self.tab_list.openRequested.connect(self.openRequested)
        self.more_button.clicked.connect(self._more)
        self.nav.linkClicked.connect(self._nav_link)
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(160)
        self._search_timer.timeout.connect(self._render_list)
        self.nav.search.textChanged.connect(lambda _t: self._search_timer.start())

    def set_games(self, entries: list[dict]):
        """entries: newest first; see Launcher._store_entries."""
        self._entries = entries
        self.carousel.set_items(entries[:8])
        self._render_list()

    def refresh_states(self, states: dict):
        changed = False
        for entry in self._entries:
            state = states.get(entry["key"], {})
            installed = bool(state.get("installed"))
            if entry.get("installed") != installed:
                entry["installed"] = installed
                changed = True
        if changed:
            self.carousel.update()

    def _filtered(self) -> list[dict]:
        query = self.nav.search.text().strip().casefold()
        if not query:
            return self._entries
        return [entry for entry in self._entries if query in entry.get("title", "").casefold()]

    def _render_list(self):
        query = self.nav.search.text().strip()
        items = self._filtered()
        self.list_title.setText("ARAMA SONUÇLARI" if query else "YENİ EKLENENLER")
        shown = items if query else items[: self._limit]
        self.tab_list.set_items(shown)
        self.more_button.setVisible(not query and len(items) > self._limit)
        if query:
            self.ensureWidgetVisible(self.list_title, 0, 60)

    def _more(self):
        self._limit += self.PAGE
        self._render_list()

    def _nav_link(self, key: str):
        if key == "featured":
            self.verticalScrollBar().setValue(0)
        elif key == "new":
            self.nav.search.clear()
            self.ensureWidgetVisible(self.list_title, 0, 40)
        elif key == "all":
            self.nav.search.clear()
            self._limit = max(self._limit, len(self._entries))
            self._render_list()
            self.ensureWidgetVisible(self.list_title, 0, 40)


# ---------------------------------------------------------------------------
# bottom bar
# ---------------------------------------------------------------------------


class SteamBottomBar(QFrame):
    """Steam's footer: a left action, the download readout in the middle
    (click it to open the downloads page) and the connection state."""

    downloadsRequested = Signal()

    def __init__(self, connection_label: QLabel, parent=None):
        super().__init__(parent)
        self.setObjectName("steamBottomBar")
        self.setFixedHeight(40)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(0)
        self.refresh_button = QPushButton("  Kataloğu yenile")
        self.refresh_button.setObjectName("bottomFlat")
        self.refresh_button.setIcon(T.glyph_icon(G.REFRESH, 13, "#8d919a", T.TEXT))
        self.refresh_button.setCursor(Qt.PointingHandCursor)
        layout.addWidget(self.refresh_button)
        layout.addStretch(1)

        self.center = ClickableFrame()
        self.center.setToolTip("İndirmeleri yönet")
        self.center.clicked.connect(self.downloadsRequested)
        self.status_row = QHBoxLayout(self.center)
        self.status_row.setContentsMargins(12, 0, 12, 0)
        self.status_row.setSpacing(10)
        self.dl_glyph = GlyphLabel(G.DOWNLOAD, 13, "#8d919a", 20)
        self.status_icon = IconSquare(24)
        self.status_icon.hide()
        self.status = ElidingLabel("Hazır")
        self.status.setObjectName("bottomStatus")
        self.status.setMaximumWidth(460)
        self.status.setMinimumWidth(180)
        self.progress = QProgressBar()
        self.progress.setObjectName("bottomProgress")
        self.progress.setRange(0, 100)
        self.progress.setTextVisible(False)
        self.progress_text = QLabel("")
        self.progress_text.setObjectName("bottomPercent")
        self.status_row.addWidget(self.dl_glyph)
        self.status_row.addWidget(self.status_icon)
        self.status_row.addWidget(self.status, 1)
        self.status_row.addWidget(self.progress)
        self.status_row.addWidget(self.progress_text)
        layout.addWidget(self.center)
        layout.addStretch(1)

        self.connection_glyph = GlyphLabel(G.NETWORK, 12, "#8d919a", 20)
        layout.addWidget(self.connection_glyph)
        connection_label.setObjectName("connectionState")
        layout.addWidget(connection_label)
        connection_label.stateChanged.connect(self._connection_state)

    def _connection_state(self, state: str):
        color = {"error": "#e0785f", "cache": "#d7b75a", "busy": "#9ecef6"}.get(state, "#8d919a")
        self.connection_glyph.set_color(color)


# ---------------------------------------------------------------------------
# launching installed games
# ---------------------------------------------------------------------------

class LaunchPicker(QDialog):
    """Asks once which executable starts the game."""

    def __init__(self, title: str, root: Path, candidates: list[Path], parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{title} nasıl başlatılsın?")
        self.setMinimumWidth(560)
        self._root = Path(root)
        self._chosen: Path | None = None
        self.browse_requested = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(12)
        layout.addWidget(make_label(title, "#ffffff", 18, 700))
        note = make_label(
            "Oyunu başlatan dosyayı seç. Seçimin bu oyun için hatırlanır; "
            "daha sonra Yönet menüsünden değiştirebilirsin.", T.TEXT_MUTED, 13)
        note.setWordWrap(True)
        layout.addWidget(note)
        self.list = QListWidget()
        self.list.setObjectName("launchList")
        self.list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list.setStyleSheet(
            "QListWidget#launchList { background: #15171b; border: 1px solid #0e1013; border-radius: 2px; }"
            "QListWidget#launchList::item { padding: 8px 10px; color: #dcdedf; }"
            "QListWidget#launchList::item:selected { background: #444e69; color: #ffffff; }"
            "QListWidget#launchList::item:hover { background: #2f333c; }"
        )
        for path in candidates:
            try:
                relative = path.relative_to(self._root).as_posix()
            except ValueError:
                relative = str(path)
            try:
                size = human_size(path.stat().st_size)
            except OSError:
                size = "-"
            item = QListWidgetItem(f"{relative}      {size}")
            item.setData(Qt.UserRole, str(path))
            self.list.addItem(item)
        if self.list.count():
            self.list.setCurrentRow(0)
        self.list.itemDoubleClicked.connect(lambda _item: self._accept())
        layout.addWidget(self.list, 1)
        buttons = QHBoxLayout()
        browse = QPushButton("Göz at…")
        browse.clicked.connect(self._browse)
        cancel = QPushButton("Vazgeç")
        cancel.clicked.connect(self.reject)
        start = QPushButton("Başlat")
        start.setObjectName("dlPlay")
        start.setDefault(True)
        start.clicked.connect(self._accept)
        buttons.addWidget(browse)
        buttons.addStretch(1)
        buttons.addWidget(cancel)
        buttons.addWidget(start)
        layout.addLayout(buttons)

    def _accept(self):
        item = self.list.currentItem()
        if item is not None:
            self._chosen = Path(item.data(Qt.UserRole))
            self.accept()

    def _browse(self):
        self.browse_requested = True
        self.reject()

    def chosen(self) -> Path | None:
        return self._chosen
