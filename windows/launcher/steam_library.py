"""Steam-style library surfaces for v0.19: the left game list, the library
home (shelf + collection wall) and the capsule painting they share.

`SteamLibraryList` exposes the exact view API app_v10/app_v11 drive their
library views with (set_items / set_current_row / set_source_rows /
selectionChanged / gameActivated / ...), so it can be installed as
`Launcher.library_grid` without touching any inherited method.
"""

from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QPoint,
    QPointF,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    QTimer,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import QAction, QColor, QFontMetrics, QLinearGradient, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

import steam_theme as T
from steam_theme import G
from steam_widgets import (
    ImageHub,
    SectionHeader,
    clamp,
    cover_crop,
    device_ratio,
    elide,
    icon_button,
    make_label,
    paint_shimmer,
    placeholder_art,
    rounded_path,
)

# ---------------------------------------------------------------------------
# shared capsule painting
# ---------------------------------------------------------------------------


def paint_capsule_shadow(painter: QPainter, rect: QRectF, hover: float, radius: float = 3.0):
    painter.save()
    painter.setPen(Qt.NoPen)
    spread = 2.0 + 8.0 * hover
    for step in range(4):
        grow = spread * (step + 1) / 4.0
        alpha = int((26 + 30 * hover) * (1.0 - step / 4.0))
        painter.setBrush(QColor(0, 0, 0, alpha))
        painter.drawRoundedRect(rect.adjusted(-grow * 0.6, -grow * 0.2 + 2, grow * 0.6, grow + 2), radius + grow,
                                radius + grow)
    painter.restore()


def paint_capsule(
    painter: QPainter,
    rect: QRectF,
    art: QPixmap | None,
    *,
    title: str = "",
    seed: str = "",
    hover: float = 0.0,
    glare_x: float = 0.5,
    radius: float = 3.0,
    badge: str = "",
    progress: int | None = None,
    action: str | None = None,
    loading: bool = False,
    shimmer: float = 0.0,
    logo: QPixmap | None = None,
):
    """One library capsule: art, hover light, badge, download bar and the
    round PLAY/INSTALL button Steam shows on hover."""
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setRenderHint(QPainter.SmoothPixmapTransform)
    painter.setClipPath(rounded_path(rect, radius))
    if art is not None and not art.isNull():
        painter.drawPixmap(rect, art, QRectF(art.rect()))
    elif loading:
        paint_shimmer(painter, rect, shimmer)
    else:
        placeholder_art(painter, rect, title, seed)

    if logo is not None and not logo.isNull():
        shade = QLinearGradient(rect.bottomLeft(), rect.topLeft())
        shade.setColorAt(0.0, QColor(0, 0, 0, 170))
        shade.setColorAt(0.55, QColor(0, 0, 0, 0))
        painter.fillRect(rect, shade)
        max_w, max_h = rect.width() * 0.55, rect.height() * 0.38
        scale = min(max_w / max(1, logo.width()), max_h / max(1, logo.height()))
        lw, lh = logo.width() * scale, logo.height() * scale
        painter.drawPixmap(QRectF(rect.x() + 14, rect.bottom() - lh - 14, lw, lh), logo, QRectF(logo.rect()))

    if hover > 0.001:
        painter.fillRect(rect, QColor(255, 255, 255, int(14 * hover)))
        # Glare band that follows the cursor, like the library's lit tiles.
        cx = rect.x() + rect.width() * glare_x
        glare = QLinearGradient(QPointF(cx - rect.width() * 0.6, rect.y()), QPointF(cx + rect.width() * 0.6, rect.bottom()))
        glare.setColorAt(0.0, QColor(255, 255, 255, 0))
        glare.setColorAt(0.5, QColor(255, 255, 255, int(46 * hover)))
        glare.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.fillRect(rect, glare)

    if badge:
        font = T.ui_font(10, 700, spacing=0.6)
        painter.setFont(font)
        width = QFontMetrics(font).horizontalAdvance(badge) + 14
        badge_rect = QRectF(rect.x(), rect.y() + 10, width, 18)
        painter.fillRect(badge_rect, QColor(T.ACCENT))
        painter.setPen(QColor("#ffffff"))
        painter.drawText(badge_rect, Qt.AlignCenter, badge)

    if progress is not None:
        bar = QRectF(rect.x(), rect.bottom() - 5, rect.width(), 5)
        painter.fillRect(bar, QColor(0, 0, 0, 190))
        painter.fillRect(QRectF(bar.x(), bar.y(), bar.width() * clamp(progress, 0, 100) / 100.0, bar.height()),
                         QColor(T.ACCENT))
    painter.restore()

    if action and hover > 0.05:
        paint_round_action(painter, action_rect(rect), action, hover)


def action_rect(rect: QRectF) -> QRectF:
    size = clamp(rect.width() * 0.24, 30, 42)
    return QRectF(rect.x() + 10, rect.bottom() - size - 12, size, size)


def paint_round_action(painter: QPainter, rect: QRectF, action: str, opacity: float = 1.0):
    painter.save()
    painter.setOpacity(clamp(opacity, 0.0, 1.0))
    painter.setRenderHint(QPainter.Antialiasing)
    if action == "play":
        left, right, glyph = T.PLAY_LEFT, T.PLAY_RIGHT, G.PLAY_SOLID
    else:
        left, right, glyph = T.INSTALL_LEFT, T.INSTALL_RIGHT, G.DOWNLOAD
    gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
    gradient.setColorAt(0.0, QColor(left))
    gradient.setColorAt(1.0, QColor(right))
    painter.setPen(QPen(QColor(0, 0, 0, 90), 1))
    painter.setBrush(gradient)
    painter.drawEllipse(rect)
    painter.setPen(QColor("#ffffff"))
    painter.setFont(T.icon_font(rect.width() * 0.38))
    painter.drawText(rect.translated(1 if action == "play" else 0, 0), Qt.AlignCenter, glyph)
    painter.restore()


