"""Steam-accurate library widgets: desktop list rail + Big Picture cover grid.

Real Steam has two distinct library presentations, and this module provides
both so the launcher can mirror them:

* `GameListView`  - the desktop client's left rail: a compact vertical list,
  small square icon plus one line of title, solid highlight on the selected
  row, thin progress line across the row while it downloads.
* `GameGridView`  - Big Picture's full-screen wall of portrait capsules:
  large cover art, no client-drawn title (the capsule art carries it), a
  bright selection ring, an optional corner badge, and a progress bar
  pinned to the bottom of a downloading capsule.

Both classes expose the same API surface, so the owner can drive them from
one data source without branching. Pure UI: no networking, no dependency on
drowned_shared. The owner listens to `coverRequested` / `thumbRequested` and
pushes pixmaps back in.
"""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPoint, QRect, QSize, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


def _paint_shimmer(painter: QPainter, rect: QRect, phase: float) -> None:
    """Skeleton placeholder: a soft highlight band sweeping across a dark
    plate. Used everywhere artwork is still in flight."""
    painter.fillRect(rect, QColor("#0d1319"))
    band_w = max(rect.width() * 0.55, 1)
    x = rect.x() - band_w + (rect.width() + band_w * 2) * phase
    gradient = QLinearGradient(x, rect.y(), x + band_w, rect.y() + rect.height())
    gradient.setColorAt(0.0, QColor(255, 255, 255, 0))
    gradient.setColorAt(0.5, QColor(255, 255, 255, 18))
    gradient.setColorAt(1.0, QColor(255, 255, 255, 0))
    painter.fillRect(rect, gradient)


