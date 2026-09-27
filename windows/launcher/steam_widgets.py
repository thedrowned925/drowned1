"""Shared building blocks for the v0.19 Steam-style launcher UI.

Pure presentation: no catalog, install or registry logic lives here. The
owner (app_v19.Launcher) pushes data in and listens to signals, the same
contract library_grid.py already follows.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from typing import Callable

from PySide6.QtCore import (
    QAbstractAnimation,
    QEasingCurve,
    QEvent,
    QObject,
    QPoint,
    QPropertyAnimation,
    QRect,
    QRectF,
    QRunnable,
    QSize,
    Qt,
    QThreadPool,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QFontMetrics,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QAbstractButton,
    QFrame,
    QGraphicsBlurEffect,
    QGraphicsOpacityEffect,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

import steam_theme as T
from steam_format import (  # noqa: F401 - re-exported for the page modules
    TR_MONTHS,
    human_size,
    long_date,
    parse_iso,
    short_date,
    time_bucket,
)
from steam_theme import G

# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------

def game_key_title(game: dict) -> str:
    return str(game.get("title") or game.get("id") or "")


def cover_crop(source: QPixmap, width: int, height: int, focus_x: float = 0.5, focus_y: float = 0.5,
               ratio: float = 1.0) -> QPixmap:
    """Scale-to-fill and crop around a focus point, at device resolution."""
    if source is None or source.isNull() or width <= 0 or height <= 0:
        return QPixmap()
    target_w = max(1, int(round(width * ratio)))
    target_h = max(1, int(round(height * ratio)))
    scaled = source.scaled(target_w, target_h, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    x = int(max(0, scaled.width() - target_w) * focus_x)
    y = int(max(0, scaled.height() - target_h) * focus_y)
    cropped = scaled.copy(x, y, target_w, target_h)
    cropped.setDevicePixelRatio(ratio)
    return cropped


def blurred_backdrop(source: QPixmap, width: int = 640, radius: float = 18.0) -> QPixmap:
    """The Steam game page paints a heavily blurred copy of the hero behind
    everything below the banner. Blur a small copy once; callers stretch it."""
    if source is None or source.isNull():
        return QPixmap()
    small = source.scaledToWidth(max(64, width), Qt.SmoothTransformation)
    scene = QGraphicsScene()
    item = QGraphicsPixmapItem(small)
    effect = QGraphicsBlurEffect()
    effect.setBlurRadius(radius)
    effect.setBlurHints(QGraphicsBlurEffect.QualityHint)
    item.setGraphicsEffect(effect)
    scene.addItem(item)
    image = QImage(small.size(), QImage.Format_ARGB32_Premultiplied)
    image.fill(QColor(T.PAGE_BASE))
    painter = QPainter(image)
    scene.render(painter, QRectF(0, 0, small.width(), small.height()), QRectF(0, 0, small.width(), small.height()))
    painter.end()
    return QPixmap.fromImage(image)


def compose_portrait(source: QPixmap, width: int = 300, height: int = 450) -> QPixmap:
    """A few catalog covers are landscape header art (460x215). Cropping
    those into a 2:3 capsule cuts the title in half, so build a portrait
    capsule instead: blurred art behind, the full image centred on top."""
    if source is None or source.isNull() or source.width() <= source.height():
        return source
    canvas = QPixmap(width, height)
    canvas.fill(QColor(T.PANEL))
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.SmoothPixmapTransform)
    backdrop = blurred_backdrop(source, 160, 8)
    if not backdrop.isNull():
        painter.drawPixmap(0, 0, cover_crop(backdrop, width, height))
    painter.fillRect(canvas.rect(), QColor(8, 10, 14, 120))
    fitted = source.scaledToWidth(width, Qt.SmoothTransformation)
    y = int(height * 0.42 - fitted.height() / 2)
    painter.drawPixmap(0, max(0, y), fitted)
    painter.end()
    return canvas


class CoverCache(dict):
    """url -> pixmap store shared with app_v10's `_tile_cover_cache`.
    Landscape covers are recomposed into portrait capsules on the way in,
    whichever loader (v0.19 hub or app_v10's Big Picture) fetched them."""

    def __setitem__(self, url, pixmap):
        if isinstance(pixmap, QPixmap) and not pixmap.isNull() and pixmap.width() > pixmap.height():
            pixmap = compose_portrait(pixmap)
        super().__setitem__(url, pixmap)


def device_ratio(widget: QWidget) -> float:
    try:
        return float(widget.devicePixelRatioF())
    except Exception:
        return 1.0


def rounded_path(rect: QRectF, radius: float) -> QPainterPath:
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    return path


def set_label_style(label: QLabel, color: str, px: float | None = None, weight: int = 400,
                    spacing: float = 0.0) -> QLabel:
    """Colour through a local style sheet, font through setFont (see the
    base-font note in steam_theme.V19_STYLE)."""
    label.setStyleSheet(f"color: {color}; background: transparent;")
    if px is not None:
        label.setFont(T.ui_font(px, weight, spacing=spacing))
    return label


def make_label(text: str, color: str = T.TEXT, px: float = 13, weight: int = 400,
               spacing: float = 0.0, parent=None) -> QLabel:
    label = QLabel(text, parent)
    return set_label_style(label, color, px, weight, spacing)


def icon_button(glyph: str, object_name: str, tooltip: str = "", px: float = 14,
                color: str = T.TEXT_MUTED, hover: str = T.TEXT, parent=None) -> QPushButton:
    button = QPushButton(parent)
    button.setObjectName(object_name)
    button.setIcon(T.glyph_icon(glyph, px, color, hover))
    button.setIconSize(QSize(int(px * 1.35), int(px * 1.35)))
    button.setCursor(Qt.PointingHandCursor)
    if tooltip:
        button.setToolTip(tooltip)
    return button


class DashLabel(QLabel):
    """The inherited backend writes "—" as its empty value. The v0.19 copy
    style uses a plain hyphen, so swap it on the way in."""

    def setText(self, text):  # noqa: N802 - Qt naming
        super().setText(str(text).replace("—", "-"))


class ClickableFrame(QFrame):
    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            event.accept()
            self.clicked.emit()
            return
        super().mousePressEvent(event)


# ---------------------------------------------------------------------------
# image loading
# ---------------------------------------------------------------------------


class _ImageSignals(QObject):
    done = Signal(str, str, object)  # kind, url, QImage | None


class _ImageTask(QRunnable):
    def __init__(self, kind: str, url: str, max_width: int, fetch: Callable[[str], bytes | None]):
        super().__init__()
        self.kind = kind
        self.url = url
        self.max_width = max_width
        self.fetch = fetch
        self.signals = _ImageSignals()

    def run(self):
        image = None
        try:
            raw = self.fetch(self.url)
            if raw:
                decoded = QImage()
                if decoded.loadFromData(raw):
                    if self.max_width and decoded.width() > self.max_width:
                        decoded = decoded.scaledToWidth(self.max_width, Qt.SmoothTransformation)
                    image = decoded
        except Exception:
            image = None
        try:
            self.signals.done.emit(self.kind, self.url, image)
        except RuntimeError:
            # The application is shutting down and the signal object is gone.
            pass


class ImageHub(QObject):
    """URL -> pixmap loader shared by every v0.19 widget.

    Decoding and downscaling happen on a small private thread pool, so the
    install/verify tasks in the launcher's main pool are never queued behind
    a wall of artwork requests, and big heroes/screenshots never stall the
    UI thread. `cover` and `icon` share one dict with app_v10's
    `_tile_cover_cache`, so Big Picture and the status bar reuse the same
    pixmaps instead of downloading them twice.
    """

    MAX_WIDTH = {"cover": 300, "icon": 0, "hero": 1920, "wide": 960, "logo": 900, "shot": 560, "shot_full": 1920}
    LIMIT = {"hero": 24, "wide": 80, "logo": 60, "shot": 160, "shot_full": 10}
    RETRY_AFTER = 90.0

    def __init__(self, fetch: Callable[[str], bytes | None], parent=None):
        super().__init__(parent)
        self._fetch = fetch
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(6)
        self.cover_cache: dict[str, QPixmap] = CoverCache()
        self._icon_cache: dict[str, QPixmap] = {}
        self._lru: dict[str, OrderedDict] = {kind: OrderedDict() for kind in self.LIMIT}
        self._waiting: dict[tuple[str, str], list[Callable]] = {}
        self._tasks: dict[tuple[str, str], _ImageTask] = {}
        self._failed: dict[tuple[str, str], float] = {}

    def _store(self, kind: str):
        if kind == "cover":
            return self.cover_cache
        if kind == "icon":
            return self._icon_cache
        return self._lru[kind]

    def failed(self, kind: str, url: str) -> bool:
        failed_at = self._failed.get((kind, url))
        return failed_at is not None and time.monotonic() - failed_at < self.RETRY_AFTER

    def pixmap(self, kind: str, url: str) -> QPixmap | None:
        if not url:
            return None
        store = self._store(kind)
        pixmap = store.get(url)
        if pixmap is not None and isinstance(store, OrderedDict):
            store.move_to_end(url)
        return pixmap

    def request(self, kind: str, url: str, callback: Callable[[str, QPixmap | None], None] | None = None):
        """Return the cached pixmap now, or schedule a load and call
        `callback(url, pixmap_or_None)` on the UI thread later."""
        if not url:
            return None
        cached = self.pixmap(kind, url)
        if cached is not None:
            return cached
        token = (kind, url)
        failed_at = self._failed.get(token)
        if failed_at is not None and time.monotonic() - failed_at < self.RETRY_AFTER:
            return None
        waiters = self._waiting.setdefault(token, [])
        if callback is not None:
            waiters.append(callback)
        if token not in self._tasks:
            task = _ImageTask(kind, url, self.MAX_WIDTH.get(kind, 0), self._fetch)
            task.signals.done.connect(self._loaded)
            self._tasks[token] = task
            self._pool.start(task)
        return None

    def _loaded(self, kind: str, url: str, image):
        token = (kind, url)
        self._tasks.pop(token, None)
        callbacks = self._waiting.pop(token, [])
        pixmap = None
        if image is not None and not image.isNull():
            store = self._store(kind)
            store[url] = QPixmap.fromImage(image)
            pixmap = store[url]
            if isinstance(store, OrderedDict):
                limit = self.LIMIT.get(kind, 64)
                while len(store) > limit:
                    store.popitem(last=False)
            self._failed.pop(token, None)
        else:
            self._failed[token] = time.monotonic()
        for callback in callbacks:
            try:
                callback(url, pixmap)
            except RuntimeError:
                # Receiver widget was deleted while the image was in flight.
                continue

    def put(self, kind: str, url: str, pixmap: QPixmap):
        """Adopt a pixmap decoded elsewhere (app_v4's artwork task) so the
        next visit to the same game paints instantly."""
        if not url or pixmap is None or pixmap.isNull():
            return
        store = self._store(kind)
        store[url] = pixmap
        if isinstance(store, OrderedDict):
            limit = self.LIMIT.get(kind, 64)
            while len(store) > limit:
                store.popitem(last=False)

    def shutdown(self):
        self._pool.clear()
        self._pool.waitForDone(1500)


# ---------------------------------------------------------------------------
# page stack with a short cross-fade
# ---------------------------------------------------------------------------


class CrossFadeStack(QStackedWidget):
    """Fades the incoming page in (state-change feedback), then removes the
    opacity effect so the page is not rendered through an offscreen buffer
    for the rest of its life."""

    DURATION = 170

    def setCurrentIndex(self, index: int):  # noqa: N802 - Qt naming
        if index == self.currentIndex() or index < 0 or index >= self.count() or not T.animations_enabled():
            super().setCurrentIndex(index)
            return
        super().setCurrentIndex(index)
        page = self.currentWidget()
        if page is None or page.graphicsEffect() is not None:
            return
        effect = QGraphicsOpacityEffect(page)
        effect.setOpacity(0.0)
        page.setGraphicsEffect(effect)
        animation = QPropertyAnimation(effect, b"opacity", self)
        animation.setDuration(self.DURATION)
        animation.setStartValue(0.0)
        animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.OutCubic)

        def _cleanup(target=page):
            try:
                target.setGraphicsEffect(None)
            except RuntimeError:
                pass

        animation.finished.connect(_cleanup)
        animation.start(QAbstractAnimation.DeleteWhenStopped)

    def setCurrentWidget(self, widget):  # noqa: N802 - Qt naming
        index = self.indexOf(widget)
        if index >= 0:
            self.setCurrentIndex(index)