class _HoverTracker:
    """Eases per-item hover amounts toward their targets with one timer."""

    def __init__(self, owner: QWidget, repaint):
        self._amounts: dict[str, float] = {}
        self._targets: dict[str, float] = {}
        self._repaint = repaint
        self._timer = QTimer(owner)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._step)

    def amount(self, key: str) -> float:
        return self._amounts.get(key, 0.0)

    def set_hover(self, key: str | None):
        for other in list(self._targets):
            if other != key:
                self._targets[other] = 0.0
        if key is not None:
            self._targets[key] = 1.0
        if not T.animations_enabled():
            for name, target in self._targets.items():
                self._amounts[name] = target
                self._repaint(name)
            self._prune()
            return
        if not self._timer.isActive():
            self._timer.start()

    def _prune(self):
        for name in [n for n, t in self._targets.items() if t == 0.0 and self._amounts.get(n, 0.0) <= 0.001]:
            self._targets.pop(name, None)
            self._amounts.pop(name, None)

    def _step(self):
        busy = False
        for name, target in list(self._targets.items()):
            current = self._amounts.get(name, 0.0)
            nxt = current + (target - current) * 0.28
            if abs(target - nxt) < 0.01:
                nxt = target
            else:
                busy = True
            self._amounts[name] = nxt
            self._repaint(name)
        self._prune()
        if not busy:
            self._timer.stop()


class _Shimmer:
    def __init__(self, owner: QWidget):
        self.phase = 0.0
        self._owner = owner
        self._anim = QVariantAnimation(owner)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setDuration(1300)
        self._anim.setLoopCount(-1)
        self._anim.valueChanged.connect(self._tick)

    def _tick(self, value):
        self.phase = float(value)
        self._owner.update()

    def run(self, active: bool):
        if active and T.animations_enabled():
            if self._anim.state() != QVariantAnimation.Running:
                self._anim.start()
        else:
            self._anim.stop()
            self.phase = 0.35


# ---------------------------------------------------------------------------
# left game list
# ---------------------------------------------------------------------------

GROUPS = (("fav", "FAVORİLER"), ("installed", "YÜKLÜ"), ("other", "YÜKLENEBİLİR"))


class _ListCanvas(QWidget):
    def __init__(self, owner: "SteamLibraryList"):
        super().__init__()
        self._owner = owner
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAttribute(Qt.WA_Hover, True)

    def paintEvent(self, event):
        self._owner._paint(self, event.rect())

    def mouseMoveEvent(self, event):
        self._owner._hover_at(event.position().toPoint())

    def leaveEvent(self, event):
        self._owner._hover_at(None)
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        self._owner._press(event)

    def mouseDoubleClickEvent(self, event):
        self._owner._double(event)

    def keyPressEvent(self, event):
        if not self._owner._key(event):
            super().keyPressEvent(event)

    def event(self, event):
        if event.type() == QEvent.ToolTip:
            self._owner._tooltip(event)
            return True
        return super().event(event)