def _draw_cover(painter: QPainter, rect: QRect, cover: QPixmap, opacity: float) -> None:
    scaled = cover.scaled(rect.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    sx = max((scaled.width() - rect.width()) // 2, 0)
    sy = max((scaled.height() - rect.height()) // 2, 0)
    source = QRect(sx, sy, min(rect.width(), scaled.width()), min(rect.height(), scaled.height()))
    painter.setOpacity(opacity)
    painter.drawPixmap(rect, scaled, source)
    painter.setOpacity(1.0)


class _ArtworkWidget(QFrame):
    """Shared behaviour for anything that shows remote cover art: shimmer
    while loading, fade-in reveal on arrival, hover easing, focus/selection
    state, and an optional download percentage."""

    activated = Signal()
    focused = Signal()

    def __init__(self, game: dict, channel: str, row: int, key: str, scale: float = 1.0, parent=None):
        super().__init__(parent)
        self.row = row
        self.key = key
        self.cover_requested = False
        self._game = game
        self._channel = channel
        self._cover = QPixmap()
        self._loading = True
        self._selected = False
        self._progress: int | None = None
        self._badge = ""
        self._scale = scale
        self._reveal = 0.0
        self._hover = 0.0
        self._shimmer_phase = 0.0

        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)

        self._shimmer_anim = QVariantAnimation(self)
        self._shimmer_anim.setStartValue(0.0)
        self._shimmer_anim.setEndValue(1.0)
        self._shimmer_anim.setDuration(1150)
        self._shimmer_anim.setLoopCount(-1)
        self._shimmer_anim.valueChanged.connect(self._on_shimmer)
        self._shimmer_anim.start()

        self._reveal_anim = QVariantAnimation(self)
        self._reveal_anim.setDuration(220)
        self._reveal_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._reveal_anim.valueChanged.connect(self._on_reveal)

        self._hover_anim = QVariantAnimation(self)
        self._hover_anim.setDuration(110)
        self._hover_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._hover_anim.valueChanged.connect(self._on_hover)

    # -- data ------------------------------------------------------------

    def set_game(self, game: dict, channel: str) -> None:
        self._game = game
        self._channel = channel
        self.update()

    def set_cover(self, pixmap: QPixmap | None) -> None:
        self._loading = pixmap is None
        self._cover = pixmap if pixmap is not None else QPixmap()
        if pixmap is not None:
            self._shimmer_anim.stop()
            self._reveal = 0.0
            self._reveal_anim.stop()
            self._reveal_anim.setStartValue(0.0)
            self._reveal_anim.setEndValue(1.0)
            self._reveal_anim.start()
        self.update()

    def set_selected(self, selected: bool) -> None:
        if self._selected == selected:
            return
        self._selected = selected
        self.update()

    def set_progress(self, percent: int | None) -> None:
        self._progress = percent
        self.update()

    def set_badge(self, text: str) -> None:
        if self._badge == text:
            return
        self._badge = text
        self.update()

    def set_installed(self, installed: bool) -> None:
        # Steam communicates installed state through the PLAY/INSTALL button
        # on the game page, not through a badge in the library rail. Kept as
        # a no-op so callers do not need a special case.
        pass

    def set_scale(self, factor: float) -> None:
        self._scale = factor
        self._apply_scale()
        self.update()

    def _apply_scale(self) -> None:
        raise NotImplementedError

    @property
    def cover_url(self) -> str:
        return str((self._game.get("artwork") or {}).get("cover") or "")

    # -- animation callbacks --------------------------------------------

    def _on_shimmer(self, value):
        self._shimmer_phase = float(value)
        if self._loading:
            self.update()

    def _on_reveal(self, value):
        self._reveal = float(value)
        self.update()

    def _on_hover(self, value):
        self._hover = float(value)
        self.update()

    # -- input -----------------------------------------------------------

    def enterEvent(self, event):
        self._hover_anim.stop()
        self._hover_anim.setStartValue(self._hover)
        self._hover_anim.setEndValue(1.0)
        self._hover_anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover_anim.stop()
        self._hover_anim.setStartValue(self._hover)
        self._hover_anim.setEndValue(0.0)
        self._hover_anim.start()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.setFocus(Qt.MouseFocusReason)
            self.focused.emit()
            self.activated.emit()
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.activated.emit()
            return
        super().keyPressEvent(event)

    def focusInEvent(self, event):
        self.focused.emit()
        super().focusInEvent(event)


class GameListRow(_ArtworkWidget):
    """One row of the desktop library rail."""

    BASE_H = 34

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setObjectName("gameRow")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._apply_scale()

    def _apply_scale(self):
        self.setFixedHeight(int(self.BASE_H * self._scale))

    def paintEvent(self, event):
        painter = QPainter(self)
        rect = self.rect()

        if self._selected:
            painter.fillRect(rect, QColor("#3d6c93"))
        elif self._hover > 0.0:
            painter.fillRect(rect, QColor(255, 255, 255, int(14 * self._hover)))

        icon = max(18, int(24 * self._scale))
        icon_rect = QRect(8, (rect.height() - icon) // 2, icon, icon)
        painter.fillRect(icon_rect, QColor("#0d1319"))
        if self._loading or self._cover.isNull():
            _paint_shimmer(painter, icon_rect, self._shimmer_phase)
        else:
            _draw_cover(painter, icon_rect, self._cover, self._reveal)

        text_x = icon_rect.right() + 9
        text_rect = QRect(text_x, 0, max(0, rect.width() - text_x - 10), rect.height())
        painter.setPen(QColor("#ffffff") if self._selected else QColor("#c7d5e0"))
        font = painter.font()
        font.setPointSize(max(8, int(9 * self._scale)))
        painter.setFont(font)
        metrics = painter.fontMetrics()
        title = metrics.elidedText(str(self._game.get("title") or ""), Qt.ElideRight, max(0, text_rect.width()))
        painter.drawText(text_rect, int(Qt.AlignVCenter | Qt.AlignLeft), title)

        if self._progress is not None:
            bar_h = 2
            bar = QRect(0, rect.height() - bar_h, rect.width(), bar_h)
            painter.fillRect(bar, QColor(0, 0, 0, 120))
            fill = int(bar.width() * max(0, min(100, self._progress)) / 100.0)
            painter.fillRect(QRect(bar.x(), bar.y(), fill, bar_h), QColor("#66c0f4"))

        if self.hasFocus() and not self._selected:
            painter.setPen(QPen(QColor("#66c0f4"), 1, Qt.DashLine))
            painter.drawRect(rect.adjusted(0, 0, -1, -1))
        painter.end()


class GameCapsule(_ArtworkWidget):
    """One portrait capsule on the Big Picture wall."""

    BASE_W = 200
    BASE_H = 300

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setObjectName("gameCapsule")
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self._apply_scale()

    def _apply_scale(self):
        self.setFixedSize(int(self.BASE_W * self._scale), int(self.BASE_H * self._scale))

    def sizeHint(self):
        return QSize(int(self.BASE_W * self._scale), int(self.BASE_H * self._scale))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        full = self.rect()

        # Selected capsule lifts slightly out of the wall, the way the Big
        # Picture cursor makes the focused item feel picked up.
        inset = 0 if self._selected else max(2, int(3 * self._scale))
        art = full.adjusted(inset, inset, -inset, -inset)

        painter.fillRect(art, QColor("#0d1319"))
        if self._loading or self._cover.isNull():
            _paint_shimmer(painter, art, self._shimmer_phase)
            painter.setPen(QColor("#46586b"))
            font = painter.font()
            font.setPointSize(max(8, int(9 * self._scale)))
            font.setBold(True)
            painter.setFont(font)
            metrics = painter.fontMetrics()
            title = metrics.elidedText(
                str(self._game.get("title") or ""), Qt.ElideRight, art.width() - 20
            )
            painter.drawText(art.adjusted(10, 0, -10, 0), Qt.AlignCenter | Qt.TextWordWrap, title)
        else:
            _draw_cover(painter, art, self._cover, self._reveal)
            if self._hover > 0.0 and not self._selected:
                painter.fillRect(art, QColor(255, 255, 255, int(18 * self._hover)))

        if self._badge:
            font = painter.font()
            font.setPointSize(max(7, int(7.5 * self._scale)))
            font.setBold(True)
            painter.setFont(font)
            metrics = painter.fontMetrics()
            text_w = metrics.horizontalAdvance(self._badge)
            badge = QRect(art.x(), art.y(), text_w + int(18 * self._scale), int(22 * self._scale))
            painter.fillRect(badge, QColor("#1a9fff"))
            painter.setPen(QColor("#ffffff"))
            painter.drawText(badge, Qt.AlignCenter, self._badge)

        if self._progress is not None:
            bar_h = max(4, int(6 * self._scale))
            bar = QRect(art.x(), art.bottom() - bar_h + 1, art.width(), bar_h)
            painter.fillRect(bar, QColor(0, 0, 0, 200))
            fill = int(bar.width() * max(0, min(100, self._progress)) / 100.0)
            painter.fillRect(QRect(bar.x(), bar.y(), fill, bar_h), QColor("#66c0f4"))

        if self._selected:
            painter.setPen(QPen(QColor("#ffffff"), max(3, int(3 * self._scale))))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(full.adjusted(1, 1, -2, -2))
        painter.end()


class _FlowLayout(QLayout):
    """Left-to-right layout that wraps to the next line when it runs out of
    width. Gives the Big Picture wall a responsive column count."""

    def __init__(self, parent=None, margin: int = 0, h_spacing: int = 20, v_spacing: int = 20):
        super().__init__(parent)
        self._h_spacing = h_spacing
        self._v_spacing = v_spacing
        self._items: list = []
        self.setContentsMargins(margin, margin, margin, margin)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientations()

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def _do_layout(self, rect: QRect, test_only: bool) -> int:
        left, top, right, bottom = self.getContentsMargins()
        effective = rect.adjusted(left, top, -right, -bottom)
        x, y = effective.x(), effective.y()
        line_height = 0
        for item in self._items:
            hint = item.sizeHint()
            next_x = x + hint.width() + self._h_spacing
            if next_x - self._h_spacing > effective.right() and line_height > 0:
                x = effective.x()
                y += line_height + self._v_spacing
                next_x = x + hint.width() + self._h_spacing
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x = next_x
            line_height = max(line_height, hint.height())
        return y + line_height - rect.y() + bottom


class _LibraryViewBase(QScrollArea):
    """Shared sync logic. The owner keeps a hidden QListWidget as the single
    source of truth; these views mirror it and drive it back through
    `tileActivated` carrying the hidden list's row index."""

    tileActivated = Signal(int)
    coverRequested = Signal(str, str)  # key, cover url

    ITEM_CLASS = _ArtworkWidget

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.NoFrame)
        self._items: dict[str, _ArtworkWidget] = {}
        self._current_key: str | None = None
        self._scale = 1.0
        self.verticalScrollBar().valueChanged.connect(self._ensure_visible_covers)

    # -- subclass hooks --------------------------------------------------

    def _add_item_widget(self, widget, index: int) -> None:
        raise NotImplementedError

    def _remove_item_widget(self, widget) -> None:
        raise NotImplementedError

    def _reposition(self, widget, index: int) -> None:
        raise NotImplementedError

    def _columns(self) -> int:
        return 1

    # -- public API ------------------------------------------------------

    def show_loading_skeleton(self, count: int = 12) -> None:
        self._clear_all()
        for i in range(count):
            key = f"__skeleton_{i}__"
            widget = self.ITEM_CLASS({"title": ""}, "", i, key, scale=self._scale)
            widget.setEnabled(False)
            self._add_item_widget(widget, i)
            self._items[key] = widget

    def set_items(self, rows: list[tuple[str, dict, str]]) -> None:
        wanted = {key for key, _, _ in rows}
        for key in list(self._items.keys()):
            if key not in wanted:
                self._remove_item_widget(self._items.pop(key))

        for index, (key, game, channel) in enumerate(rows):
            widget = self._items.get(key)
            if widget is None:
                widget = self.ITEM_CLASS(game, channel, index, key, scale=self._scale)
                widget.activated.connect(lambda k=key: self._activate(k))
                widget.focused.connect(lambda k=key: self._set_current_key(k))
                self._add_item_widget(widget, index)
                self._items[key] = widget
            else:
                widget.row = index
                widget.set_game(game, channel)
            self._reposition(widget, index)
        self._ensure_visible_covers()

    def set_current_row(self, row: int) -> None:
        target = None
        for key, widget in self._items.items():
            selected = widget.row == row
            widget.set_selected(selected)
            if selected:
                target = key
        self._current_key = target
        if target is not None:
            self.ensureWidgetVisible(self._items[target], 40, 60)

    def set_tile_progress(self, key: str, percent: int | None) -> None:
        widget = self._items.get(key)
        if widget is not None:
            widget.set_progress(percent)

    def set_tile_installed(self, key: str, installed: bool) -> None:
        widget = self._items.get(key)
        if widget is not None:
            widget.set_installed(installed)

    def set_tile_badge(self, key: str, text: str) -> None:
        widget = self._items.get(key)
        if widget is not None:
            widget.set_badge(text)

    def set_tile_cover(self, key: str, pixmap: QPixmap) -> None:
        widget = self._items.get(key)
        if widget is not None:
            widget.set_cover(pixmap)

    def set_scale(self, factor: float) -> None:
        self._scale = factor
        for widget in self._items.values():
            widget.set_scale(factor)

    def is_selection_on_last_row(self) -> bool:
        ordered = sorted(self._items.values(), key=lambda w: w.row)
        if not ordered or self._current_key is None:
            return False
        index = next((i for i, w in enumerate(ordered) if w.key == self._current_key), 0)
        return index >= len(ordered) - self._columns()

    def focus_selection(self) -> None:
        if self._current_key and self._current_key in self._items:
            self._items[self._current_key].setFocus()
        else:
            self.setFocus()

    # -- internals -------------------------------------------------------

    def _clear_all(self) -> None:
        for widget in self._items.values():
            self._remove_item_widget(widget)
        self._items.clear()
        self._current_key = None

    def _activate(self, key: str) -> None:
        widget = self._items.get(key)
        if widget is not None:
            self.tileActivated.emit(widget.row)

    def _set_current_key(self, key: str) -> None:
        self._current_key = key

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._ensure_visible_covers()

    def _ensure_visible_covers(self) -> None:
        viewport = QRect(
            self.horizontalScrollBar().value(),
            self.verticalScrollBar().value(),
            self.viewport().width(),
            self.viewport().height(),
        ).adjusted(0, -500, 0, 500)
        for key, widget in self._items.items():
            if widget.cover_requested or key.startswith("__skeleton_"):
                continue
            if not widget.geometry().intersects(viewport):
                continue
            widget.cover_requested = True
            if widget.cover_url:
                self.coverRequested.emit(key, widget.cover_url)

    def keyPressEvent(self, event):
        key = event.key()
        if key in (Qt.Key_Return, Qt.Key_Enter):
            if self._current_key is not None:
                self._activate(self._current_key)
            return
        columns = self._columns()
        step = {
            Qt.Key_Left: -1,
            Qt.Key_Right: 1,
            Qt.Key_Up: -columns,
            Qt.Key_Down: columns,
        }.get(key)
        if step is not None:
            self._move_selection_by(step)
            return
        super().keyPressEvent(event)

    def _move_selection_by(self, delta: int) -> None:
        ordered = sorted(self._items.values(), key=lambda w: w.row)
        if not ordered:
            return
        index = next((i for i, w in enumerate(ordered) if w.key == self._current_key), 0)
        new_index = max(0, min(len(ordered) - 1, index + delta))
        self.tileActivated.emit(ordered[new_index].row)


class GameListView(_LibraryViewBase):
    """Desktop client left rail."""

    ITEM_CLASS = GameListRow

    def __init__(self, parent=None):
        super().__init__(parent)
        content = QWidget()
        content.setObjectName("gameListContent")
        self._layout = QVBoxLayout(content)
        self._layout.setContentsMargins(0, 2, 0, 2)
        self._layout.setSpacing(0)
        self._layout.addStretch(1)
        self.setWidget(content)

    def _add_item_widget(self, widget, index: int) -> None:
        self._layout.insertWidget(self._layout.count() - 1, widget)

    def _remove_item_widget(self, widget) -> None:
        self._layout.removeWidget(widget)
        widget.setParent(None)
        widget.deleteLater()

    def _reposition(self, widget, index: int) -> None:
        self._layout.removeWidget(widget)
        self._layout.insertWidget(index, widget)

    def _columns(self) -> int:
        return 1


class GameGridView(_LibraryViewBase):
    """Big Picture capsule wall."""

    ITEM_CLASS = GameCapsule

    def __init__(self, parent=None):
        super().__init__(parent)
        content = QWidget()
        content.setObjectName("gameGridContent")
        self._flow = _FlowLayout(content, margin=4, h_spacing=20, v_spacing=22)
        content.setLayout(self._flow)
        self.setWidget(content)

    def _add_item_widget(self, widget, index: int) -> None:
        self._flow.addWidget(widget)

    def _remove_item_widget(self, widget) -> None:
        self._flow.removeWidget(widget)
        widget.setParent(None)
        widget.deleteLater()

    def _reposition(self, widget, index: int) -> None:
        self._flow.removeWidget(widget)
        self._flow.addWidget(widget)

    def _columns(self) -> int:
        capsule_w = int(GameCapsule.BASE_W * self._scale) + self._flow._h_spacing
        return max(1, self.viewport().width() // max(capsule_w, 1))


THUMB_W = 292
THUMB_H = 164


class ScreenshotThumb(QFrame):
    def __init__(self, index: int, parent=None):
        super().__init__(parent)
        self.index = index
        self.setFixedSize(THUMB_W, THUMB_H)
        self._pixmap = QPixmap()
        self._loading = True
        self._reveal = 0.0
        self._shimmer_phase = 0.0

        self._shimmer_anim = QVariantAnimation(self)
        self._shimmer_anim.setStartValue(0.0)
        self._shimmer_anim.setEndValue(1.0)
        self._shimmer_anim.setDuration(1150)
        self._shimmer_anim.setLoopCount(-1)
        self._shimmer_anim.valueChanged.connect(self._on_shimmer)
        self._shimmer_anim.start()

        self._reveal_anim = QVariantAnimation(self)
        self._reveal_anim.setDuration(220)
        self._reveal_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._reveal_anim.valueChanged.connect(self._on_reveal)

    def _on_shimmer(self, value):
        self._shimmer_phase = float(value)
        if self._loading:
            self.update()

    def _on_reveal(self, value):
        self._reveal = float(value)
        self.update()

    def set_pixmap(self, pixmap: QPixmap) -> None:
        self._loading = False
        self._pixmap = pixmap
        self._shimmer_anim.stop()
        self._reveal_anim.stop()
        self._reveal_anim.setStartValue(0.0)
        self._reveal_anim.setEndValue(1.0)
        self._reveal_anim.start()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        rect = self.rect().adjusted(0, 0, -1, -1)
        painter.fillRect(rect, QColor("#0d1319"))
        if self._loading or self._pixmap.isNull():
            _paint_shimmer(painter, rect, self._shimmer_phase)
        else:
            _draw_cover(painter, rect, self._pixmap, self._reveal)
        painter.setPen(QColor("#2a3f57"))
        painter.drawRect(rect)
        painter.end()


class ScreenshotGallery(QScrollArea):
    """Horizontal strip of screenshots with its own empty state, so a game
    with no `artwork.screenshots` still reads as intentional rather than
    broken."""

    thumbRequested = Signal(int, str)  # index, url

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFixedHeight(THUMB_H + 18)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.NoFrame)

        content = QWidget()
        self._layout = QHBoxLayout(content)
        self._layout.setContentsMargins(0, 4, 0, 4)
        self._layout.setSpacing(10)
        self._empty = QLabel("Bu yayın için ekran görüntüsü eklenmemiş.")
        self._empty.setObjectName("muted")
        self._layout.addWidget(self._empty)
        self._layout.addStretch(1)
        self.setWidget(content)
        self._thumbs: list[ScreenshotThumb] = []

    def set_urls(self, urls: list[str]) -> None:
        for thumb in self._thumbs:
            self._layout.removeWidget(thumb)
            thumb.setParent(None)
            thumb.deleteLater()
        self._thumbs.clear()

        if not urls:
            self._empty.show()
            return

        self._empty.hide()
        for index, url in enumerate(urls):
            thumb = ScreenshotThumb(index)
            self._layout.insertWidget(index, thumb)
            self._thumbs.append(thumb)
            self.thumbRequested.emit(index, url)

    def set_thumb_pixmap(self, index: int, pixmap: QPixmap) -> None:
        if 0 <= index < len(self._thumbs):
            self._thumbs[index].set_pixmap(pixmap)
