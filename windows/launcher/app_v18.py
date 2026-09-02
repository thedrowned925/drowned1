"""v18: a from-scratch Epic Games-style home screen.

v17 reused the existing Big Picture widgets (GameCapsule / GameGridView /
BigPictureView from library_grid.py) and just changed which page was shown
by default. That still painted with the exact same tile/shimmer/hover code
that had been sitting in this repo since v9-v10, so visually nothing about
the actual grid or hero had changed - only its position in the navigation
flow. This version instead writes new widgets: EpicTile, EpicGrid,
EpicTopBar and EpicHeroBanner all have their own paintEvent/animation code,
none of it subclassed from library_grid.py.

The backend contract is untouched (same rule every presentation-only
version in this chain follows): the fresh widgets are wired into the
existing render_library / library_selection_changed / _apply_cover /
update_install_state_ui extension points the same way app_v10 already wires
its own Big Picture view, and the real action buttons call straight into
the unmodified install/verify/uninstall/pause/cancel backend methods.
"""

from __future__ import annotations

import math
import sys

from PySide6.QtCore import QEasingCurve, QRect, QRectF, Qt, QVariantAnimation, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSplashScreen,
    QVBoxLayout,
    QWidget,
)

import app_v16 as previous

APP_VERSION = "0.18.0"
BASE = previous.BASE


V18_STYLE = previous.V16_STYLE + r"""
/* v18: freshly painted Epic-style home screen (EpicTile/EpicGrid/
   EpicTopBar/EpicHeroBanner below) instead of the reused Big Picture
   widgets. */
QFrame#epicTopBar { background:#0c0e0f; border-bottom:1px solid rgba(255,255,255,20); }
QLabel#epicBrand { color:#ffffff; font-size:13px; font-weight:900; letter-spacing:2px; }
QLabel#epicTab, QLabel#epicTabActive {
    color:rgba(255,255,255,110); font-size:10px; font-weight:850; letter-spacing:1px;
    padding:8px 14px; border-bottom:2px solid transparent;
}
QLabel#epicTab:hover { color:#ffffff; }
QLabel#epicTabActive { color:#ffffff; border-bottom-color:#ffffff; }
QLineEdit#epicSearch {
    background:rgba(255,255,255,9); border:1px solid rgba(255,255,255,26);
    border-radius:15px; padding:7px 14px; font-size:11px;
}
QPushButton#epicChrome {
    background:transparent; border:1px solid rgba(255,255,255,28);
    color:rgba(255,255,255,190); border-radius:14px; padding:6px 12px;
    font-size:10px; font-weight:800;
}
QPushButton#epicChrome:hover { background:rgba(255,255,255,14); color:#fff; }

QFrame#epicHero { background:#101314; border:0; }
QLabel#epicHeroEyebrow {
    color:rgba(255,255,255,150); font-size:9px; font-weight:900; letter-spacing:2px;
}
QLabel#epicHeroTitle { color:#ffffff; font-size:30px; font-weight:900; }
QLabel#epicHeroMeta { color:#8fd7ff; font-size:10px; font-weight:850; }
QLabel#epicHeroDesc { color:rgba(255,255,255,195); font-size:12px; }
QPushButton#epicInstall {
    min-width:140px; min-height:36px; padding:8px 22px; border-radius:18px;
    background:#ffffff; color:#101112; border:1px solid #ffffff;
    font-size:11px; font-weight:950;
}
QPushButton#epicInstall:hover { background:#eaeaea; }
QPushButton#epicInstall:disabled { background:rgba(255,255,255,35); color:rgba(0,0,0,90); border-color:rgba(255,255,255,35); }
QPushButton#epicSecondary {
    min-height:36px; padding:8px 18px; border-radius:18px;
    background:transparent; border:1px solid rgba(255,255,255,45); color:rgba(255,255,255,210);
}
QPushButton#epicSecondary:hover { background:rgba(255,255,255,14); }
QPushButton#epicDanger {
    min-height:36px; padding:8px 18px; border-radius:18px;
    background:rgba(120,40,50,110); border:1px solid rgba(220,90,105,90); color:#ffd9dd;
}
QProgressBar#epicProgress {
    min-height:6px; max-height:6px; background:rgba(255,255,255,16); border:0; border-radius:3px;
}
QProgressBar#epicProgress::chunk { background:#ffffff; border-radius:3px; }
QLabel#epicProgressLabel { color:rgba(255,255,255,190); font-size:10px; font-weight:750; }

QScrollArea#epicGridScroll { background:#121415; border:0; }
QWidget#epicGridContent { background:#121415; }
"""