class SteamLibraryList(QScrollArea):
    """The Steam client's left game list: collapsible groups, square icons,
    grey titles for games that are not installed and a blue status suffix
    for downloads and pending updates. One painted canvas, so filtering 100+
    games re-renders instantly."""

    tileActivated = Signal(int)
    coverRequested = Signal(str, str)
    selectionChanged = Signal(int)
    gameActivated = Signal(int)
    rowClicked = Signal(int)
    rowDoubleClicked = Signal(int)
    rowContextMenu = Signal(int, QPoint)

    ROW_H = 28
    HEADER_H = 30

    def __init__(self, images: ImageHub, parent=None):
        super().__init__(parent)
        self._images = images
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._canvas = _ListCanvas(self)
        self.setWidget(self._canvas)
        self.setFocusProxy(self._canvas)
        self._entries: dict[str, dict] = {}
        self._order: list[str] = []
        self._display: list[tuple] = []
        self._tops: list[int] = []
        self._current_key: str | None = None
        self._hover_index = -1
        self._collapsed: set[str] = set()
        self._progress: dict[str, int] = {}
        self._icons: dict[str, QPixmap] = {}
        self._state_provider = lambda key: {}
        self._sort_mode = "alpha"
        self._installed_only = False
        self._skeleton = 0
        self._empty_text = ""
        self._shimmer = _Shimmer(self._canvas)
        self._title_font = T.ui_font(13)
        self._suffix_font = T.ui_font(13)
        self._header_font = T.ui_font(12, 700, spacing=0.6)

    def keyPressEvent(self, event):  # noqa: N802 - Qt naming
        # app_v10's controller code sends arrow/Return key events straight to
        # the view object, not to the canvas that normally has focus.
        if not self._key(event):
            super().keyPressEvent(event)

    # -- configuration --------------------------------------------------
    def set_state_provider(self, provider):
        self._state_provider = provider

    def set_sort_mode(self, mode: str):
        self._sort_mode = mode
        self._rebuild()

    def set_installed_only(self, value: bool):
        self._installed_only = bool(value)
        self._rebuild()

    def refresh_states(self):
        self._rebuild()

    # -- app_v10 / app_v11 view contract -------------------------------
    def show_loading_skeleton(self, count: int = 12):
        self._skeleton = count
        self._display = []
        self._shimmer.run(True)
        self._relayout()

    def set_items(self, rows):
        self._skeleton = 0
        self._shimmer.run(False)
        self._entries = {}
        self._order = []
        for index, (key, game, channel) in enumerate(rows):
            self._entries[key] = {"game": game, "channel": channel, "row": index}
            self._order.append(key)
        self._rebuild()

    def set_source_rows(self, mapping: dict):
        for key, entry in self._entries.items():
            if key in mapping:
                entry["row"] = int(mapping[key])

    def set_current_row(self, row: int):
        target = self._key_for_row(row)
        self._current_key = target
        self._canvas.update()
        if target is not None:
            self._ensure_key_visible(target)

    def set_tile_progress(self, key: str, percent):
        if percent is None:
            self._progress.pop(key, None)
        else:
            self._progress[key] = int(percent)
        self._canvas.update()

    def set_tile_badge(self, key: str, text: str):
        pass

    def set_tile_cover(self, key: str, pixmap):
        # Icons come from the shared ImageHub by URL; covers pushed by key
        # are meant for the Big Picture wall.
        pass

    def set_tile_installed(self, key: str, installed: bool):
        pass

    def focus_selection(self):
        self._canvas.setFocus(Qt.OtherFocusReason)

    def is_selection_on_last_row(self) -> bool:
        keys = self._visual_keys()
        return bool(keys) and self._current_key == keys[-1]

    def contains_source_row(self, row: int) -> bool:
        return self._key_for_row(row) in set(self._visual_keys())

    def first_source_row(self):
        keys = self._visual_keys()
        return self._entries[keys[0]]["row"] if keys else None

    def activate_current(self) -> bool:
        keys = self._visual_keys()
        if not keys:
            return False
        key = self._current_key if self._current_key in keys else keys[0]
        row = self._entries[key]["row"]
        self._current_key = key
        self.gameActivated.emit(row)
        self.rowClicked.emit(row)
        return True

    def move_direction(self, direction: str) -> bool:
        delta = {"up": -1, "down": 1}.get(direction)
        if delta is None:
            return False
        self._move_by(delta)
        return True

    # -- model ------------------------------------------------------------
    def _state(self, key: str) -> dict:
        try:
            return self._state_provider(key) or {}
        except Exception:
            return {}

    def _visual_keys(self) -> list[str]:
        return [item[1] for item in self._display if item[0] == "row"]

    def _key_for_row(self, row: int):
        for key, entry in self._entries.items():
            if entry["row"] == row:
                return key
        return None

    def _rebuild(self):
        buckets = {gid: [] for gid, _ in GROUPS}
        states = {}
        for key in self._order:
            state = self._state(key)
            states[key] = state
            if self._installed_only and not state.get("installed"):
                continue
            if state.get("favorite"):
                buckets["fav"].append(key)
            elif state.get("installed"):
                buckets["installed"].append(key)
            else:
                buckets["other"].append(key)

        def title_of(key):
            return str(self._entries[key]["game"].get("title") or "").casefold()

        for keys in buckets.values():
            if self._sort_mode == "recent":
                keys.sort(key=lambda k: (-(states[k].get("recent_ts") or 0.0), title_of(k)))
            else:
                keys.sort(key=title_of)

        display = []
        for gid, title in GROUPS:
            keys = buckets[gid]
            if not keys:
                continue
            display.append(("header", gid, title, len(keys)))
            if gid not in self._collapsed:
                display.extend(("row", key) for key in keys)
        self._display = display
        self._states = states
        if not display:
            self._empty_text = "Oynamaya hazır oyun yok" if self._installed_only else "Bu filtrede oyun yok"
        else:
            self._empty_text = ""
        self._relayout()

    def _relayout(self):
        tops = []
        y = 4
        if self._skeleton:
            height = 4 + self._skeleton * self.ROW_H + 8
        else:
            for item in self._display:
                tops.append(y)
                y += self.HEADER_H if item[0] == "header" else self.ROW_H
            height = y + 12
        self._tops = tops
        self._canvas.setMinimumHeight(max(height, 60))
        self._canvas.update()

    def _index_at(self, y: int) -> int:
        for index, top in enumerate(self._tops):
            item = self._display[index]
            h = self.HEADER_H if item[0] == "header" else self.ROW_H
            if top <= y < top + h:
                return index
        return -1

    def _ensure_key_visible(self, key: str):
        for index, item in enumerate(self._display):
            if item[0] == "row" and item[1] == key:
                top = self._tops[index] if index < len(self._tops) else 0
                self.ensureVisible(0, top + self.ROW_H // 2, 0, self.ROW_H * 2)
                return

    def _select_key(self, key: str, activate: bool = False):
        self._current_key = key
        row = self._entries[key]["row"]
        self._ensure_key_visible(key)
        self._canvas.update()
        if activate:
            self.gameActivated.emit(row)
            self.rowClicked.emit(row)
        else:
            self.selectionChanged.emit(row)
            self.rowClicked.emit(row)

    def _move_by(self, delta: int):
        keys = self._visual_keys()
        if not keys:
            return
        index = keys.index(self._current_key) if self._current_key in keys else (-1 if delta > 0 else len(keys))
        index = int(clamp(index + delta, 0, len(keys) - 1))
        self._select_key(keys[index])

    # -- input ---------------------------------------------------------------
    def _hover_at(self, pos):
        index = -1 if pos is None else self._index_at(pos.y())
        if index != self._hover_index:
            self._hover_index = index
            item = self._display[index] if 0 <= index < len(self._display) else None
            self._canvas.setCursor(Qt.PointingHandCursor if item else Qt.ArrowCursor)
            self._canvas.update()

    def _press(self, event):
        self._canvas.setFocus(Qt.MouseFocusReason)
        index = self._index_at(event.position().toPoint().y())
        if index < 0:
            return
        item = self._display[index]
        if item[0] == "header":
            if event.button() == Qt.LeftButton:
                gid = item[1]
                if gid in self._collapsed:
                    self._collapsed.discard(gid)
                else:
                    self._collapsed.add(gid)
                self._rebuild()
            return
        key = item[1]
        row = self._entries[key]["row"]
        if event.button() == Qt.LeftButton:
            self._select_key(key, activate=True)
        elif event.button() == Qt.RightButton:
            self._current_key = key
            self._canvas.update()
            self.gameActivated.emit(row)
            self.rowContextMenu.emit(row, event.globalPosition().toPoint())

    def _double(self, event):
        index = self._index_at(event.position().toPoint().y())
        if index < 0 or event.button() != Qt.LeftButton:
            return
        item = self._display[index]
        if item[0] == "row":
            self.rowDoubleClicked.emit(self._entries[item[1]]["row"])

    def _key(self, event) -> bool:
        key = event.key()
        if key in (Qt.Key_Up, Qt.Key_Down):
            self._move_by(-1 if key == Qt.Key_Up else 1)
            return True
        if key in (Qt.Key_PageUp, Qt.Key_PageDown):
            step = max(1, self.viewport().height() // self.ROW_H - 1)
            self._move_by(-step if key == Qt.Key_PageUp else step)
            return True
        if key in (Qt.Key_Home, Qt.Key_End):
            keys = self._visual_keys()
            if keys:
                self._select_key(keys[0] if key == Qt.Key_Home else keys[-1])
            return True
        if key in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.activate_current()
            return True
        return False

    def _tooltip(self, event):
        index = self._index_at(event.pos().y())
        if 0 <= index < len(self._display) and self._display[index][0] == "row":
            key = self._display[index][1]
            title = str(self._entries[key]["game"].get("title") or "")
            QToolTip.showText(event.globalPos(), title, self._canvas)
        else:
            QToolTip.hideText()

    # -- painting --------------------------------------------------------
    def _icon(self, key: str, game: dict, size: int, ratio: float) -> QPixmap | None:
        cache_key = f"{key}@{size}@{ratio}"
        cached = self._icons.get(cache_key)
        if cached is not None:
            return cached
        artwork = game.get("artwork") or {}
        url = str(artwork.get("cover") or "")
        if not url:
            return None
        source = self._images.request("cover", url, lambda _url, _pm: self._canvas.update())
        if source is None:
            return None
        icon = cover_crop(source, size, size, 0.5, 0.3, ratio)
        self._icons[cache_key] = icon
        return icon

    def _paint(self, canvas: QWidget, clip):
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        width = canvas.width()
        if self._skeleton:
            for i in range(self._skeleton):
                y = 4 + i * self.ROW_H
                paint_shimmer(painter, QRectF(22, y + 5, 18, 18), self._shimmer.phase, 2)
                paint_shimmer(painter, QRectF(50, y + 9, (width - 90) * (0.45 + 0.4 * ((i * 37) % 10) / 10), 10),
                              self._shimmer.phase, 3)
            painter.end()
            return
        if not self._display:
            painter.setPen(QColor(T.TEXT_MUTED))
            painter.setFont(T.ui_font(12))
            painter.drawText(QRectF(16, 16, width - 32, 40), Qt.AlignLeft | Qt.TextWordWrap, self._empty_text)
            painter.end()
            return

        ratio = device_ratio(canvas)
        states = getattr(self, "_states", {})
        for index, item in enumerate(self._display):
            top = self._tops[index]
            h = self.HEADER_H if item[0] == "header" else self.ROW_H
            if top + h < clip.top() or top > clip.bottom():
                continue
            if item[0] == "header":
                self._paint_header(painter, QRectF(0, top, width, h), item, index == self._hover_index)
                continue
            key = item[1]
            entry = self._entries[key]
            state = states.get(key, {})
            rect = QRectF(0, top, width, h)
            selected = key == self._current_key
            if selected:
                painter.fillRect(rect, QColor(T.ROW_SELECTED))
            elif index == self._hover_index:
                painter.fillRect(rect, QColor(T.ROW_HOVER))
            icon_rect = QRectF(22, top + (h - 18) / 2, 18, 18)
            icon = self._icon(key, entry["game"], 18, ratio)
            if icon is not None:
                painter.save()
                painter.setClipPath(rounded_path(icon_rect, 2))
                painter.drawPixmap(icon_rect, icon, QRectF(icon.rect()))
                painter.restore()
            else:
                painter.fillRect(icon_rect, QColor("#1b1d22"))
                painter.setPen(QColor(T.TEXT_FAINT))
                painter.setFont(T.ui_font(10, 700))
                painter.drawText(icon_rect, Qt.AlignCenter, str(entry["game"].get("title") or "?")[:1].upper())

            title = str(entry["game"].get("title") or "")
            suffix = ""
            progress = self._progress.get(key)
            installed = bool(state.get("installed"))
            blue = False
            if progress is not None or state.get("downloading"):
                blue = True
                suffix = "Duraklatıldı" if state.get("paused") else f"%{progress if progress is not None else 0}"
            elif state.get("update"):
                blue = True
                suffix = "Güncelleme gerekli"
            elif state.get("partial"):
                blue = True
                suffix = "Devam ettirilebilir"
            if selected:
                title_color = QColor("#ffffff")
            elif blue:
                title_color = QColor(T.STATUS_BLUE)
            elif installed:
                title_color = QColor(T.ROW_TEXT)
            else:
                title_color = QColor(T.ROW_TEXT_DIM)
            text_x = 50.0
            available = width - text_x - 10
            painter.setFont(self._title_font)
            metrics = QFontMetrics(self._title_font)
            suffix_text = f"  -  {suffix}" if suffix else ""
            suffix_w = metrics.horizontalAdvance(suffix_text)
            title_room = max(40.0, available - suffix_w)
            shown = metrics.elidedText(title, Qt.ElideRight, int(title_room))
            painter.setPen(title_color)
            painter.drawText(QRectF(text_x, top, title_room, h), Qt.AlignVCenter | Qt.AlignLeft, shown)
            if suffix_text:
                x = text_x + metrics.horizontalAdvance(shown)
                painter.setPen(QColor("#ffffff") if selected else QColor(T.STATUS_BLUE_LIGHT))
                painter.drawText(QRectF(x, top, width - x - 8, h), Qt.AlignVCenter | Qt.AlignLeft, suffix_text)
            if selected and self._canvas.hasFocus():
                painter.fillRect(QRectF(0, top, 2, h), QColor(T.NAV_ACTIVE))
        painter.end()

    def _paint_header(self, painter: QPainter, rect: QRectF, item, hovered: bool):
        _kind, gid, title, count = item
        painter.fillRect(rect, QColor(T.GROUP_HEADER) if not hovered else QColor("#313643"))
        collapsed = gid in self._collapsed
        painter.setPen(QPen(QColor("#8d95a7"), 1.6))
        cy = rect.center().y()
        painter.drawLine(QPointF(9, cy), QPointF(16, cy))
        if collapsed:
            painter.drawLine(QPointF(12.5, cy - 3.5), QPointF(12.5, cy + 3.5))
        painter.setFont(self._header_font)
        metrics = QFontMetrics(self._header_font)
        painter.setPen(QColor("#e0e7f3"))
        painter.drawText(QRectF(24, rect.y(), rect.width(), rect.height()), Qt.AlignVCenter | Qt.AlignLeft, title)
        x = 24 + metrics.horizontalAdvance(title) + 6
        painter.setPen(QColor(T.TEXT_FAINT))
        painter.drawText(QRectF(x, rect.y(), rect.width() - x, rect.height()), Qt.AlignVCenter | Qt.AlignLeft,
                         f"({count})")


class DropdownButton(QPushButton):
    """Sidebar "GAMES v" dropdown: label on the left, chevron on the right."""

    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setObjectName("sidebarDropdown")
        self.setCursor(Qt.PointingHandCursor)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.TextAntialiasing)
        painter.setPen(QColor(T.TEXT_MUTED))
        painter.setFont(T.icon_font(9))
        painter.drawText(QRectF(self.width() - 26, 0, 20, self.height()), Qt.AlignCenter, G.CHEVRON_DOWN)
        painter.end()


class SidebarPanel(QFrame):
    """Top of the Steam library sidebar (HOME, type dropdown, recent and
    ready-to-play toggles, search) plus the game list."""

    homeRequested = Signal()
    collectionRequested = Signal()
    sortModeChanged = Signal(str)
    installedOnlyChanged = Signal(bool)

    def __init__(self, images: ImageHub, parent=None):
        super().__init__(parent)
        self.setObjectName("steamSidebar")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        top = QFrame()
        top.setObjectName("sidebarTop")
        top_layout = QVBoxLayout(top)
        top_layout.setContentsMargins(8, 8, 8, 8)
        top_layout.setSpacing(6)

        home_row = QHBoxLayout()
        home_row.setSpacing(4)
        self.home_button = QPushButton("ANA SAYFA")
        self.home_button.setObjectName("sidebarHome")
        self.home_button.setCursor(Qt.PointingHandCursor)
        self.home_button.setFont(T.ui_font(12, 700, spacing=0.8))
        self.home_button.clicked.connect(self.homeRequested)
        self.grid_button = icon_button(G.GRID, "sidebarIcon", "Koleksiyon görünümü", 13)
        self.grid_button.clicked.connect(self.collectionRequested)
        home_row.addWidget(self.home_button, 1)
        home_row.addWidget(self.grid_button)
        top_layout.addLayout(home_row)

        filter_row = QHBoxLayout()
        filter_row.setSpacing(2)
        self.filter_button = DropdownButton("OYUNLAR")
        self.filter_button.setFont(T.ui_font(12, 700, spacing=0.8))
        self.filter_menu = QMenu(self.filter_button)
        self.filter_button.setMenu(self.filter_menu)
        filter_row.addWidget(self.filter_button, 1)
        filter_row.addSpacing(4)
        self.recent_toggle = icon_button(G.CLOCK, "sidebarToggle", "Son eklenenlere göre sırala", 14,
                                         color=T.TEXT_MUTED, hover=T.NAV_ACTIVE)
        self.recent_toggle.setCheckable(True)
        self.ready_toggle = icon_button(G.PLAY, "sidebarToggle", "Yalnızca oynamaya hazır olanlar", 13,
                                        color=T.TEXT_MUTED, hover=T.NAV_ACTIVE)
        self.ready_toggle.setCheckable(True)
        self.recent_toggle.toggled.connect(lambda on: self.sortModeChanged.emit("recent" if on else "alpha"))
        self.ready_toggle.toggled.connect(self.installedOnlyChanged)
        filter_row.addWidget(self.recent_toggle)
        filter_row.addWidget(self.ready_toggle)
        top_layout.addLayout(filter_row)

        self.search = QLineEdit()
        self.search.setObjectName("sidebarSearch")
        self.search.setPlaceholderText("Ara")
        self.search.setClearButtonEnabled(True)
        self.search.addAction(QAction(T.glyph_icon(G.SEARCH, 12, T.TEXT_MUTED), "", self.search),
                              QLineEdit.LeadingPosition)
        top_layout.addWidget(self.search)
        outer.addWidget(top)

        self.list = SteamLibraryList(images)
        outer.addWidget(self.list, 1)

    def set_home_active(self, active: bool):
        self.home_button.setProperty("active", "true" if active else "false")
        self.home_button.style().unpolish(self.home_button)
        self.home_button.style().polish(self.home_button)

    def set_filter_label(self, text: str):
        self.filter_button.setText(text)


# ---------------------------------------------------------------------------
# library home: shelf + collection wall
# ---------------------------------------------------------------------------


class CapsuleGrid(QWidget):
    """The library's "ALL GAMES" wall, painted in one widget: hover lift with
    a light glare, a round PLAY/INSTALL button, a download bar and skeleton
    capsules while the catalog is still loading."""

    openRequested = Signal(str)
    actionRequested = Signal(str)
    contextRequested = Signal(str, QPoint)

    GAP = 18
    PAD = 10

    def __init__(self, images: ImageHub, parent=None):
        super().__init__(parent)
        self._images = images
        self._items: list[dict] = []
        self._rects: list[QRectF] = []
        self._capsule_w = 170
        self._art: dict[str, QPixmap] = {}
        self._hover_key: str | None = None
        self._mouse = QPointF()
        self._loading = 0
        self._shimmer = _Shimmer(self)
        self._hover = _HoverTracker(self, self._repaint_key)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WA_Hover, True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_capsule_width(self, width: int):
        width = int(clamp(width, 120, 240))
        if width != self._capsule_w:
            self._capsule_w = width
            self._art.clear()
            self._relayout()

    def capsule_width(self) -> int:
        return self._capsule_w

    def set_loading(self, count: int):
        self._loading = count
        self._items = []
        self._shimmer.run(count > 0)
        self._relayout()

    def set_items(self, items: list[dict]):
        """items: key, title, cover_url, badge, progress, action ("play"/"install")."""
        self._loading = 0
        self._shimmer.run(False)
        self._items = items
        self._relayout()

    def update_item(self, key: str, **changes):
        for index, item in enumerate(self._items):
            if item["key"] == key:
                item.update(changes)
                if index < len(self._rects):
                    self.update(self._rects[index].adjusted(-16, -16, 16, 22).toAlignedRect())
                return

    def _size(self) -> tuple[int, int]:
        return self._capsule_w, int(round(self._capsule_w * 1.5))

    def _relayout(self):
        width = max(1, self.width() - self.PAD * 2)
        cw, ch = self._size()
        cols = max(1, (width + self.GAP) // (cw + self.GAP))
        count = self._loading or len(self._items)
        rects = []
        for index in range(count):
            row, col = divmod(index, cols)
            rects.append(QRectF(self.PAD + col * (cw + self.GAP), self.PAD + row * (ch + self.GAP), cw, ch))
        rows = -(-count // cols) if count else 0
        self._rects = rects
        height = self.PAD * 2 + rows * ch + max(0, rows - 1) * self.GAP
        self.setFixedHeight(max(height, 40))
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if event.oldSize().width() != event.size().width():
            self._relayout()

    def _repaint_key(self, key: str):
        for index, item in enumerate(self._items):
            if item["key"] == key and index < len(self._rects):
                self.update(self._rects[index].adjusted(-16, -16, 16, 22).toAlignedRect())
                return

    def _art_for(self, item: dict) -> QPixmap | None:
        cw, ch = self._size()
        cached = self._art.get(item["key"])
        if cached is not None:
            return cached
        url = item.get("cover_url") or ""
        if not url:
            return None
        source = self._images.request("cover", url, lambda _u, _p, k=item["key"]: self._repaint_key(k))
        if source is None:
            return None
        art = cover_crop(source, cw, ch, 0.5, 0.5, device_ratio(self))
        self._art[item["key"]] = art
        return art

    def _index_at(self, pos: QPointF) -> int:
        for index, rect in enumerate(self._rects):
            if rect.contains(pos):
                return index
        return -1

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        clip = QRectF(event.rect()).adjusted(-20, -20, 20, 20)
        if self._loading:
            for rect in self._rects:
                if rect.intersects(clip):
                    paint_shimmer(painter, rect, self._shimmer.phase, 3)
            painter.end()
            return
        hovered_index = -1
        for index, item in enumerate(self._items):
            if index >= len(self._rects):
                break
            if item["key"] == self._hover_key:
                hovered_index = index
                continue
            self._paint_item(painter, index, item, clip)
        if hovered_index >= 0:  # draw last so its lift overlaps neighbours
            self._paint_item(painter, hovered_index, self._items[hovered_index], clip)
        painter.end()

    def _paint_item(self, painter: QPainter, index: int, item: dict, clip: QRectF):
        base = self._rects[index]
        if not base.intersects(clip):
            return
        amount = self._hover.amount(item["key"])
        scale = 1.0 + 0.035 * amount
        rect = QRectF(0, 0, base.width() * scale, base.height() * scale)
        rect.moveCenter(base.center() - QPointF(0, 3 * amount))
        paint_capsule_shadow(painter, rect, amount)
        glare = 0.5
        if item["key"] == self._hover_key and base.width() > 0:
            glare = clamp((self._mouse.x() - base.x()) / base.width(), 0.0, 1.0)
        paint_capsule(
            painter,
            rect,
            self._art_for(item),
            title=item.get("title", ""),
            seed=item["key"],
            hover=amount,
            glare_x=glare,
            badge=item.get("badge", ""),
            progress=item.get("progress"),
            action=item.get("action"),
        )

    def event(self, event):
        if event.type() == QEvent.ToolTip:
            index = self._index_at(QPointF(event.pos()))
            if 0 <= index < len(self._items):
                QToolTip.showText(event.globalPos(), self._items[index].get("title", ""), self)
            else:
                QToolTip.hideText()
            return True
        if event.type() == QEvent.HoverLeave:
            self._set_hover(None)
        return super().event(event)

    def _set_hover(self, key: str | None):
        if key != self._hover_key:
            previous = self._hover_key
            self._hover_key = key
            self._hover.set_hover(key)
            if previous:
                self._repaint_key(previous)
            self.setCursor(Qt.PointingHandCursor if key else Qt.ArrowCursor)

    def mouseMoveEvent(self, event):
        self._mouse = event.position()
        index = self._index_at(self._mouse)
        key = self._items[index]["key"] if 0 <= index < len(self._items) else None
        self._set_hover(key)
        if key:
            self._repaint_key(key)

    def mousePressEvent(self, event):
        index = self._index_at(event.position())
        if index < 0 or index >= len(self._items):
            return
        item = self._items[index]
        if event.button() == Qt.RightButton:
            self.contextRequested.emit(item["key"], event.globalPosition().toPoint())
            return
        if event.button() != Qt.LeftButton:
            return
        rect = self._rects[index]
        if item.get("action") and action_rect(rect).adjusted(-4, -4, 4, 4).contains(event.position()):
            self.actionRequested.emit(item["key"])
        else:
            self.openRequested.emit(item["key"])


class _ShelfStrip(QWidget):
    """Horizontal run of capsules with Steam's time captions above groups.
    The first item is a wide capsule (hero + logo), the rest are portrait."""

    openRequested = Signal(str)
    actionRequested = Signal(str)
    contextRequested = Signal(str, QPoint)

    CAPTION_H = 24
    GAP = 14
    PAD = 10

    def __init__(self, images: ImageHub, parent=None):
        super().__init__(parent)
        self._images = images
        self._items: list[dict] = []
        self._rects: list[QRectF] = []
        self._captions: list[tuple[float, str]] = []
        self._art: dict[str, QPixmap] = {}
        self._hover_key = None
        self._mouse = QPointF()
        self._hover = _HoverTracker(self, lambda _k: self.update())
        self._capsule_w = 150
        self.setMouseTracking(True)
        self.setAttribute(Qt.WA_Hover, True)

    def capsule_height(self) -> int:
        return int(self._capsule_w * 1.5)

    def set_items(self, items: list[dict]):
        self._items = items
        self._art.clear()
        self._relayout()

    def _relayout(self):
        cw = self._capsule_w
        ch = self.capsule_height()
        x = float(self.PAD)
        rects, captions = [], []
        last_caption = None
        for index, item in enumerate(self._items):
            caption = item.get("caption") or ""
            if caption != last_caption:
                if index:
                    x += 10
                captions.append((x, caption))
                last_caption = caption
            width = cw * 2 + self.GAP if item.get("wide") else cw
            rects.append(QRectF(x, self.PAD + self.CAPTION_H, width, ch))
            x += width + self.GAP
        self._rects = rects
        self._captions = captions
        self.setFixedSize(int(x + self.PAD), self.PAD * 2 + self.CAPTION_H + ch + 4)
        self.update()

    def _art_for(self, index: int, item: dict):
        rect = self._rects[index]
        key = item["key"]
        cached = self._art.get(key)
        if cached is not None:
            return cached
        kind = "hero" if item.get("wide") else "cover"
        url = item.get("hero_url" if item.get("wide") else "cover_url") or ""
        if not url:
            return None
        source = self._images.request(kind, url, lambda _u, _p: self.update())
        if source is None:
            return None
        art = cover_crop(source, int(rect.width()), int(rect.height()), 0.5, 0.35, device_ratio(self))
        self._art[key] = art
        return art

    def _logo_for(self, item: dict):
        url = item.get("logo_url") or ""
        if not item.get("wide") or not url:
            return None
        return self._images.request("logo", url, lambda _u, _p: self.update())

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.setFont(T.ui_font(12, 600))
        painter.setPen(QColor(T.TEXT_MUTED))
        for x, caption in self._captions:
            painter.drawText(QRectF(x, self.PAD, 300, self.CAPTION_H - 6), Qt.AlignLeft | Qt.AlignVCenter, caption)
        order = [i for i, it in enumerate(self._items) if it["key"] != self._hover_key]
        order += [i for i, it in enumerate(self._items) if it["key"] == self._hover_key]
        for index in order:
            item = self._items[index]
            base = self._rects[index]
            amount = self._hover.amount(item["key"])
            scale = 1.0 + 0.03 * amount
            rect = QRectF(0, 0, base.width() * scale, base.height() * scale)
            rect.moveCenter(base.center() - QPointF(0, 3 * amount))
            paint_capsule_shadow(painter, rect, amount)
            glare = clamp((self._mouse.x() - base.x()) / max(1.0, base.width()), 0, 1) \
                if item["key"] == self._hover_key else 0.5
            paint_capsule(
                painter, rect, self._art_for(index, item), title=item.get("title", ""), seed=item["key"],
                hover=amount, glare_x=glare, progress=item.get("progress"), action=item.get("action"),
                logo=self._logo_for(item),
            )
        painter.end()

    def _index_at(self, pos: QPointF) -> int:
        for index, rect in enumerate(self._rects):
            if rect.contains(pos):
                return index
        return -1

    def event(self, event):
        if event.type() == QEvent.ToolTip:
            index = self._index_at(QPointF(event.pos()))
            if index >= 0:
                QToolTip.showText(event.globalPos(), self._items[index].get("title", ""), self)
            else:
                QToolTip.hideText()
            return True
        if event.type() == QEvent.HoverLeave:
            self._hover_key = None
            self._hover.set_hover(None)
            self.setCursor(Qt.ArrowCursor)
        return super().event(event)

    def mouseMoveEvent(self, event):
        self._mouse = event.position()
        index = self._index_at(self._mouse)
        key = self._items[index]["key"] if index >= 0 else None
        if key != self._hover_key:
            self._hover_key = key
            self._hover.set_hover(key)
            self.setCursor(Qt.PointingHandCursor if key else Qt.ArrowCursor)
        self.update()

    def mousePressEvent(self, event):
        index = self._index_at(event.position())
        if index < 0:
            return
        item = self._items[index]
        if event.button() == Qt.RightButton:
            self.contextRequested.emit(item["key"], event.globalPosition().toPoint())
        elif event.button() == Qt.LeftButton:
            if item.get("action") and action_rect(self._rects[index]).adjusted(-4, -4, 4, 4).contains(event.position()):
                self.actionRequested.emit(item["key"])
            else:
                self.openRequested.emit(item["key"])


class _HorizontalScroller(QScrollArea):
    def wheelEvent(self, event):
        # Vertical wheel scrolls the page, not the shelf (Steam behaviour).
        if abs(event.angleDelta().y()) > abs(event.angleDelta().x()):
            event.ignore()
            return
        super().wheelEvent(event)


class CapsuleShelf(QWidget):
    openRequested = Signal(str)
    actionRequested = Signal(str)
    contextRequested = Signal(str, QPoint)

    def __init__(self, images: ImageHub, title: str, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.header = SectionHeader(title)
        self.prev_button = icon_button(G.CHEVRON_LEFT, "chromeFlat", "Geri kaydır", 12)
        self.next_button = icon_button(G.CHEVRON_RIGHT, "chromeFlat", "İleri kaydır", 12)
        self.header.add_right(self.prev_button)
        self.header.add_right(self.next_button)
        layout.addWidget(self.header)
        self.scroller = _HorizontalScroller()
        self.scroller.setFrameShape(QFrame.NoFrame)
        self.scroller.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroller.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroller.setWidgetResizable(False)
        self.strip = _ShelfStrip(images)
        self.scroller.setWidget(self.strip)
        layout.addWidget(self.scroller)
        self.strip.openRequested.connect(self.openRequested)
        self.strip.actionRequested.connect(self.actionRequested)
        self.strip.contextRequested.connect(self.contextRequested)
        self.prev_button.clicked.connect(lambda: self._scroll(-1))
        self.next_button.clicked.connect(lambda: self._scroll(1))
        self.scroller.horizontalScrollBar().rangeChanged.connect(lambda *_: self._sync_arrows())
        self.scroller.horizontalScrollBar().valueChanged.connect(lambda *_: self._sync_arrows())
        self._anim = QPropertyAnimation(self.scroller.horizontalScrollBar(), b"value", self)
        self._anim.setDuration(420)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

    def set_items(self, title: str, items: list[dict]):
        self.header.set_title(title)
        self.header.set_count(len(items) if items else None)
        self.strip.set_items(items)
        self.scroller.setFixedHeight(self.strip.height())
        self._sync_arrows()

    def _scroll(self, direction: int):
        bar = self.scroller.horizontalScrollBar()
        target = int(clamp(bar.value() + direction * self.scroller.viewport().width() * 0.75, 0, bar.maximum()))
        if T.animations_enabled():
            self._anim.stop()
            self._anim.setStartValue(bar.value())
            self._anim.setEndValue(target)
            self._anim.start()
        else:
            bar.setValue(target)

    def _sync_arrows(self):
        bar = self.scroller.horizontalScrollBar()
        self.prev_button.setEnabled(bar.value() > 0)
        self.next_button.setEnabled(bar.value() < bar.maximum())
        visible = bar.maximum() > 0
        self.prev_button.setVisible(visible)
        self.next_button.setVisible(visible)


class HomeNotice(QFrame):
    """Empty and error states for the library home."""

    actionClicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("steamPanel")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(16)
        self.glyph = QLabel()
        self.glyph.setFixedSize(34, 34)
        layout.addWidget(self.glyph, 0, Qt.AlignTop)
        column = QVBoxLayout()
        column.setSpacing(4)
        self.title = make_label("", T.TEXT, 15, 700)
        self.text = make_label("", T.TEXT_MUTED, 13)
        self.text.setWordWrap(True)
        column.addWidget(self.title)
        column.addWidget(self.text)
        layout.addLayout(column, 1)
        self.button = QPushButton()
        self.button.setCursor(Qt.PointingHandCursor)
        self.button.clicked.connect(self.actionClicked)
        layout.addWidget(self.button, 0, Qt.AlignVCenter)

    def show_notice(self, glyph: str, title: str, text: str, button: str = ""):
        self.glyph.setPixmap(T.glyph_pixmap(glyph, 22, T.TEXT_MUTED, 34))
        self.title.setText(title)
        self.text.setText(text)
        self.button.setText(button)
        self.button.setVisible(bool(button))
        self.show()


class _GradientCanvas(QWidget):
    def __init__(self, top: str = T.PAGE_TOP, bottom: str = T.PAGE_BOTTOM, parent=None):
        super().__init__(parent)
        self._top, self._bottom = QColor(top), QColor(bottom)

    def paintEvent(self, event):
        painter = QPainter(self)
        gradient = QLinearGradient(0, 0, 0, max(1, min(self.height(), 900)))
        gradient.setColorAt(0.0, self._top)
        gradient.setColorAt(1.0, self._bottom)
        painter.fillRect(self.rect(), self._bottom)
        painter.fillRect(QRectF(0, 0, self.width(), min(self.height(), 900)), gradient)
        painter.end()


class LibraryHome(QScrollArea):
    """Library home: one shelf (recent installs, or newest releases when
    nothing is installed yet) and the ALL GAMES wall with sort and size."""

    openRequested = Signal(str)
    actionRequested = Signal(str)
    contextRequested = Signal(str, QPoint)
    sortChanged = Signal(str)
    retryRequested = Signal()
    clearFiltersRequested = Signal()

    SORTS = (("alpha", "Alfabetik"), ("published", "Yayın tarihi"), ("size", "Boyut"))

    def __init__(self, images: ImageHub, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        canvas = _GradientCanvas()
        self.setWidget(canvas)
        layout = QVBoxLayout(canvas)
        layout.setContentsMargins(26, 22, 26, 40)
        layout.setSpacing(24)

        self.notice = HomeNotice()
        self.notice.hide()
        self.notice.actionClicked.connect(self._notice_action)
        self._notice_kind = ""
        layout.addWidget(self.notice)

        self.shelf = CapsuleShelf(images, "SON YÜKLENENLER")
        layout.addWidget(self.shelf)

        grid_block = QVBoxLayout()
        grid_block.setSpacing(6)
        self.grid_header = SectionHeader("TÜM OYUNLAR")
        sort_caption = make_label("SIRALA", T.TEXT_MUTED, 11, 700, spacing=0.8)
        self.sort_combo = QComboBox()
        self.sort_combo.setCursor(Qt.PointingHandCursor)
        for value, label in self.SORTS:
            self.sort_combo.addItem(label, value)
        self.sort_combo.currentIndexChanged.connect(lambda _i: self.sortChanged.emit(self.sort_value()))
        self.size_slider = QSlider(Qt.Horizontal)
        self.size_slider.setRange(120, 230)
        self.size_slider.setValue(170)
        self.size_slider.setFixedWidth(110)
        self.size_slider.setToolTip("Kapak boyutu")
        self.size_slider.setCursor(Qt.PointingHandCursor)
        self.size_slider.setStyleSheet(
            "QSlider::groove:horizontal { height: 4px; background: #3d4450; border-radius: 2px; }"
            "QSlider::sub-page:horizontal { background: #64a6fc; border-radius: 2px; }"
            "QSlider::handle:horizontal { width: 12px; margin: -5px 0; border-radius: 6px; background: #dcdedf; }"
        )
        self.grid_header.add_right(sort_caption)
        self.grid_header.add_right(self.sort_combo)
        self.grid_header.add_right(self.size_slider)
        grid_block.addWidget(self.grid_header)
        self.grid = CapsuleGrid(images)
        grid_block.addWidget(self.grid)
        layout.addLayout(grid_block)
        layout.addStretch(1)

        self.size_slider.valueChanged.connect(self.grid.set_capsule_width)
        for source in (self.shelf, self.grid):
            source.openRequested.connect(self.openRequested)
            source.actionRequested.connect(self.actionRequested)
            source.contextRequested.connect(self.contextRequested)

    def sort_value(self) -> str:
        return str(self.sort_combo.currentData() or "alpha")

    def set_sort_value(self, value: str):
        index = self.sort_combo.findData(value)
        if index >= 0:
            self.sort_combo.setCurrentIndex(index)

    def set_loading(self):
        self.notice.hide()
        self.shelf.hide()
        self.grid_header.set_count(None)
        self.grid.set_loading(12)

    def set_content(self, shelf_title: str, shelf_items: list[dict], grid_items: list[dict]):
        self.notice.hide()
        self._notice_kind = ""
        self.shelf.setVisible(bool(shelf_items))
        if shelf_items:
            self.shelf.set_items(shelf_title, shelf_items)
        self.grid_header.set_count(len(grid_items))
        self.grid.set_items(grid_items)

    def show_error(self, title: str, text: str):
        self._notice_kind = "retry"
        self.notice.show_notice(G.WARNING, title, text, "Tekrar dene")
        self.shelf.hide()
        self.grid.set_items([])
        self.grid_header.set_count(0)

    def show_filtered_empty(self):
        self._notice_kind = "clear"
        self.notice.show_notice(G.SEARCH, "Bu filtrede oyun yok",
                                "Arama, kanal ya da hazır olma filtresini değiştir.", "Filtreleri temizle")
        self.shelf.hide()
        self.grid.set_items([])
        self.grid_header.set_count(0)

    def _notice_action(self):
        if self._notice_kind == "retry":
            self.retryRequested.emit()
        elif self._notice_kind == "clear":
            self.clearFiltersRequested.emit()

    def scroll_to_grid(self):
        self.ensureWidgetVisible(self.grid_header, 0, 20)
