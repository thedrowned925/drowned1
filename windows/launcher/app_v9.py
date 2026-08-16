from __future__ import annotations

import sys

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRect, Qt, QTimer, QVariantAnimation
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QProgressBar,
    QPushButton,
    QPlainTextEdit,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

import app_v4 as base
import app_v8 as previous

APP_VERSION = "0.9.0"


MODERN_STYLE = r"""
* {
    font-family: "Segoe UI Variable", "Segoe UI";
    outline: 0;
}
QWidget {
    background: #090d14;
    color: #e7edf5;
    font-size: 14px;
}
QMainWindow { background: #090d14; }
QToolTip {
    background: #151d29;
    color: #f3f6fb;
    border: 1px solid #2b3b50;
    padding: 6px 8px;
}
QFrame#topbar {
    background: #0d121b;
    border-bottom: 1px solid #1d2836;
}
QFrame#sidebar {
    background: #0c1119;
    border-right: 1px solid #1c2735;
}
QFrame#detail { background: #090d14; }
QFrame#infoCard {
    background: #0f151f;
    border: 1px solid #1d2938;
    border-radius: 18px;
}
QFrame#statCard {
    background: #121a26;
    border: 1px solid #223146;
    border-radius: 11px;
}
QFrame#downloadBar {
    background: #0d131d;
    border-top: 1px solid #1d2a39;
}
QFrame#downloadCard {
    background: #101824;
    border: 1px solid #223247;
    border-radius: 14px;
}
QLabel#brandMark {
    background: #66c0f4;
    color: #071018;
    border-radius: 10px;
    font-size: 20px;
    font-weight: 900;
}
QLabel#brand {
    color: #ffffff;
    font-size: 21px;
    font-weight: 900;
    letter-spacing: 4px;
}
QLabel#navActive {
    color: #ffffff;
    font-size: 14px;
    font-weight: 800;
    padding: 9px 13px;
    background: #182231;
    border-radius: 9px;
}
QLabel#nav {
    color: #7f8da1;
    font-size: 14px;
    font-weight: 700;
    padding: 9px 13px;
}
QLabel#section {
    color: #6f7d90;
    font-size: 11px;
    font-weight: 900;
    letter-spacing: 2px;
}
QLabel#gameTitle {
    color: #ffffff;
    font-size: 31px;
    font-weight: 850;
}
QLabel#eyebrow {
    color: #6f7d90;
    font-size: 11px;
    font-weight: 800;
    letter-spacing: 1px;
}
QLabel#metaLine {
    color: #90a1b6;
    font-size: 13px;
    font-weight: 650;
}
QLabel#description {
    color: #b9c5d4;
    font-size: 14px;
    line-height: 1.35;
}
QLabel#statValue {
    color: #eef5fd;
    font-size: 13px;
    font-weight: 800;
}
QLabel#statName {
    color: #718096;
    font-size: 10px;
    font-weight: 850;
    letter-spacing: 1px;
}
QLabel#connectionOnline {
    color: #8ee0a0;
    background: #102419;
    border: 1px solid #1f4b2d;
    border-radius: 12px;
    padding: 5px 10px;
    font-size: 11px;
    font-weight: 800;
}
QLabel#muted { color: #7f8da0; }
QLabel#downloadDot { color: #66c0f4; font-size: 16px; }
QLabel#downloadTitle { color: #f1f6fc; font-size: 13px; font-weight: 800; }
QLabel#progressText { color: #9edaff; font-size: 12px; font-weight: 750; }
QLineEdit, QComboBox {
    min-height: 20px;
    background: #111925;
    border: 1px solid #223246;
    border-radius: 10px;
    padding: 9px 11px;
    color: #dce7f3;
    selection-background-color: #2a76a7;
}
QLineEdit:hover, QComboBox:hover { border-color: #30465f; }
QLineEdit:focus, QComboBox:focus {
    border-color: #4aa9df;
    background: #131d2a;
}
QComboBox::drop-down { border: 0; width: 24px; }
QComboBox QAbstractItemView {
    background: #111925;
    color: #dce7f3;
    border: 1px solid #2a3b50;
    selection-background-color: #21364b;
    padding: 5px;
}
QListWidget {
    background: transparent;
    border: 0;
    outline: 0;
    padding: 3px;
}
QListWidget::item {
    color: #aebdce;
    padding: 11px 12px;
    margin: 2px 0;
    border-radius: 9px;
    border-left: 3px solid transparent;
}
QListWidget::item:hover {
    background: #131d2a;
    color: #ffffff;
}
QListWidget::item:selected {
    background: #18283a;
    color: #ffffff;
    border-left: 3px solid #66c0f4;
}
QPushButton {
    min-height: 22px;
    background: #182434;
    color: #c9d6e5;
    border: 1px solid #28394d;
    border-radius: 10px;
    padding: 9px 15px;
    font-weight: 750;
}
QPushButton:hover {
    background: #213249;
    color: #ffffff;
    border-color: #39516d;
}
QPushButton:pressed { background: #152131; }
QPushButton:disabled {
    background: #111720;
    color: #4f5a68;
    border-color: #1c2633;
}
QPushButton#iconButton {
    min-width: 38px;
    max-width: 38px;
    min-height: 38px;
    max-height: 38px;
    padding: 0;
    border-radius: 10px;
    font-size: 16px;
}
QPushButton#install {
    background: #7ab829;
    color: #071006;
    border: 1px solid #8bcd33;
    border-radius: 11px;
    min-height: 27px;
    padding: 10px 23px;
    font-size: 14px;
    font-weight: 900;
}
QPushButton#install:hover {
    background: #8bcd33;
    border-color: #a0df47;
}
QPushButton#secondary {
    background: #172334;
    color: #c8d7e8;
    border: 1px solid #293d55;
}
QPushButton#secondary:hover {
    background: #20334a;
    border-color: #3b5877;
}
QPushButton#danger {
    background: #2a171d;
    color: #efb9c1;
    border: 1px solid #56303a;
}
QPushButton#danger:hover {
    background: #3a1d25;
    color: #ffd8df;
    border-color: #78404d;
}
QProgressBar {
    min-height: 9px;
    max-height: 9px;
    background: #080d13;
    border: 0;
    border-radius: 4px;
    text-align: center;
    color: transparent;
}
QProgressBar::chunk {
    background: #66c0f4;
    border-radius: 4px;
}
QPlainTextEdit {
    background: #0a1018;
    border: 1px solid #1d2b3d;
    border-radius: 9px;
    color: #8ea2b8;
    padding: 8px 10px;
    selection-background-color: #234765;
}
QScrollBar:vertical {
    background: transparent;
    width: 8px;
    margin: 3px 1px;
}
QScrollBar::handle:vertical {
    background: #29384b;
    border-radius: 4px;
    min-height: 28px;
}
QScrollBar::handle:vertical:hover { background: #3a516d; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QSplitter::handle { background: #141d29; width: 1px; }
"""


