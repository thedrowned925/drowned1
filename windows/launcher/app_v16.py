from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSplashScreen,
    QVBoxLayout,
    QWidget,
)

import app_v15 as previous

APP_VERSION = "0.16.0"
BASE = previous.BASE


V16_STYLE = previous.VIRTUAL_STYLE + r"""
/* v16: responsive action deck + Steam-like downloads */
QFrame#heroActionBar {
    background:rgba(8,10,11,220);
    border:1px solid rgba(255,255,255,30);
    border-radius:16px;
}
QFrame#actionButtonsRow, QFrame#actionStatsRow { background:transparent; border:0; }
QPushButton#install {
    min-width:150px; min-height:36px; padding:8px 26px; border-radius:19px;
    background:#f7f7f3; color:#101212; border:1px solid #ffffff;
    font-size:11px; font-weight:950;
}
QPushButton#install:disabled {
    background:rgba(247,247,243,42); color:rgba(255,255,255,120);
    border:1px solid rgba(255,255,255,42);
}
QPushButton#secondary, QPushButton#danger {
    min-height:36px; padding:8px 18px; border-radius:19px;
}
QLabel#actionDivider { background:rgba(255,255,255,22); min-height:1px; max-height:1px; }

QFrame#downloadsRoot { background:#11171e; border:0; }
QFrame#downloadHero { background:#0c131a; border:0; }
QFrame#downloadMetrics { background:rgba(8,12,16,210); border:0; }
QLabel#downloadGameTitle { color:#ffffff; font-size:20px; font-weight:850; }
QLabel#downloadMetricName { color:#8c959f; font-size:9px; font-weight:850; letter-spacing:1px; }
QLabel#downloadMetricValue { color:#f5f7f8; font-size:12px; font-weight:850; }
QLabel#downloadRowLabel { color:#c8cdd2; font-size:11px; font-weight:800; }
QLabel#downloadRowValue { color:#dfe4e8; font-size:10px; font-weight:800; }
QLabel#downloadEta { color:#7f8992; font-size:10px; }
QFrame#downloadQueue { background:#343b46; border:0; }
QLabel#queueTitle { color:#f3f5f6; font-size:15px; font-weight:850; }
QLabel#queueMuted { color:#929aa3; font-size:10px; }
QFrame#downloadBottomBar {
    background:#151c24; border-top:1px solid #26313c;
}
QProgressBar#steamBar {
    min-height:4px; max-height:4px; background:#3e4854; border:0; border-radius:0;
}
QProgressBar#steamBar::chunk { background:#28a5ec; border-radius:0; }
QProgressBar#diskBar {
    min-height:4px; max-height:4px; background:#3e4854; border:0; border-radius:0;
}
QProgressBar#diskBar::chunk { background:#59c93d; border-radius:0; }
QPushButton#downloadPause {
    min-width:42px; max-width:42px; min-height:36px; max-height:36px;
    padding:0; border-radius:3px; background:#1497e6; border:0;
    color:#ffffff; font-size:17px; font-weight:900;
}
QPushButton#downloadPause:hover { background:#27a9f3; }
"""


class CompactHero(previous.VirtualHero):
    """Same artwork renderer, but it can shrink instead of crushing controls."""

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(420)
        self.setMaximumHeight(620)