# ---------------------------------------------------------------------------
# chrome: brand mark, nav tabs, account pill, window buttons, title bar
# ---------------------------------------------------------------------------


def paint_brand(painter: QPainter, rect: QRectF):
    """Single geometric mark standing in for Steam's logo."""
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setRenderHint(QPainter.TextAntialiasing)
    gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
    gradient.setColorAt(0.0, QColor("#6fc3f7"))
    gradient.setColorAt(1.0, QColor("#1a73d9"))
    painter.setPen(Qt.NoPen)
    painter.setBrush(gradient)
    painter.drawEllipse(rect)
    painter.setPen(QColor("#ffffff"))
    painter.setFont(T.ui_font(rect.height() * 0.62, 800))
    painter.drawText(rect, Qt.AlignCenter, "D")


def brand_pixmap(size: int) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    paint_brand(painter, QRectF(0.5, 0.5, size - 1, size - 1))
    painter.end()
    return pixmap


class BrandMark(QWidget):
    def __init__(self, size: int = 16, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)

    def paintEvent(self, event):
        painter = QPainter(self)
        paint_brand(painter, QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5))
        painter.end()


class NavTab(QWidget):
    """STORE / LIBRARY / COMMUNITY style top navigation entry."""

    clicked = Signal()

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self._text = text
        self._active = False
        self._hover = False
        self._font = T.ui_font(19, 700, spacing=0.2, display=True)
        metrics = QFontMetrics(self._font)
        self.setFixedSize(metrics.horizontalAdvance(text) + 6, 48)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover, True)
        self.setAccessibleName(text)

    def text(self) -> str:
        return self._text

    def setActive(self, active: bool):  # noqa: N802 - Qt naming
        if self._active != active:
            self._active = active
            self.update()

    def isActive(self) -> bool:  # noqa: N802 - Qt naming
        return self._active

    def event(self, event):
        if event.type() == QEvent.HoverEnter:
            self._hover = True
            self.update()
        elif event.type() == QEvent.HoverLeave:
            self._hover = False
            self.update()
        return super().event(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            event.accept()
            self.clicked.emit()
            return
        super().mousePressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        painter.setFont(self._font)
        if self._active:
            color = QColor(T.NAV_ACTIVE)
        elif self._hover:
            color = QColor("#ffffff")
        else:
            color = QColor(T.NAV_TEXT)
        painter.setPen(color)
        text_rect = QRectF(0, 0, self.width(), self.height() - 6)
        painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, self._text)
        if self._active:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(T.NAV_ACTIVE))
            metrics = QFontMetrics(self._font)
            width = metrics.horizontalAdvance(self._text)
            painter.drawRoundedRect(QRectF(1, self.height() - 11, width - 2, 3), 1.5, 1.5)
        painter.end()