class ModernHeroView(base.HeroView):
    """Existing hero contract with a softer cinematic fade when artwork changes."""

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(365)
        self._reveal = 0.0
        self._reveal_anim = QVariantAnimation(self)
        self._reveal_anim.setDuration(520)
        self._reveal_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._reveal_anim.valueChanged.connect(self._on_reveal)

    def _on_reveal(self, value):
        self._reveal = float(value)
        self.update()

    def set_art(self, hero: QPixmap | None, logo: QPixmap | None, title: str):
        super().set_art(hero, logo, title)
        self._reveal_anim.stop()
        self._reveal_anim.setStartValue(0.0)
        self._reveal_anim.setEndValue(1.0)
        self._reveal_anim.start()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect()

        # Extra cinematic vignette and a subtle top highlight make raw artwork
        # feel integrated with the shell instead of pasted into a widget.
        vignette = QLinearGradient(0, 0, rect.width(), 0)
        vignette.setColorAt(0.0, QColor(4, 8, 13, 180))
        vignette.setColorAt(0.42, QColor(4, 8, 13, 30))
        vignette.setColorAt(1.0, QColor(4, 8, 13, 75))
        painter.fillRect(rect, vignette)

        top_glow = QLinearGradient(0, 0, 0, max(1, rect.height() * 0.45))
        top_glow.setColorAt(0.0, QColor(102, 192, 244, 18))
        top_glow.setColorAt(1.0, QColor(102, 192, 244, 0))
        painter.fillRect(rect, top_glow)

        if self._reveal < 1.0:
            painter.fillRect(rect, QColor(7, 11, 17, int((1.0 - self._reveal) * 150)))
        painter.end()