class Launcher(previous.Launcher):
    """v15 behaviour with corrected responsive layout and downloads surface."""

    def __init__(self):
        super().__init__()
        QApplication.instance().setStyleSheet(V16_STYLE)
        self.setWindowTitle(f"Drowned Launcher {APP_VERSION} • Virtual Worlds UI")

    def _build_game_page(self):
        scroller = QScrollArea()
        scroller.setWidgetResizable(True)
        scroller.setFrameShape(QFrame.NoFrame)

        surface = QFrame()
        surface.setObjectName("detailSurface")
        self.game_surface = surface
        page = QVBoxLayout(surface)
        page.setContentsMargins(0, 0, 0, 24)
        page.setSpacing(0)

        self.hero = CompactHero()
        hero_l = QVBoxLayout(self.hero)
        hero_l.setContentsMargins(30, 22, 30, 24)
        hero_l.setSpacing(9)

        top = QHBoxLayout()
        top.addStretch()
        pill = QFrame()
        pill.setObjectName("topPill")
        pl = QHBoxLayout(pill)
        pl.setContentsMargins(12, 4, 12, 4)
        pl.setSpacing(8)
        dot = QLabel("●")
        dot.setObjectName("accentDot")
        txt = QLabel("DROWNED  •  LIBRARY")
        txt.setObjectName("topPillText")
        pl.addWidget(dot)
        pl.addWidget(txt)
        top.addWidget(pill)
        top.addStretch()
        hero_l.addLayout(top)
        hero_l.addStretch()

        self.title = QLabel("Kütüphane yükleniyor…")
        self.title.setObjectName("gameTitle")
        self.title.hide()
        self.meta = QLabel("")
        self.meta.setObjectName("metaLine")
        self.meta.setMaximumWidth(560)
        self.description = QLabel("Raw GitHub kataloğundan oyunlar yükleniyor.")
        self.description.setObjectName("description")
        self.description.setWordWrap(True)
        self.description.setMaximumWidth(560)
        hero_l.addWidget(self.meta, 0, Qt.AlignLeft)
        hero_l.addWidget(self.description, 0, Qt.AlignLeft)

        # Two rows instead of one overloaded horizontal strip.
        action_bar = QFrame(self.hero)
        action_bar.setObjectName("heroActionBar")
        deck = QVBoxLayout(action_bar)
        deck.setContentsMargins(13, 11, 13, 11)
        deck.setSpacing(9)

        button_row = QFrame(action_bar)
        button_row.setObjectName("actionButtonsRow")
        buttons = QHBoxLayout(button_row)
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.setSpacing(8)

        self.info_card = QFrame(button_row)
        self.info_card.setObjectName("infoCard")
        info = QHBoxLayout(self.info_card)
        info.setContentsMargins(0, 0, 0, 0)
        info.setSpacing(8)
        self.install_button = previous.previous.GlowButton("YÜKLE")
        self.install_button.setObjectName("install")
        self.install_button.clicked.connect(self.install_current_game)
        self.install_button.setEnabled(False)
        self.verify_button = QPushButton("DOSYALARI DOĞRULA")
        self.verify_button.setObjectName("secondary")
        self.verify_button.setEnabled(False)
        info.addWidget(self.install_button)
        info.addWidget(self.verify_button)
        buttons.addWidget(self.info_card, 0)

        self.action_dl = QWidget(button_row)
        dl_l = QHBoxLayout(self.action_dl)
        dl_l.setContentsMargins(0, 0, 0, 0)
        dl_l.setSpacing(9)
        self.action_pause = QPushButton("DURAKLAT")
        self.action_pause.setObjectName("pauseButton")
        self.action_pause.clicked.connect(self.toggle_pause)
        dl_l.addWidget(self.action_pause)
        dl_text = QVBoxLayout()
        dl_text.setSpacing(1)
        self.action_dl_caption = QLabel("İNDİRİLİYOR")
        self.action_dl_caption.setObjectName("statName")
        self.action_dl_value = QLabel("%0 Tamamlandı")
        self.action_dl_value.setObjectName("rowValue")
        self.action_dl_bar = QProgressBar()
        self.action_dl_bar.setRange(0, 100)
        self.action_dl_bar.setValue(0)
        self.action_dl_bar.setTextVisible(False)
        self.action_dl_bar.setFixedWidth(150)
        dl_text.addWidget(self.action_dl_caption)
        dl_text.addWidget(self.action_dl_value)
        dl_text.addWidget(self.action_dl_bar)
        dl_l.addLayout(dl_text)
        self.action_dl.hide()
        buttons.addWidget(self.action_dl, 0)
        buttons.addStretch(1)
        self.state_badge = QLabel("HAZIR")
        self.state_badge.setObjectName("statePill")
        buttons.addWidget(self.state_badge, 0, Qt.AlignVCenter)
        deck.addWidget(button_row)

        divider = QLabel("")
        divider.setObjectName("actionDivider")
        deck.addWidget(divider)

        stats_row = QFrame(action_bar)
        stats_row.setObjectName("actionStatsRow")
        stats = QHBoxLayout(stats_row)
        stats.setContentsMargins(2, 0, 2, 0)
        stats.setSpacing(28)
        for caption, attr in (
            ("PLATFORM", "stat_platform"),
            ("KANAL", "stat_channel"),
            ("SÜRÜM", "stat_version"),
            ("BOYUT", "stat_size"),
        ):
            box = QWidget(stats_row)
            b = QVBoxLayout(box)
            b.setContentsMargins(0, 0, 0, 0)
            b.setSpacing(1)
            c = QLabel(caption)
            c.setObjectName("statName")
            v = QLabel("—")
            v.setObjectName("statValue")
            b.addWidget(c)
            b.addWidget(v)
            setattr(self, attr, v)
            stats.addWidget(box)
        stats.addStretch(1)
        deck.addWidget(stats_row)
        hero_l.addWidget(action_bar)
        page.addWidget(self.hero)

        content = QFrame()
        content.setObjectName("detailSurface")
        self.game_content = content
        c = QVBoxLayout(content)
        c.setContentsMargins(28, 20, 28, 6)
        c.setSpacing(0)

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
        line = QFrame()
        line.setObjectName("hairline")
        line.setFixedHeight(1)
        c.addWidget(line)
        c.addSpacing(14)

        columns = QHBoxLayout()
        columns.setSpacing(14)
        self.detail_stack = previous.previous.FadeStack()
        overview = QFrame()
        overview.setObjectName("glassCard")
        ov = QVBoxLayout(overview)
        ov.setContentsMargins(16, 14, 16, 16)
        cap = QLabel("OYUN HAKKINDA")
        cap.setObjectName("panelTitle")
        self._detail_description = QLabel("Seçili oyunun ayrıntıları yukarıdaki hero alanında gösterilir.")
        self._detail_description.setObjectName("muted")
        self._detail_description.setWordWrap(True)
        ov.addWidget(cap)
        ov.addSpacing(7)
        ov.addWidget(self._detail_description)
        ov.addStretch()
        self.detail_stack.addWidget(overview)

        shots = QFrame()
        shots.setObjectName("glassCard")
        sh = QVBoxLayout(shots)
        sh.setContentsMargins(12, 12, 12, 12)
        self.screenshot_gallery = BASE.ScreenshotGallery()
        sh.addWidget(self.screenshot_gallery)
        self.detail_stack.addWidget(shots)
        columns.addWidget(self.detail_stack, 1)
        columns.addWidget(previous.previous.Launcher._build_side_panels(self), 0)
        c.addLayout(columns, 1)
        page.addWidget(content)

        self.cover = BASE.previous.CoverLabel()
        self.cover.setParent(surface)
        self.cover.hide()
        scroller.setWidget(surface)
        return scroller

    def _metric(self, parent_layout: QHBoxLayout, title: str):
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(1)
        name = QLabel(title)
        name.setObjectName("downloadMetricName")
        value = QLabel("0 b/sn")
        value.setObjectName("downloadMetricValue")
        lay.addWidget(name)
        lay.addWidget(value)
        parent_layout.addWidget(box)
        return value

    def _build_downloads_page(self):
        root = QFrame()
        root.setObjectName("downloadsRoot")
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Top half mirrors Steam Downloads: artwork left, live transfer data right.
        hero = CompactHero()
        hero.setObjectName("downloadHero")
        hero.setMinimumHeight(200)
        hero.setMaximumHeight(230)
        self.dlp_hero = hero
        hero_l = QHBoxLayout(hero)
        hero_l.setContentsMargins(28, 18, 26, 14)
        hero_l.setSpacing(24)
        hero_l.addStretch(3)

        metrics_panel = QFrame(hero)
        metrics_panel.setObjectName("downloadMetrics")
        metrics_panel.setMinimumWidth(520)
        mp = QVBoxLayout(metrics_panel)
        mp.setContentsMargins(0, 0, 0, 0)
        mp.setSpacing(9)

        metric_row = QHBoxLayout()
        metric_row.setSpacing(34)
        self.dlp_net = self._metric(metric_row, "AĞ")
        self.dlp_peak = self._metric(metric_row, "EN YÜKSEK")
        self.dlp_streams = self._metric(metric_row, "DİSK KULLANIMI")
        metric_row.addStretch()
        mp.addLayout(metric_row)

        self.dlp_title = QLabel("Etkin indirme yok")
        self.dlp_title.setObjectName("downloadGameTitle")
        self.dlp_title.hide()
        self.dlp_detail = QLabel("Kütüphaneden bir oyun seçip YÜKLE ile indirmeyi başlat.")
        self.dlp_detail.setObjectName("downloadEta")
        self.dlp_detail.hide()

        row1 = QHBoxLayout()
        r1 = QLabel("Veriler İndiriliyor")
        r1.setObjectName("downloadRowLabel")
        self.dlp_bytes = QLabel("—")
        self.dlp_bytes.setObjectName("downloadRowValue")
        row1.addWidget(r1)
        row1.addStretch()
        row1.addWidget(self.dlp_bytes)
        mp.addLayout(row1)
        self.dlp_bar = QProgressBar()
        self.dlp_bar.setObjectName("steamBar")
        self.dlp_bar.setRange(0, 100)
        self.dlp_bar.setValue(0)
        self.dlp_bar.setTextVisible(False)
        mp.addWidget(self.dlp_bar)

        row2 = QHBoxLayout()
        r2 = QLabel("Dosyalar Yükleniyor")
        r2.setObjectName("downloadRowLabel")
        self.dlp_percent = QLabel("%0")
        self.dlp_percent.setObjectName("downloadRowValue")
        row2.addWidget(r2)
        row2.addStretch()
        row2.addWidget(self.dlp_percent)
        mp.addLayout(row2)
        self.dlp_disk_bar = QProgressBar()
        self.dlp_disk_bar.setObjectName("diskBar")
        self.dlp_disk_bar.setRange(0, 100)
        self.dlp_disk_bar.setValue(0)
        self.dlp_disk_bar.setTextVisible(False)
        mp.addWidget(self.dlp_disk_bar)

        bottom = QHBoxLayout()
        self.dlp_eta = QLabel("Kalan tahmini süre: —")
        self.dlp_eta.setObjectName("downloadEta")
        self.dlp_limit = QLabel("GitHub Releases • Direct download")
        self.dlp_limit.setObjectName("downloadEta")
        self.dlp_pause = QPushButton("▶")
        self.dlp_pause.setObjectName("downloadPause")
        self.dlp_pause.clicked.connect(self.toggle_pause)
        self.dlp_pause.hide()
        bottom.addWidget(self.dlp_eta)
        bottom.addStretch()
        bottom.addWidget(self.dlp_limit)
        bottom.addSpacing(10)
        bottom.addWidget(self.dlp_pause)
        mp.addLayout(bottom)
        hero_l.addWidget(metrics_panel, 4)
        outer.addWidget(hero)

        # Queue block.
        queue = QFrame()
        queue.setObjectName("downloadQueue")
        ql = QVBoxLayout(queue)
        ql.setContentsMargins(28, 18, 28, 18)
        ql.setSpacing(12)
        qh = QHBoxLayout()
        self.dlp_queue_caption = QLabel("Sıradaki (0)")
        self.dlp_queue_caption.setObjectName("queueTitle")
        line = QFrame()
        line.setObjectName("hairline")
        line.setFixedHeight(1)
        note = QLabel("Otomatik güncellemeler etkin")
        note.setObjectName("queueMuted")
        qh.addWidget(self.dlp_queue_caption)
        qh.addSpacing(12)
        qh.addWidget(line, 1)
        qh.addWidget(note)
        ql.addLayout(qh)
        self.dlp_queue_body = QLabel("Kuyrukta indirme yok")
        self.dlp_queue_body.setObjectName("queueMuted")
        ql.addWidget(self.dlp_queue_body)

        self.dlp_done_caption = QLabel("TAMAMLANDI (0)")
        self.dlp_done_caption.setObjectName("queueTitle")
        self.dlp_done_caption.hide()
        self.dlp_done_empty = QLabel("Henüz tamamlanmış kurulum yok.")
        self.dlp_done_empty.setObjectName("queueMuted")
        self.dlp_done_empty.hide()
        self.dlp_rows_layout = QVBoxLayout()
        self.dlp_rows_layout.setSpacing(7)
        ql.addStretch(1)
        ql.addWidget(self.dlp_done_caption)
        ql.addWidget(self.dlp_done_empty)
        ql.addLayout(self.dlp_rows_layout)
        outer.addWidget(queue, 1)

        self._completed_rows = []
        return root

    def install_progress(self, percent: int, text: str):
        super().install_progress(percent, text)
        if hasattr(self, "dlp_disk_bar"):
            self.dlp_disk_bar.setValue(max(0, min(int(percent), 100)))

    def toggle_pause(self):
        super().toggle_pause()
        if hasattr(self, "dlp_pause"):
            paused = self.download_control is not None and self.download_control.paused
            self.dlp_pause.setText("▶" if paused else "Ⅱ")


def main():
    BASE.base.install_exception_hook()
    app = QApplication(sys.argv)
    app.setApplicationName("Drowned Launcher")
    app.setOrganizationName("Drowned")
    app.setStyle("Fusion")
    app.setStyleSheet(V16_STYLE)
    splash = QSplashScreen(BASE._splash_pixmap())
    splash.show()
    app.processEvents()
    win = Launcher()
    win.show()
    splash.finish(win)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