class AccountPill(QPushButton):
    """Steam's avatar + blue name + grey wallet pill, reused for the catalog
    source (owner name + game count)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("accountPill")
        self.setCursor(Qt.PointingHandCursor)
        self._name = ""
        self._meta = ""
        self._name_font = T.ui_font(13, 600)
        self._meta_font = T.ui_font(12, 400)

    def set_account(self, name: str, meta: str):
        self._name = name
        self._meta = meta
        self.updateGeometry()
        self.update()

    def sizeHint(self):  # noqa: N802 - Qt naming
        name_w = QFontMetrics(self._name_font).horizontalAdvance(self._name)
        meta_w = QFontMetrics(self._meta_font).horizontalAdvance(self._meta)
        return QSize(4 + 18 + 8 + name_w + 14 + meta_w + 10, 24)

    def minimumSizeHint(self):  # noqa: N802 - Qt naming
        return self.sizeHint()

    def paintEvent(self, event):
        super().paintEvent(event)  # background from the style sheet
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        avatar = QRectF(4, 3, 18, 18)
        gradient = QLinearGradient(avatar.topLeft(), avatar.bottomRight())
        gradient.setColorAt(0.0, QColor("#4f94bc"))
        gradient.setColorAt(1.0, QColor("#2c5a86"))
        painter.setPen(Qt.NoPen)
        painter.setBrush(gradient)
        painter.drawRoundedRect(avatar, 2, 2)
        painter.setPen(QColor("#ffffff"))
        painter.setFont(T.ui_font(11, 700))
        painter.drawText(avatar, Qt.AlignCenter, (self._name[:1] or "D").upper())
        x = avatar.right() + 8
        painter.setFont(self._name_font)
        painter.setPen(QColor(T.ACCOUNT_BLUE))
        name_w = QFontMetrics(self._name_font).horizontalAdvance(self._name)
        painter.drawText(QRectF(x, 0, name_w + 2, self.height()), Qt.AlignVCenter | Qt.AlignLeft, self._name)
        x += name_w + 4
        painter.setFont(T.icon_font(8))
        painter.drawText(QRectF(x, 0, 10, self.height()), Qt.AlignCenter, G.CHEVRON_DOWN)
        x += 12
        painter.setFont(self._meta_font)
        painter.setPen(QColor("#808791"))
        painter.drawText(QRectF(x, 0, self.width() - x, self.height()), Qt.AlignVCenter | Qt.AlignLeft, self._meta)
        painter.end()


class SteamTitleBar(QFrame):
    """Frameless window chrome: menu row + primary navigation row.

    Empty chrome area drags the window (native move loop, so Windows snap
    still works), a double click toggles maximise, and the top-right
    cluster carries the Big Picture button and window controls the way the
    Steam client does.
    """

    navRequested = Signal(str)
    backRequested = Signal()
    forwardRequested = Signal()

    def __init__(self, window: QWidget, parent=None):
        super().__init__(parent)
        self.setObjectName("steamChrome")
        self._window = window
        self._press_pos: QPoint | None = None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # -- menu row ------------------------------------------------------
        menu_row = QHBoxLayout()
        menu_row.setContentsMargins(10, 0, 0, 0)
        menu_row.setSpacing(1)
        menu_row.addWidget(BrandMark(16))
        menu_row.addSpacing(3)
        self.menus: dict[str, QMenu] = {}
        for key, text in (("app", "Drowned"), ("view", "Görünüm"), ("games", "Oyunlar"), ("help", "Yardım")):
            button = QPushButton(text)
            button.setObjectName("chromeMenu")
            button.setCursor(Qt.PointingHandCursor)
            menu = QMenu(button)
            button.setMenu(menu)
            self.menus[key] = menu
            menu_row.addWidget(button)
        menu_row.addStretch(1)

        self.settings_button = icon_button(G.SETTINGS, "chromeBox", "Ayarlar", 13)
        menu_row.addWidget(self.settings_button)
        menu_row.addSpacing(6)
        self.account_button = AccountPill()
        self.account_menu = QMenu(self.account_button)
        self.account_button.setMenu(self.account_menu)
        menu_row.addWidget(self.account_button)
        menu_row.addSpacing(8)
        self.big_picture_button = icon_button(G.MONITOR, "chromeFlat", "Big Picture modu (F11)", 15)
        menu_row.addWidget(self.big_picture_button)
        menu_row.addSpacing(6)
        self.min_button = icon_button(G.MINIMIZE, "windowButton", "Simge durumuna küçült", 10)
        self.max_button = icon_button(G.MAXIMIZE, "windowButton", "Ekranı kapla", 10)
        self.close_button = icon_button(G.CLOSE, "windowClose", "Kapat", 10, hover="#ffffff")
        for button in (self.min_button, self.max_button, self.close_button):
            button.setFocusPolicy(Qt.NoFocus)
            menu_row.addWidget(button, 0, Qt.AlignTop)
        self.min_button.clicked.connect(self._window.showMinimized)
        self.max_button.clicked.connect(self.toggle_maximized)
        self.close_button.clicked.connect(self._window.close)
        outer.addLayout(menu_row)

        # -- navigation row ---------------------------------------------
        nav_row = QHBoxLayout()
        nav_row.setContentsMargins(12, 0, 16, 0)
        nav_row.setSpacing(2)
        self.back_button = icon_button(G.BACK, "chromeFlat", "Geri (Alt+Sol)", 14, hover="#ffffff")
        self.forward_button = icon_button(G.FORWARD, "chromeFlat", "İleri (Alt+Sağ)", 14, hover="#ffffff")
        self.back_button.clicked.connect(self.backRequested)
        self.forward_button.clicked.connect(self.forwardRequested)
        nav_row.addWidget(self.back_button)
        nav_row.addWidget(self.forward_button)
        nav_row.addSpacing(14)
        self.tabs: dict[str, NavTab] = {}
        for key, text in (("store", "MAĞAZA"), ("library", "KÜTÜPHANE"), ("downloads", "İNDİRMELER")):
            tab = NavTab(text)
            tab.clicked.connect(lambda k=key: self.navRequested.emit(k))
            self.tabs[key] = tab
            nav_row.addWidget(tab)
            nav_row.addSpacing(22)
        nav_row.addStretch(1)
        outer.addLayout(nav_row)
        self.setFixedHeight(30 + 48)

    def set_active_tab(self, key: str):
        for name, tab in self.tabs.items():
            tab.setActive(name == key)

    def set_history_state(self, can_back: bool, can_forward: bool):
        self.back_button.setEnabled(can_back)
        self.forward_button.setEnabled(can_forward)

    def sync_window_state(self):
        maximized = self._window.isMaximized()
        glyph = G.RESTORE if maximized else G.MAXIMIZE
        self.max_button.setIcon(T.glyph_icon(glyph, 10, T.TEXT_MUTED, T.TEXT))
        self.max_button.setToolTip("Önceki boyut" if maximized else "Ekranı kapla")

    def toggle_maximized(self):
        if self._window.isFullScreen():
            return
        if self._window.isMaximized():
            self._window.showNormal()
        else:
            self._window.showMaximized()

    # -- dragging ------------------------------------------------------
    # The native move loop starts only after a few pixels of movement, so a
    # plain double click still reaches mouseDoubleClickEvent.
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and not self._window.isFullScreen():
            self._press_pos = event.position().toPoint()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._press_pos is not None and event.buttons() & Qt.LeftButton:
            if (event.position().toPoint() - self._press_pos).manhattanLength() > 4:
                if self._window.isMaximized():
                    # Dragging a maximised window: restore under the cursor
                    # first, keeping the grab point proportionally in place.
                    ratio = self._press_pos.x() / max(1, self.width())
                    global_pos = event.globalPosition().toPoint()
                    self._window.showNormal()
                    width = self._window.width()
                    self._window.move(int(global_pos.x() - width * ratio),
                                      max(0, global_pos.y() - self._press_pos.y()))
                self._press_pos = None
                handle = self._window.windowHandle()
                if handle is not None:
                    handle.startSystemMove()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._press_pos = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.toggle_maximized()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


class ResizeGrip(QWidget):
    def __init__(self, parent: QWidget, edges, cursor):
        super().__init__(parent)
        self._edges = edges
        self.setCursor(cursor)
        self.setMouseTracking(True)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            handle = self.window().windowHandle()
            if handle is not None:
                handle.startSystemResize(self._edges)
            event.accept()
            return
        super().mousePressEvent(event)


class EdgeGrips:
    """Invisible resize handles on the edges of the frameless window."""

    THICKNESS = 5
    CORNER = 12

    def __init__(self, host: QWidget):
        self._host = host
        edge = Qt.Edge
        self._grips = {
            "left": ResizeGrip(host, edge.LeftEdge, Qt.SizeHorCursor),
            "right": ResizeGrip(host, edge.RightEdge, Qt.SizeHorCursor),
            "top": ResizeGrip(host, edge.TopEdge, Qt.SizeVerCursor),
            "bottom": ResizeGrip(host, edge.BottomEdge, Qt.SizeVerCursor),
            "top_left": ResizeGrip(host, edge.TopEdge | edge.LeftEdge, Qt.SizeFDiagCursor),
            "bottom_right": ResizeGrip(host, edge.BottomEdge | edge.RightEdge, Qt.SizeFDiagCursor),
            "top_right": ResizeGrip(host, edge.TopEdge | edge.RightEdge, Qt.SizeBDiagCursor),
            "bottom_left": ResizeGrip(host, edge.BottomEdge | edge.LeftEdge, Qt.SizeBDiagCursor),
        }

    def update_geometry(self):
        rect = self._host.rect()
        t, c = self.THICKNESS, self.CORNER
        w, h = rect.width(), rect.height()
        g = self._grips
        g["left"].setGeometry(0, c, t, max(0, h - 2 * c))
        g["right"].setGeometry(w - t, c, t, max(0, h - 2 * c))
        g["top"].setGeometry(c, 0, max(0, w - 2 * c), t)
        g["bottom"].setGeometry(c, h - t, max(0, w - 2 * c), t)
        g["top_left"].setGeometry(0, 0, c, c)
        g["top_right"].setGeometry(w - c, 0, c, c)
        g["bottom_left"].setGeometry(0, h - c, c, c)
        g["bottom_right"].setGeometry(w - c, h - c, c, c)
        for grip in g.values():
            grip.raise_()

    def set_enabled(self, enabled: bool):
        for grip in self._grips.values():
            grip.setVisible(enabled)
            if enabled:
                grip.raise_()


# ---------------------------------------------------------------------------
# game-page primitives
# ---------------------------------------------------------------------------


class SteamActionButton(QAbstractButton):
    """The big PLAY / INSTALL / UPDATE button.

    Colours follow the Steam client: green gradient for PLAY, blue for
    anything that downloads (install, update, resume), flat slate while
    busy. A focus ring keeps it usable with keyboard and gamepad.
    """

    MODES = {
        "play": (T.PLAY_LEFT, T.PLAY_RIGHT, G.PLAY_SOLID),
        "install": (T.INSTALL_LEFT, T.INSTALL_RIGHT, G.DOWNLOAD),
        "pause": (T.INSTALL_LEFT, T.INSTALL_RIGHT, G.PAUSE_SOLID),
        "resume": (T.INSTALL_LEFT, T.INSTALL_RIGHT, G.PLAY_SOLID),
        "busy": ("#3d4450", "#353b46", G.SYNC),
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mode = "install"
        self._hover = False
        self._font = T.ui_font(16, 500, spacing=1.1)
        self.setText("YÜKLE")
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAttribute(Qt.WA_Hover, True)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

    def mode(self) -> str:
        return self._mode

    def set_state(self, mode: str, text: str, enabled: bool):
        changed = (mode, text, enabled) != (self._mode, self.text(), self.isEnabled())
        self._mode = mode if mode in self.MODES else "install"
        self.setText(text)
        self.setEnabled(enabled)
        self.setCursor(Qt.PointingHandCursor if enabled else Qt.ArrowCursor)
        if changed:
            self.updateGeometry()
            self.update()

    def sizeHint(self):  # noqa: N802 - Qt naming
        text_w = QFontMetrics(self._font).horizontalAdvance(self.text())
        return QSize(max(176, 28 + 18 + 12 + text_w + 32), 48)

    def minimumSizeHint(self):  # noqa: N802 - Qt naming
        return self.sizeHint()

    def event(self, event):
        if event.type() == QEvent.HoverEnter:
            self._hover = True
            self.update()
        elif event.type() == QEvent.HoverLeave:
            self._hover = False
            self.update()
        return super().event(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        left, right, glyph = self.MODES.get(self._mode, self.MODES["install"])
        enabled = self.isEnabled()
        if not enabled and self._mode != "busy":
            left, right = "#3d4450", "#353b46"
        left_c, right_c = QColor(left), QColor(right)
        if enabled and self.isDown():
            left_c, right_c = left_c.darker(112), right_c.darker(112)
        elif enabled and self._hover:
            left_c, right_c = left_c.lighter(112), right_c.lighter(112)
        gradient = QLinearGradient(rect.topLeft(), rect.topRight())
        gradient.setColorAt(0.0, left_c)
        gradient.setColorAt(1.0, right_c)
        painter.setPen(Qt.NoPen)
        painter.setBrush(gradient)
        painter.drawRoundedRect(rect, 3, 3)
        if enabled and self._mode != "busy":
            sheen = QLinearGradient(rect.topLeft(), rect.bottomLeft())
            sheen.setColorAt(0.0, QColor(255, 255, 255, 34))
            sheen.setColorAt(0.5, QColor(255, 255, 255, 0))
            painter.setBrush(sheen)
            painter.drawRoundedRect(rect, 3, 3)
        if self.hasFocus() and self.focusPolicy() != Qt.NoFocus:
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor(255, 255, 255, 220), 2))
            painter.drawRoundedRect(rect.adjusted(2, 2, -2, -2), 2, 2)

        text_color = QColor("#ffffff") if enabled else QColor("#9aa1ab")
        metrics = QFontMetrics(self._font)
        text_w = metrics.horizontalAdvance(self.text())
        content_w = 18 + 12 + text_w
        x = (rect.width() - content_w) / 2
        painter.setFont(T.icon_font(15))
        shadow = QColor(0, 0, 0, 70 if enabled else 0)
        painter.setPen(shadow)
        painter.drawText(QRectF(x, 1, 18, rect.height()), Qt.AlignCenter, glyph)
        painter.setPen(text_color)
        painter.drawText(QRectF(x, 0, 18, rect.height()), Qt.AlignCenter, glyph)
        painter.setFont(self._font)
        text_rect = QRectF(x + 30, 0, text_w + 4, rect.height())
        painter.setPen(shadow)
        painter.drawText(text_rect.translated(0, 1), Qt.AlignVCenter | Qt.AlignLeft, self.text())
        painter.setPen(text_color)
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, self.text())
        painter.end()


class StatBlock(QWidget):
    """CLOUD STATUS / LAST PLAYED style stat next to the PLAY button."""

    def __init__(self, glyph: str, caption: str, value_label: QLabel, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        self.icon = QLabel()
        self.icon.setPixmap(T.glyph_pixmap(glyph, 18, "#8b929a", 26))
        self.icon.setFixedSize(26, 26)
        layout.addWidget(self.icon, 0, Qt.AlignVCenter)
        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(1)
        self.caption = make_label(caption, T.STAT_LABEL, 11, 700, spacing=0.8)
        value_label.setStyleSheet(f"color: {T.TEXT_MUTED}; background: transparent;")
        value_label.setFont(T.ui_font(12))
        self.value = value_label
        column.addWidget(self.caption)
        column.addWidget(value_label)
        layout.addLayout(column)

    def set_icon(self, glyph: str, color: str = "#8b929a"):
        if getattr(self, "_icon_state", None) != (glyph, color):
            self._icon_state = (glyph, color)
            self.icon.setPixmap(T.glyph_pixmap(glyph, 18, color, 26))


class SectionHeader(QWidget):
    """Uppercase section caption, optional count and a hairline that runs to
    the right edge, plus any extra widgets pinned to the right."""

    def __init__(self, title: str, *, line: bool = True, px: float = 13, color: str = T.SECTION_TEXT,
                 parent=None):
        super().__init__(parent)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(8)
        self.title = make_label(title.upper(), color, px, 700, spacing=1.2)
        self.count = make_label("", T.TEXT_FAINT, px, 700, spacing=1.0)
        self.count.hide()
        self._layout.addWidget(self.title)
        self._layout.addWidget(self.count)
        if line:
            self.line = QFrame()
            self.line.setFixedHeight(1)
            self.line.setStyleSheet("background: rgba(255, 255, 255, 22);")
            self._layout.addWidget(self.line, 1, Qt.AlignVCenter)
        else:
            self.line = None
            self._layout.addStretch(1)

    def set_title(self, title: str):
        self.title.setText(title.upper())

    def set_count(self, count: int | None):
        if count is None:
            self.count.hide()
        else:
            self.count.setText(f"({count})")
            self.count.show()

    def add_right(self, widget: QWidget):
        self._layout.addWidget(widget, 0, Qt.AlignVCenter)


class ConnectionLabel(QLabel):
    """Backend writes "RAW • çevrimiçi" style strings; the state property
    lets the style sheet colour errors and cache fallbacks."""

    stateChanged = Signal(str)

    def setText(self, text):  # noqa: N802 - Qt naming
        text = str(text)
        super().setText(text)
        lowered = text.lower()
        if "hata" in lowered:
            state = "error"
        elif "cache" in lowered:
            state = "cache"
        elif "çevrimiçi" in lowered:
            state = "online"
        else:
            state = "busy"
        if self.property("state") != state:
            self.setProperty("state", state)
            self.style().unpolish(self)
            self.style().polish(self)
        self.stateChanged.emit(state)


class GlyphLabel(QLabel):
    def __init__(self, glyph: str, px: float, color: str, box: int | None = None, parent=None):
        super().__init__(parent)
        self._glyph, self._px, self._box = glyph, px, box
        self.set_color(color)

    def set_color(self, color: str, glyph: str | None = None):
        if glyph:
            self._glyph = glyph
        pixmap = T.glyph_pixmap(self._glyph, self._px, color, self._box)
        self.setPixmap(pixmap)
        self.setFixedSize(pixmap.size() / max(1.0, pixmap.devicePixelRatio()))


def placeholder_art(painter: QPainter, rect: QRectF, title: str, seed: str = "", radius: float = 0.0):
    """Dark gradient plate with the title, for games whose art is missing."""
    hue = (sum(ord(ch) for ch in (seed or title)) * 37) % 360
    top = QColor.fromHsv(hue, 60, 70)
    bottom = QColor.fromHsv((hue + 30) % 360, 70, 38)
    gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
    gradient.setColorAt(0.0, top)
    gradient.setColorAt(1.0, bottom)
    painter.save()
    if radius:
        painter.setClipPath(rounded_path(rect, radius))
    painter.fillRect(rect, gradient)
    painter.setPen(QColor(255, 255, 255, 200))
    size = max(9.0, min(18.0, rect.width() / 9))
    painter.setFont(T.ui_font(size, 700))
    painter.drawText(rect.adjusted(10, 10, -10, -10), Qt.AlignCenter | Qt.TextWordWrap, title)
    painter.restore()


def paint_shimmer(painter: QPainter, rect: QRectF, phase: float, radius: float = 0.0, base: str = "#2a2d34"):
    painter.save()
    if radius:
        painter.setClipPath(rounded_path(rect, radius))
    painter.fillRect(rect, QColor(base))
    band = max(rect.width() * 0.6, 1.0)
    x = rect.x() - band + (rect.width() + band * 2) * phase
    gradient = QLinearGradient(x, rect.y(), x + band, rect.y() + rect.height())
    gradient.setColorAt(0.0, QColor(255, 255, 255, 0))
    gradient.setColorAt(0.5, QColor(255, 255, 255, 16))
    gradient.setColorAt(1.0, QColor(255, 255, 255, 0))
    painter.fillRect(rect, gradient)
    painter.restore()


def elide(text: str, font, width: float) -> str:
    return QFontMetrics(font).elidedText(text, Qt.ElideRight, max(0, int(width)))


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def rect_i(rect: QRectF) -> QRect:
    return rect.toAlignedRect()