class CoverLabel(QLabel):
    def __init__(self):
        super().__init__("COVER")
        self._cover = QPixmap()
        self.setAlignment(Qt.AlignCenter)
        self.setFixedSize(190, 285)

    def setPixmap(self, pixmap: QPixmap):
        self._cover = QPixmap(pixmap)
        self.setText("")
        self.update()

    def clear(self):
        self._cover = QPixmap()
        super().clear()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect().adjusted(1, 1, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(rect, 15, 15)
        painter.setClipPath(path)
        painter.fillRect(rect, QColor("#0a1018"))
        if not self._cover.isNull():
            scaled = self._cover.scaled(rect.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            sx = max((scaled.width() - rect.width()) // 2, 0)
            sy = max((scaled.height() - rect.height()) // 2, 0)
            source = QRect(sx, sy, min(rect.width(), scaled.width()), min(rect.height(), scaled.height()))
            painter.drawPixmap(rect, scaled, source)
        else:
            painter.setPen(QColor("#536276"))
            painter.drawText(rect, Qt.AlignCenter, self.text() or "COVER")
        painter.setClipping(False)
        painter.setPen(QColor("#26384d"))
        painter.drawRoundedRect(rect, 15, 15)
        painter.end()


def stat_card(name: str, value: str) -> tuple[QFrame, QLabel]:
    card = QFrame()
    card.setObjectName("statCard")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(12, 8, 12, 8)
    layout.setSpacing(1)
    label = QLabel(name.upper())
    label.setObjectName("statName")
    value_label = QLabel(value)
    value_label.setObjectName("statValue")
    layout.addWidget(label)
    layout.addWidget(value_label)
    return card, value_label


class Launcher(previous.Launcher):
    def __init__(self):
        self._detail_opacity = None
        self._detail_fade = None
        self._progress_anim = None
        self._pulse_on = False
        super().__init__()
        self.setWindowTitle(f"Drowned Launcher {APP_VERSION}")

        # app_v7/v8 create these after _build_ui. Restyle them once the legacy
        # functional layer has finished wiring all signals.
        self.uninstall_button.setObjectName("danger")
        self.uninstall_button.setStyleSheet("")
        self.uninstall_button.setMinimumWidth(104)
        self.uninstall_button.setText("KALDIR")
        self.uninstall_button.show()

        self.pause_button.setObjectName("secondary")
        self.pause_button.setStyleSheet("")
        self.cancel_button.setObjectName("danger")
        self.cancel_button.setStyleSheet("")

        self._progress_anim = QVariantAnimation(self)
        self._progress_anim.setDuration(210)
        self._progress_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._progress_anim.valueChanged.connect(lambda value: self.progress.setValue(int(value)))

        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(520)
        self._pulse_timer.timeout.connect(self._pulse_download)

        self._refresh_state_badge()

    def _build_ui(self):
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ---- top navigation -------------------------------------------------
        top = QFrame()
        top.setObjectName("topbar")
        top.setFixedHeight(72)
        top_layout = QHBoxLayout(top)
        top_layout.setContentsMargins(20, 0, 18, 0)
        top_layout.setSpacing(10)

        mark = QLabel("D")
        mark.setObjectName("brandMark")
        mark.setAlignment(Qt.AlignCenter)
        mark.setFixedSize(38, 38)
        brand = QLabel("DROWNED")
        brand.setObjectName("brand")
        library_nav = QLabel("KÜTÜPHANE")
        library_nav.setObjectName("navActive")
        downloads_nav = QLabel("İNDİRMELER")
        downloads_nav.setObjectName("nav")

        top_layout.addWidget(mark)
        top_layout.addWidget(brand)
        top_layout.addSpacing(30)
        top_layout.addWidget(library_nav)
        top_layout.addWidget(downloads_nav)
        top_layout.addStretch()

        self.connection = QLabel("RAW • bağlanıyor")
        self.connection.setObjectName("connectionOnline")
        refresh = QPushButton("↻")
        refresh.setObjectName("iconButton")
        refresh.setToolTip("Kataloğu yenile")
        refresh.clicked.connect(self.load_catalog)
        settings_button = QPushButton("⚙")
        settings_button.setObjectName("iconButton")
        settings_button.setToolTip("Ayarlar")
        settings_button.clicked.connect(self.open_settings)
        top_layout.addWidget(self.connection)
        top_layout.addSpacing(4)
        top_layout.addWidget(refresh)
        top_layout.addWidget(settings_button)
        outer.addWidget(top)

        # ---- library + hero -------------------------------------------------
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setMinimumWidth(280)
        sidebar.setMaximumWidth(365)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(16, 18, 14, 14)
        side.setSpacing(10)

        library_header = QHBoxLayout()
        section = QLabel("OYUN KÜTÜPHANESİ")
        section.setObjectName("section")
        self.game_count = QLabel("0 oyun")
        self.game_count.setObjectName("muted")
        library_header.addWidget(section)
        library_header.addStretch()
        library_header.addWidget(self.game_count)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Oyun ara…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.render_library)

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

        self.library = QListWidget()
        self.library.setSpacing(1)
        self.library.currentItemChanged.connect(self.library_selection_changed)

        side.addLayout(library_header)
        side.addWidget(self.search)
        side.addLayout(filters)
        side.addWidget(self.library, 1)

        detail = QFrame()
        detail.setObjectName("detail")
        detail_layout = QVBoxLayout(detail)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        detail_layout.setSpacing(0)

        self.hero = ModernHeroView()
        detail_layout.addWidget(self.hero)

        content_shell = QWidget()
        shell_layout = QVBoxLayout(content_shell)
        shell_layout.setContentsMargins(24, 0, 24, 22)
        shell_layout.setSpacing(0)

        self.info_card = QFrame()
        self.info_card.setObjectName("infoCard")
        info = QHBoxLayout(self.info_card)
        info.setContentsMargins(22, 20, 22, 20)
        info.setSpacing(22)

        self.cover = CoverLabel()
        info.addWidget(self.cover, 0, Qt.AlignTop)

        right = QVBoxLayout()
        right.setSpacing(8)
        eyebrow = QLabel("OYUN DETAYLARI")
        eyebrow.setObjectName("eyebrow")
        self.title = QLabel("Kütüphane yükleniyor…")
        self.title.setObjectName("gameTitle")
        self.meta = QLabel("")
        self.meta.setObjectName("metaLine")
        self.description = QLabel("Raw GitHub kataloğundan oyunlar yükleniyor.")
        self.description.setObjectName("description")
        self.description.setWordWrap(True)
        self.description.setAlignment(Qt.AlignTop)
        self.description.setMinimumHeight(54)

        right.addWidget(eyebrow)
        right.addWidget(self.title)
        right.addWidget(self.meta)
        right.addSpacing(3)
        right.addWidget(self.description, 1)

        stats = QHBoxLayout()
        stats.setSpacing(8)
        card, self.stat_platform = stat_card("Platform", "—")
        stats.addWidget(card)
        card, self.stat_channel = stat_card("Kanal", "—")
        stats.addWidget(card)
        card, self.stat_version = stat_card("Sürüm", "—")
        stats.addWidget(card)
        card, self.stat_size = stat_card("Boyut", "—")
        stats.addWidget(card)
        stats.addStretch()
        right.addLayout(stats)
        right.addSpacing(4)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.install_button = QPushButton("YÜKLE")
        self.install_button.setObjectName("install")
        self.install_button.clicked.connect(self.install_current_game)
        self.install_button.setEnabled(False)
        self.verify_button = QPushButton("DOSYALARI DOĞRULA")
        self.verify_button.setObjectName("secondary")
        self.verify_button.setEnabled(False)
        self.state_badge = QLabel("HAZIR")
        self.state_badge.setObjectName("connectionOnline")
        self.state_badge.setAlignment(Qt.AlignCenter)
        actions.addWidget(self.install_button)
        actions.addWidget(self.verify_button)
        actions.addWidget(self.state_badge)
        actions.addStretch()
        right.addLayout(actions)

        info.addLayout(right, 1)
        shell_layout.addWidget(self.info_card)
        detail_layout.addWidget(content_shell, 1)

        splitter.addWidget(sidebar)
        splitter.addWidget(detail)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([315, 1180])
        outer.addWidget(splitter, 1)

        # ---- persistent download dashboard ---------------------------------
        download = QFrame()
        download.setObjectName("downloadBar")
        download_outer = QVBoxLayout(download)
        download_outer.setContentsMargins(14, 10, 14, 12)
        download_outer.setSpacing(0)

        self.download_card = QFrame()
        self.download_card.setObjectName("downloadCard")
        dl = QVBoxLayout(self.download_card)
        dl.setContentsMargins(14, 9, 14, 10)
        dl.setSpacing(6)

        status_row = QHBoxLayout()
        status_row.setSpacing(8)
        self.download_dot = QLabel("●")
        self.download_dot.setObjectName("downloadDot")
        self.status = QLabel("Hazır")
        self.status.setObjectName("downloadTitle")
        self.progress_text = QLabel("")
        self.progress_text.setObjectName("progressText")
        status_row.addWidget(self.download_dot)
        status_row.addWidget(self.status)
        status_row.addStretch()
        status_row.addWidget(self.progress_text)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)

        self.logs = QPlainTextEdit()
        self.logs.setReadOnly(True)
        self.logs.setFixedHeight(64)
        self.logs.hide()

        dl.addLayout(status_row)
        dl.addWidget(self.progress)
        dl.addWidget(self.logs)
        download_outer.addWidget(self.download_card)
        outer.addWidget(download)

        # Detail fade target exists before the first catalog selection.
        self._detail_opacity = QGraphicsOpacityEffect(self.info_card)
        self._detail_opacity.setOpacity(1.0)
        self.info_card.setGraphicsEffect(self._detail_opacity)
        self._detail_fade = QPropertyAnimation(self._detail_opacity, b"opacity", self)
        self._detail_fade.setDuration(260)
        self._detail_fade.setEasingCurve(QEasingCurve.OutCubic)

    def library_selection_changed(self, current, previous_item):
        super().library_selection_changed(current, previous_item)
        self._sync_game_stats()
        self._animate_detail_card()
        self._refresh_state_badge()

    def _sync_game_stats(self):
        if not self.current_game:
            for label in (self.stat_platform, self.stat_channel, self.stat_version, self.stat_size):
                label.setText("—")
            return
        data = (self.current_game.get("channels") or {}).get(self.current_channel) or {}
        self.stat_platform.setText(str(self.current_game.get("platform") or "—").upper())
        self.stat_channel.setText(str(self.current_channel or "—").upper())
        self.stat_version.setText(str(data.get("version") or "—"))
        try:
            self.stat_size.setText(base.format_bytes(int(data.get("size") or 0)))
        except Exception:
            self.stat_size.setText("—")

    def _animate_detail_card(self):
        if not self._detail_fade or not self._detail_opacity:
            return
        self._detail_fade.stop()
        self._detail_opacity.setOpacity(0.35)
        self._detail_fade.setStartValue(0.35)
        self._detail_fade.setEndValue(1.0)
        self._detail_fade.start()

    def install_progress(self, percent: int, text: str):
        # Keep the exact downloader text/metrics, but animate visual progress so
        # high-frequency worker updates do not make the bar look jittery.
        target = max(0, min(int(percent), 100))
        if self._progress_anim is not None:
            self._progress_anim.stop()
            self._progress_anim.setStartValue(self.progress.value())
            self._progress_anim.setEndValue(target)
            self._progress_anim.start()
        else:
            self.progress.setValue(target)
        self.progress_text.setText(f"%{target}  •  {text}")

    def _set_download_controls(self, active: bool):
        super()._set_download_controls(active)
        if not hasattr(self, "download_dot"):
            return
        if active:
            self.download_dot.setText("●")
            self._pulse_on = False
            if hasattr(self, "_pulse_timer") and not self._pulse_timer.isActive():
                self._pulse_timer.start()
        else:
            if hasattr(self, "_pulse_timer"):
                self._pulse_timer.stop()
            self.download_dot.setStyleSheet("")
            self.download_dot.setText("●")

    def _pulse_download(self):
        self._pulse_on = not self._pulse_on
        alpha = "#66c0f4" if self._pulse_on else "#31546b"
        self.download_dot.setStyleSheet(f"color:{alpha};font-size:16px;")

    def toggle_pause(self):
        super().toggle_pause()
        self._refresh_state_badge()
        if self.download_control is not None and self.download_control.paused:
            self.download_dot.setStyleSheet("color:#f2bf63;font-size:16px;")
        elif self.download_control is not None:
            self.download_dot.setStyleSheet("")

    def update_install_state_ui(self):
        super().update_install_state_ui()
        if hasattr(self, "state_badge"):
            self._refresh_state_badge()

    def install_done(self):
        super().install_done()
        self._refresh_state_badge()

    def install_cancelled(self):
        super().install_cancelled()
        self._refresh_state_badge()

    def install_error(self, message: str):
        super().install_error(message)
        self._refresh_state_badge()

    def uninstall_done(self, removed_path: str):
        super().uninstall_done(removed_path)
        self._refresh_state_badge()

    def repair_done(self, result: dict):
        super().repair_done(result)
        self._refresh_state_badge()

    def _refresh_state_badge(self):
        if not hasattr(self, "state_badge"):
            return
        if self.download_control is not None:
            if self.download_control.paused:
                self.state_badge.setText("DURAKLATILDI")
                self.state_badge.setStyleSheet(
                    "color:#f7c873;background:#2b2111;border:1px solid #5a4320;"
                    "border-radius:12px;padding:5px 10px;font-size:11px;font-weight:800;"
                )
            else:
                self.state_badge.setText("İNDİRİLİYOR")
                self.state_badge.setStyleSheet("")
            return

        record = self._record() if self.current_game else None
        partial = self._valid_partial() if self.current_game else None
        if record and self._record_path_exists(record):
            data = (self.current_game.get("channels") or {}).get(self.current_channel) or {}
            if str(record.get("tag") or "") == str(data.get("tag") or ""):
                self.state_badge.setText("KURULU")
                self.state_badge.setStyleSheet("")
            else:
                self.state_badge.setText("GÜNCELLEME VAR")
                self.state_badge.setStyleSheet(
                    "color:#f7c873;background:#2b2111;border:1px solid #5a4320;"
                    "border-radius:12px;padding:5px 10px;font-size:11px;font-weight:800;"
                )
        elif partial:
            self.state_badge.setText("DEVAM EDİLEBİLİR")
            self.state_badge.setStyleSheet(
                "color:#a9d7ff;background:#132536;border:1px solid #244a68;"
                "border-radius:12px;padding:5px 10px;font-size:11px;font-weight:800;"
            )
        else:
            self.state_badge.setText("HAZIR")
            self.state_badge.setStyleSheet(
                "color:#9aa8b9;background:#171e28;border:1px solid #293442;"
                "border-radius:12px;padding:5px 10px;font-size:11px;font-weight:800;"
            )


def main():
    base.install_exception_hook()
    app = QApplication(sys.argv)
    app.setApplicationName("Drowned Launcher")
    app.setOrganizationName("Drowned")
    app.setStyle("Fusion")
    app.setStyleSheet(MODERN_STYLE)
    win = Launcher()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