def _paint_epic_shimmer(painter: QPainter, rect: QRect, phase: float) -> None:
    band = max(rect.width() * 0.6, 1)
    x = rect.x() - band + (rect.width() + band * 2) * phase
    grad = QLinearGradient(x, rect.y(), x + band, rect.y() + rect.height())
    grad.setColorAt(0.0, QColor(255, 255, 255, 0))
    grad.setColorAt(0.5, QColor(255, 255, 255, 16))
    grad.setColorAt(1.0, QColor(255, 255, 255, 0))
    painter.fillRect(rect, grad)


class EpicTile(QFrame):
    """One portrait tile: rounded corners, cover art, bottom title overlay
    baked straight into the paint (Epic never draws a title below the
    art the way the old Steam-style capsule did), a soft hover "pop" done
    by zooming the art a few percent rather than animating geometry, and a
    drop shadow that grows on hover for a lift effect."""

    activated = Signal()

    WIDTH = 196
    HEIGHT = 264

    def __init__(self, key: str, row: int, parent=None):
        super().__init__(parent)
        self.key = key
        self.row = row
        self.cover_requested = False
        self._cover_url = ""
        self._title = ""
        self._cover = QPixmap()
        self._loading = True
        self._selected = False
        self._progress: int | None = None
        self._badge = ""
        self._reveal = 0.0
        self._shimmer_phase = 0.0
        self._lift = 0.0

        self.setFixedSize(self.WIDTH, self.HEIGHT)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)

        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setBlurRadius(4)
        self._shadow.setOffset(0, 3)
        self._shadow.setColor(QColor(0, 0, 0, 140))
        self.setGraphicsEffect(self._shadow)

        self._shimmer_anim = QVariantAnimation(self)
        self._shimmer_anim.setStartValue(0.0)
        self._shimmer_anim.setEndValue(1.0)
        self._shimmer_anim.setDuration(1300)
        self._shimmer_anim.setLoopCount(-1)
        self._shimmer_anim.valueChanged.connect(self._on_shimmer)
        self._shimmer_anim.start()

        self._reveal_anim = QVariantAnimation(self)
        self._reveal_anim.setDuration(240)
        self._reveal_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._reveal_anim.valueChanged.connect(self._on_reveal)

        self._lift_anim = QVariantAnimation(self)
        self._lift_anim.setDuration(150)
        self._lift_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._lift_anim.valueChanged.connect(self._on_lift)

    def set_title(self, title: str) -> None:
        self._title = title
        self.update()

    def set_cover(self, pixmap: QPixmap | None) -> None:
        self._loading = pixmap is None
        self._cover = pixmap if pixmap is not None else QPixmap()
        if pixmap is not None:
            self._shimmer_anim.stop()
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
        self._badge = text
        self.update()

    @property
    def cover_url(self) -> str:
        return self._cover_url

    def _on_shimmer(self, value):
        self._shimmer_phase = float(value)
        if self._loading:
            self.update()

    def _on_reveal(self, value):
        self._reveal = float(value)
        self.update()

    def _on_lift(self, value):
        self._lift = float(value)
        self._shadow.setBlurRadius(4 + 22 * self._lift)
        self._shadow.setOffset(0, 3 + 9 * self._lift)
        self.update()

    def enterEvent(self, event):
        self._lift_anim.stop()
        self._lift_anim.setStartValue(self._lift)
        self._lift_anim.setEndValue(1.0)
        self._lift_anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._lift_anim.stop()
        self._lift_anim.setStartValue(self._lift)
        self._lift_anim.setEndValue(0.0)
        self._lift_anim.start()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.setFocus(Qt.MouseFocusReason)
            self.activated.emit()
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.activated.emit()
            return
        super().keyPressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        rect = self.rect()
        radius = 12.0

        path = QPainterPath()
        path.addRoundedRect(QRectF(rect), radius, radius)
        painter.setClipPath(path)
        painter.fillRect(rect, QColor("#181c20"))

        if self._loading or self._cover.isNull():
            _paint_epic_shimmer(painter, rect, self._shimmer_phase)
        else:
            zoom = 1.0 + 0.05 * self._lift
            target_w = int(rect.width() * zoom)
            target_h = int(rect.height() * zoom)
            scaled = self._cover.scaled(target_w, target_h, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            sx = max((scaled.width() - rect.width()) // 2, 0)
            sy = max((scaled.height() - rect.height()) // 2, 0)
            painter.setOpacity(self._reveal)
            painter.drawPixmap(rect, scaled, QRect(sx, sy, rect.width(), rect.height()))
            painter.setOpacity(1.0)

        scrim = QLinearGradient(0, rect.height() * 0.42, 0, rect.height())
        scrim.setColorAt(0.0, QColor(6, 8, 9, 0))
        scrim.setColorAt(1.0, QColor(6, 8, 9, 235))
        painter.fillRect(rect, QBrush(scrim))

        if self._badge:
            font = painter.font()
            font.setPointSize(7)
            font.setBold(True)
            painter.setFont(font)
            metrics = painter.fontMetrics()
            badge_rect = QRect(8, 8, metrics.horizontalAdvance(self._badge) + 14, 18)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor("#3fa9f5"))
            painter.drawRoundedRect(badge_rect, 4, 4)
            painter.setPen(QColor("#ffffff"))
            painter.drawText(badge_rect, Qt.AlignCenter, self._badge)

        painter.setPen(QColor("#ffffff"))
        font = painter.font()
        font.setPointSize(9)
        font.setBold(True)
        painter.setFont(font)
        text_rect = rect.adjusted(10, 0, -10, -10)
        metrics = painter.fontMetrics()
        title = metrics.elidedText(self._title, Qt.ElideRight, text_rect.width())
        painter.drawText(text_rect, int(Qt.AlignLeft | Qt.AlignBottom), title)

        if self._progress is not None:
            bar = QRect(rect.x(), rect.bottom() - 4, rect.width(), 4)
            painter.fillRect(bar, QColor(0, 0, 0, 210))
            fill = int(bar.width() * max(0, min(100, self._progress)) / 100.0)
            painter.fillRect(QRect(bar.x(), bar.y(), fill, bar.height()), QColor("#ffffff"))

        if self._selected:
            painter.setPen(QPen(QColor("#ffffff"), 3))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(QRectF(rect).adjusted(1.5, 1.5, -1.5, -1.5), radius, radius)
        painter.end()


class EpicGrid(QScrollArea):
    """Manually laid-out tile wall: no QLayout subclass, just geometry
    placement recomputed on resize. Exposes the same small surface the
    backend already knows how to drive a library view through (set_items /
    set_current_row / set_tile_progress / set_tile_badge / set_tile_cover /
    focus_selection), so it plugs into the existing render_library /
    _apply_cover extension points without changing any backend code."""

    tileActivated = Signal(int)
    coverRequested = Signal(str, str)

    GAP = 22

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("epicGridScroll")
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._content = QWidget()
        self._content.setObjectName("epicGridContent")
        self.setWidget(self._content)
        self._tiles: dict[str, EpicTile] = {}
        self._order: list[str] = []
        self._current_key: str | None = None
        self.verticalScrollBar().valueChanged.connect(self._ensure_visible_covers)

    def show_loading_skeleton(self, count: int = 12) -> None:
        self._clear()
        for index in range(count):
            key = f"__skeleton_{index}__"
            tile = self._make_tile(key, index, "", "")
            tile.setEnabled(False)
            self._order.append(key)
        self._relayout()

    def set_items(self, rows: list[tuple[str, dict, str]]) -> None:
        wanted = {key for key, _, _ in rows}
        for key in list(self._tiles.keys()):
            if key not in wanted:
                self._tiles.pop(key).deleteLater()
        self._order = []
        for index, (key, game, channel) in enumerate(rows):
            title = str(game.get("title") or "")
            cover_url = str((game.get("artwork") or {}).get("cover") or "")
            tile = self._tiles.get(key)
            if tile is None:
                tile = self._make_tile(key, index, title, cover_url)
            else:
                tile.row = index
                tile.set_title(title)
                tile._cover_url = cover_url
            self._order.append(key)
        self._relayout()
        self._ensure_visible_covers()

    def _make_tile(self, key: str, index: int, title: str, cover_url: str) -> EpicTile:
        tile = EpicTile(key, index, self._content)
        tile.set_title(title)
        tile._cover_url = cover_url
        tile.activated.connect(lambda k=key: self._activate(k))
        self._tiles[key] = tile
        tile.show()
        return tile

    def _activate(self, key: str) -> None:
        tile = self._tiles.get(key)
        if tile is not None:
            self.tileActivated.emit(tile.row)

    def set_current_row(self, row: int) -> None:
        target = None
        for key, tile in self._tiles.items():
            selected = tile.row == row
            tile.set_selected(selected)
            if selected:
                target = key
        self._current_key = target
        if target is not None:
            self.ensureWidgetVisible(self._tiles[target], 30, 60)

    def set_tile_progress(self, key: str, percent: int | None) -> None:
        tile = self._tiles.get(key)
        if tile is not None:
            tile.set_progress(percent)

    def set_tile_badge(self, key: str, text: str) -> None:
        tile = self._tiles.get(key)
        if tile is not None:
            tile.set_badge(text)

    def set_tile_cover(self, key: str, pixmap: QPixmap) -> None:
        tile = self._tiles.get(key)
        if tile is not None:
            tile.set_cover(pixmap)

    def set_tile_installed(self, key: str, installed: bool) -> None:
        pass

    def focus_selection(self) -> None:
        if self._current_key and self._current_key in self._tiles:
            self._tiles[self._current_key].setFocus()

    def is_selection_on_last_row(self) -> bool:
        return False

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._relayout()
        self._ensure_visible_covers()

    def _columns(self) -> int:
        step = EpicTile.WIDTH + self.GAP
        return max(1, self.viewport().width() // step)

    def _relayout(self) -> None:
        columns = self._columns()
        step_x = EpicTile.WIDTH + self.GAP
        step_y = EpicTile.HEIGHT + self.GAP
        x, y, col = self.GAP, self.GAP, 0
        for key in self._order:
            tile = self._tiles.get(key)
            if tile is None:
                continue
            tile.move(x, y)
            col += 1
            if col >= columns:
                col = 0
                x = self.GAP
                y += step_y
            else:
                x += step_x
        rows = -(-len(self._order) // max(columns, 1)) if self._order else 0
        content_h = self.GAP + rows * step_y
        content_w = self.GAP + columns * step_x
        self._content.setMinimumSize(max(content_w, self.viewport().width()), content_h)

    def _ensure_visible_covers(self) -> None:
        viewport_rect = QRect(
            0, self.verticalScrollBar().value(), self.viewport().width(), self.viewport().height()
        ).adjusted(0, -400, 0, 400)
        for key, tile in self._tiles.items():
            if tile.cover_requested or key.startswith("__skeleton_"):
                continue
            if not tile.geometry().intersects(viewport_rect):
                continue
            tile.cover_requested = True
            if tile.cover_url:
                self.coverRequested.emit(key, tile.cover_url)

    def _clear(self) -> None:
        for tile in self._tiles.values():
            tile.deleteLater()
        self._tiles.clear()
        self._order.clear()
        self._current_key = None


class _EpicTabLabel(QLabel):
    clicked = Signal()

    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class EpicTopBar(QFrame):
    searchChanged = Signal(str)
    tabChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("epicTopBar")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(26, 12, 26, 12)
        layout.setSpacing(16)

        brand = QLabel("DROWNED")
        brand.setObjectName("epicBrand")
        layout.addWidget(brand)
        layout.addSpacing(14)

        self._tabs: list[_EpicTabLabel] = []
        for index, text in enumerate(("TÜM OYUNLAR", "KURULU")):
            label = _EpicTabLabel(text)
            label.setObjectName("epicTabActive" if index == 0 else "epicTab")
            label.clicked.connect(lambda i=index: self._select_tab(i))
            self._tabs.append(label)
            layout.addWidget(label)
        self._tab_index = 0

        layout.addStretch(1)

        self.search = QLineEdit()
        self.search.setObjectName("epicSearch")
        self.search.setPlaceholderText("Kütüphanede ara")
        self.search.setClearButtonEnabled(True)
        self.search.setFixedWidth(260)
        self.search.textChanged.connect(self.searchChanged)
        layout.addWidget(self.search)

        self.classic_button = QPushButton("Klasik görünüm")
        self.classic_button.setObjectName("epicChrome")
        layout.addWidget(self.classic_button)
        self.refresh_button = QPushButton("↻")
        self.refresh_button.setObjectName("epicChrome")
        self.refresh_button.setToolTip("Kataloğu yenile")
        layout.addWidget(self.refresh_button)
        self.settings_button = QPushButton("⚙")
        self.settings_button.setObjectName("epicChrome")
        self.settings_button.setToolTip("Ayarlar")
        layout.addWidget(self.settings_button)

    def _select_tab(self, index: int) -> None:
        if index == self._tab_index:
            return
        self._tab_index = index
        for i, label in enumerate(self._tabs):
            label.setObjectName("epicTabActive" if i == index else "epicTab")
            label.style().unpolish(label)
            label.style().polish(label)
        self.tabChanged.emit(index)


class EpicHeroBanner(QFrame):
    """Currently-selected game's banner: slow Ken-Burns drift on the art,
    title/meta/description, and the real install/verify/uninstall/pause/
    cancel buttons wired straight to the backend by the owning Launcher -
    Epic's home screen never navigates away to a separate page to install,
    it happens right here."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("epicHero")
        self.setMinimumHeight(320)
        self.setMaximumHeight(380)
        self._hero = QPixmap()
        self._phase = 0.0

        self._zoom_anim = QVariantAnimation(self)
        self._zoom_anim.setStartValue(0.0)
        self._zoom_anim.setEndValue(1.0)
        self._zoom_anim.setDuration(17000)
        self._zoom_anim.setLoopCount(-1)
        self._zoom_anim.setEasingCurve(QEasingCurve.InOutSine)
        self._zoom_anim.valueChanged.connect(self._on_zoom)
        self._zoom_anim.start()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 0, 36, 24)
        layout.addStretch(1)

        eyebrow = QLabel("SEÇİLİ OYUN")
        eyebrow.setObjectName("epicHeroEyebrow")
        layout.addWidget(eyebrow)

        self.title = QLabel("Kütüphane yükleniyor…")
        self.title.setObjectName("epicHeroTitle")
        layout.addWidget(self.title)

        self.meta = QLabel("")
        self.meta.setObjectName("epicHeroMeta")
        layout.addWidget(self.meta)

        self.description = QLabel("")
        self.description.setObjectName("epicHeroDesc")
        self.description.setWordWrap(True)
        self.description.setMaximumWidth(640)
        layout.addWidget(self.description)
        layout.addSpacing(14)

        actions = QHBoxLayout()
        actions.setSpacing(10)
        self.install_btn = QPushButton("YÜKLE")
        self.install_btn.setObjectName("epicInstall")
        self.install_btn.setEnabled(False)
        self.verify_btn = QPushButton("DOĞRULA")
        self.verify_btn.setObjectName("epicSecondary")
        self.verify_btn.setEnabled(False)
        self.uninstall_btn = QPushButton("KALDIR")
        self.uninstall_btn.setObjectName("epicDanger")
        self.uninstall_btn.setEnabled(False)
        self.pause_btn = QPushButton("DURAKLAT")
        self.pause_btn.setObjectName("epicSecondary")
        self.pause_btn.hide()
        self.cancel_btn = QPushButton("İPTAL")
        self.cancel_btn.setObjectName("epicDanger")
        self.cancel_btn.hide()
        for button in (self.install_btn, self.verify_btn, self.uninstall_btn, self.pause_btn, self.cancel_btn):
            button.setMinimumHeight(38)
            actions.addWidget(button)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.progress_row = QWidget()
        self.progress_row.hide()
        progress_layout = QVBoxLayout(self.progress_row)
        progress_layout.setContentsMargins(0, 12, 0, 0)
        progress_layout.setSpacing(4)
        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("epicProgress")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setTextVisible(False)
        self.progress_label = QLabel("")
        self.progress_label.setObjectName("epicProgressLabel")
        progress_layout.addWidget(self.progress_bar)
        progress_layout.addWidget(self.progress_label)
        layout.addWidget(self.progress_row)

    def _on_zoom(self, value):
        self._phase = float(value)
        self.update()

    def set_hero(self, pixmap: QPixmap | None) -> None:
        self._hero = pixmap if pixmap is not None else QPixmap()
        self.update()

    def set_content(self, title: str, meta: str, description: str) -> None:
        self.title.setText(title)
        self.meta.setText(meta)
        self.description.setText(description)

    def set_progress(self, percent: int, status_text: str, percent_text: str) -> None:
        self.progress_bar.setValue(max(0, min(100, int(percent))))
        self.progress_label.setText(f"{status_text}  •  {percent_text}".strip(" •"))

    def paintEvent(self, event):
        QFrame.paintEvent(self, event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        rect = self.rect()

        if not self._hero.isNull() and rect.width() > 0 and rect.height() > 0:
            wobble = math.sin(self._phase * math.tau)
            zoom = 1.05 + 0.02 * math.cos(self._phase * math.tau)
            target_w = max(int(rect.width() * zoom), rect.width())
            target_h = max(int(rect.height() * zoom), rect.height())
            scaled = self._hero.scaled(target_w, target_h, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            overflow_x = max(scaled.width() - rect.width(), 0)
            overflow_y = max(scaled.height() - rect.height(), 0)
            sx = int(overflow_x * (0.5 + 0.1 * wobble))
            sy = int(overflow_y * 0.4)
            source = scaled.rect().adjusted(sx, sy, -(overflow_x - sx), -(overflow_y - sy))
            painter.drawPixmap(rect, scaled, source)
        else:
            gradient = QLinearGradient(0, 0, rect.width(), rect.height())
            gradient.setColorAt(0, QColor("#1b2024"))
            gradient.setColorAt(1, QColor("#0d0f10"))
            painter.fillRect(rect, gradient)

        scrim = QLinearGradient(0, rect.height() * 0.2, 0, rect.height())
        scrim.setColorAt(0.0, QColor(9, 11, 12, 0))
        scrim.setColorAt(1.0, QColor(9, 11, 12, 250))
        painter.fillRect(rect, QBrush(scrim))
        painter.end()


class EpicHomePage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.topbar = EpicTopBar()
        outer.addWidget(self.topbar)
        self.hero = EpicHeroBanner()
        outer.addWidget(self.hero)
        self.grid = EpicGrid()
        outer.addWidget(self.grid, 1)


class Launcher(previous.Launcher):
    """Adds the from-scratch Epic-style home page as the default view.
    Everything below only talks to the same extension points app_v10's own
    Big Picture support already uses (render_library / _apply_cover /
    library_selection_changed / update_install_state_ui), so no backend
    method is touched."""

    def __init__(self):
        super().__init__()
        QApplication.instance().setStyleSheet(V18_STYLE)
        self.setWindowTitle(f"Drowned Launcher {APP_VERSION} • Epic tarzı (sıfırdan)")
        self.resize(max(self.width(), 1500), max(self.height(), 920))
        self._build_epic_home()
        self._wire_epic_home()
        self._show_epic_home()

    def _build_epic_home(self):
        self.epic_page = EpicHomePage()
        self.main_stack.addWidget(self.epic_page)
        self._epic_index = self.main_stack.count() - 1
        self.epic_topbar = self.epic_page.topbar
        self.epic_hero = self.epic_page.hero
        self.epic_grid = self.epic_page.grid

    def _wire_epic_home(self):
        self.epic_grid.tileActivated.connect(self.library.setCurrentRow)
        self.epic_grid.coverRequested.connect(self._on_cover_requested)
        self.epic_grid.show_loading_skeleton(12)

        self.epic_topbar.searchChanged.connect(self._on_epic_search)
        self.epic_topbar.tabChanged.connect(lambda _index: self.render_library())
        self.epic_topbar.classic_button.clicked.connect(self._show_classic_shell)
        self.epic_topbar.refresh_button.clicked.connect(self.load_catalog)
        self.epic_topbar.settings_button.clicked.connect(self.open_settings)

        self.epic_hero.install_btn.clicked.connect(self.install_current_game)
        self.epic_hero.verify_btn.clicked.connect(self.verify_current_game)
        self.epic_hero.uninstall_btn.clicked.connect(self.uninstall_current_game)
        self.epic_hero.pause_btn.clicked.connect(self.toggle_pause)
        self.epic_hero.cancel_btn.clicked.connect(self.cancel_download)

        # install_progress() (backend, not overridable here) already updates
        # action_dl_bar/status/progress_text on every tick; mirroring the
        # progress bar's own valueChanged signal is enough to stay live
        # without polling or touching that method.
        self.action_dl_bar.valueChanged.connect(self._sync_epic_progress)

    def _on_epic_search(self, text: str) -> None:
        self.search.setText(text)

    def _show_epic_home(self) -> None:
        self.main_stack.setCurrentIndex(self._epic_index)
        self.epic_grid.focus_selection()

    def _show_classic_shell(self) -> None:
        self.main_stack.setCurrentIndex(0)
        self.library_grid.focus_selection()

    def _toggle_big_picture(self):
        """F11: plain OS fullscreen of whichever view is showing, fully
        decoupled from view choice (that lives in _show_epic_home /
        _show_classic_shell instead)."""
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def _exit_big_picture(self):
        if self.isFullScreen():
            self.showNormal()

    def render_library(self):
        super().render_library()
        if not hasattr(self, "epic_grid"):
            return
        installed = self._installed_keys()
        show_installed_only = self.epic_topbar._tab_index == 1
        rows = []
        badges: dict[str, str] = {}
        for row in range(self.library.count()):
            payload = self.library.item(row).data(Qt.UserRole)
            if not payload:
                continue
            game, channel = payload
            key = self._key(game, channel)
            if show_installed_only and key not in installed:
                continue
            rows.append((key, game, channel))
            data = (game.get("channels") or {}).get(channel) or {}
            if self._is_recent(data):
                badges[key] = "YENİ"
        self.epic_grid.set_items(rows)
        for key, text in badges.items():
            self.epic_grid.set_tile_badge(key, text)
        self.epic_grid.set_current_row(self.library.currentRow())

    def library_selection_changed(self, current, previous_item):
        super().library_selection_changed(current, previous_item)
        self._sync_epic_hero()

    def _sync_epic_hero(self) -> None:
        if not hasattr(self, "epic_hero"):
            return
        if not self.current_game:
            self.epic_hero.set_content("Oyun seçilmedi", "", "")
            self.epic_hero.set_hero(None)
            return
        self.epic_hero.set_content(
            str(self.current_game.get("title") or "—"),
            self.meta.text(),
            str(self.current_game.get("description") or ""),
        )
        self.epic_hero.set_hero(self.hero.hero if not self.hero.hero.isNull() else None)
        self._sync_epic_actions()

    def _sync_epic_actions(self) -> None:
        if not hasattr(self, "epic_hero"):
            return
        downloading = self.download_control is not None
        self.epic_hero.install_btn.setText(self.install_button.text())
        self.epic_hero.install_btn.setEnabled(self.install_button.isEnabled())
        self.epic_hero.install_btn.setVisible(not downloading)
        self.epic_hero.verify_btn.setEnabled(self.verify_button.isEnabled())
        self.epic_hero.verify_btn.setVisible(not downloading)
        self.epic_hero.uninstall_btn.setEnabled(self.uninstall_button.isEnabled())
        self.epic_hero.uninstall_btn.setVisible(not downloading)
        self.epic_hero.pause_btn.setVisible(downloading)
        self.epic_hero.cancel_btn.setVisible(downloading)
        self.epic_hero.progress_row.setVisible(downloading)

    def update_install_state_ui(self):
        super().update_install_state_ui()
        self._sync_epic_actions()

    def _apply_cover(self, key, pixmap):
        super()._apply_cover(key, pixmap)
        if hasattr(self, "epic_grid"):
            self.epic_grid.set_tile_cover(key, pixmap)

    def _sync_epic_progress(self, value: int) -> None:
        if hasattr(self, "epic_hero"):
            self.epic_hero.set_progress(value, self.status.text(), self.progress_text.text())


def main():
    BASE.base.install_exception_hook()
    app = QApplication(sys.argv)
    app.setApplicationName("Drowned Launcher")
    app.setOrganizationName("Drowned")
    app.setStyle("Fusion")
    app.setStyleSheet(V18_STYLE)
    splash = QSplashScreen(BASE._splash_pixmap())
    splash.show()
    app.processEvents()
    win = Launcher()
    win.show()
    splash.finish(win)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
