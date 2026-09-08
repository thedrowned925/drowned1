"""Isolated Steam-inspired launcher entry point.

Inherits the same v12 functional layer as v18, without its v13-v18 visual
wrappers. No builder, registry schema, repository default or downloader changes.
Run: python windows/launcher/app_steam.py
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess
import sys

from PySide6.QtCore import QEvent, QSettings, QTimer, Qt
from PySide6.QtGui import QColor, QKeySequence, QPalette, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication, QBoxLayout, QCheckBox, QComboBox, QFileDialog, QFrame, QGridLayout,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QMenu, QMessageBox,
    QPlainTextEdit, QProgressBar, QScrollArea, QSizePolicy, QSplitter,
    QStackedWidget, QVBoxLayout, QWidget,
)

import app_v12 as functional
import app_v10 as BASE
from steam_desktop_widgets import STYLE, ControllerGrid, DesktopList, FadeStack, LibraryCard, MotionButton, SteamHero, TransferGraph

APP_VERSION = '0.19.1-preview'


def apply_palette(app):
    palette = app.palette()
    for role, color in ((QPalette.Window, '#1b2330'), (QPalette.Base, '#202630'),
                        (QPalette.AlternateBase, '#253244'), (QPalette.Text, '#dce3ed'),
                        (QPalette.WindowText, '#dce3ed'), (QPalette.Button, '#303c4d'),
                        (QPalette.ButtonText, '#dce3ed'), (QPalette.Highlight, '#386b91')):
        palette.setColor(role, QColor(color))
    app.setPalette(palette)


def containing_layout(layout, widget):
    if layout is None:
        return None
    for index in range(layout.count()):
        item = layout.itemAt(index)
        if item.widget() is widget:
            return layout
        if item.layout():
            found = containing_layout(item.layout(), widget)
            if found:
                return found
    return None


def label(text, name='muted'):
    widget = QLabel(text)
    widget.setObjectName(name)
    widget.setTextFormat(Qt.PlainText)
    return widget


def button(text, callback=None, name='quiet'):
    widget = MotionButton(text)
    widget.setObjectName(name)
    if callback:
        widget.clicked.connect(callback)
    return widget


class Launcher(functional.Launcher):
    def __init__(self):
        self._cards = {}
        self._home_rows = []
        self._home_columns = 0
        self._view_ready = False
        self._home_installed_only = False
        self._cover_pending = set()
        self._card_progress = {}
        # New presentation preferences are deliberately outside the legacy keys.
        self.desktop_preferences = QSettings('Drowned', 'LauncherSteamDesktop')
        super().__init__()
        self.setWindowTitle(f'Drowned • Launcher {APP_VERSION}')
        QApplication.instance().setStyleSheet(STYLE)
        apply_palette(QApplication.instance())
        self.setMinimumSize(1080, 700)
        screen = self.screen().availableGeometry()
        self.resize(min(1440, screen.width()), min(900, screen.height()))
        self._view_ready = True
        self._finish_details()
        self._apply_motion(self.desktop_preferences.value('reduce_motion', False, type=bool))
        self._search_shortcut = QShortcut(QKeySequence('Ctrl+F'), self)
        self._search_shortcut.activated.connect(self.search.setFocus)
        self._refresh_shortcut = QShortcut(QKeySequence('F5'), self)
        self._refresh_shortcut.activated.connect(self.load_catalog)
        self._downloads_shortcut = QShortcut(QKeySequence('Ctrl+J'), self)
        self._downloads_shortcut.activated.connect(lambda: self._show_right_page(1))
        self._home_shortcut = QShortcut(QKeySequence('Alt+Home'), self)
        self._home_shortcut.activated.connect(self.show_home)
        self.library_grid.gameActivated.connect(self._open_desktop_game)
        self.show_home()

    def _build_ui(self):
        root = QWidget()
        root.setObjectName('steamRoot')
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self._chrome_widgets = []
        header = QFrame()
        header.setObjectName('steamHeader')
        top = QVBoxLayout(header)
        top.setContentsMargins(22, 12, 22, 0)
        top.setSpacing(4)
        brand = QHBoxLayout()
        mark = label('D', 'brandMark')
        mark.setAlignment(Qt.AlignCenter)
        mark.setFixedSize(34, 34)
        brand.addWidget(mark)
        brand.addSpacing(7)
        brand.addWidget(label('DROWNED', 'brand'))
        brand.addStretch()
        self.connection = label('Bağlanıyor…', 'connectionOnline')
        brand.addWidget(self.connection)
        brand.addSpacing(12)
        brand.addWidget(button('Ayarlar', self.open_settings))
        self.big_picture_button = button('Geniş ekran', name='quiet')
        self.big_picture_button.setToolTip('Kol ile gezinme / Big Picture (F11)')
        brand.addWidget(self.big_picture_button)
        top.addLayout(brand)
        navigation = QHBoxLayout()
        navigation.setSpacing(6)
        self.nav_library = button('KÜTÜPHANE', self.show_home, 'navActive')
        self.nav_downloads = button('İNDİRMELER', lambda: self._show_right_page(1), 'nav')
        navigation.addWidget(self.nav_library)
        navigation.addWidget(self.nav_downloads)
        navigation.addStretch()
        self.motion_toggle = QCheckBox('Hareketi azalt')
        self.motion_toggle.setToolTip('Arayüz hareketlerini ve görsel geçişleri azaltır')
        self.motion_toggle.toggled.connect(self._motion_changed)
        navigation.addWidget(self.motion_toggle)
        navigation.addSpacing(12)
        navigation.addWidget(button('Yenile', self.load_catalog))
        top.addLayout(navigation)
        outer.addWidget(header)
        self._chrome_widgets.append(header)

        # A plain outer stack avoids nested opacity effects in Big Picture.
        self.main_stack = QStackedWidget()
        self.main_stack.addWidget(self._build_desktop_shell())
        self.library_grid_bp = ControllerGrid()
        self.big_picture = BASE.BigPictureView(self.library_grid_bp)
        self.big_picture.setStyleSheet(BASE.STEAM_STYLE)
        self.main_stack.addWidget(self.big_picture)
        outer.addWidget(self.main_stack, 1)

        footer = QFrame()
        footer.setObjectName('statusRail')
        foot = QVBoxLayout(footer)
        foot.setContentsMargins(18, 8, 18, 8)
        foot.setSpacing(5)
        self.download_card = QFrame()
        download_layout = QVBoxLayout(self.download_card)
        download_layout.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        self.download_dot = label('●', 'connectionOnline')
        self.status_icon = BASE.IconLabel(24, 24)
        self.status_icon.hide()
        self.status = label('Hazır')
        self.status.setMinimumWidth(80)
        self.status.setMaximumWidth(430)
        self.status.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setMinimumWidth(100)
        self.progress_text = label('')
        row.addWidget(button('↓ İndirmeler', lambda: self._show_right_page(1)))
        row.addWidget(self.download_dot)
        row.addWidget(self.status_icon)
        row.addWidget(self.status, 2)
        row.addWidget(self.progress, 1)
        row.addWidget(self.progress_text)
        self._status_row = row
        download_layout.addLayout(row)
        self.logs = QPlainTextEdit()
        self.logs.setReadOnly(True)
        self.logs.setMaximumBlockCount(2000)
        self.logs.setFixedHeight(95)
        self.logs.hide()
        download_layout.addWidget(self.logs)
        foot.addWidget(self.download_card)
        row.addWidget(button('Günlük', lambda: self.logs.setVisible(not self.logs.isVisible())))
        outer.addWidget(footer)
        self._chrome_widgets.append(footer)
        self._wire_runtime()
        # The new transition owns the page effect. Retain the legacy animation
        # object but disable its nested opacity effect to avoid Qt paint conflicts.
        self._detail_fade.stop()
        self.info_card.setGraphicsEffect(None)
        self._detail_opacity = None
        self._detail_fade = None

    def _build_desktop_shell(self):
        shell = QSplitter(Qt.Horizontal)
        shell.setChildrenCollapsible(False)
        self.main_splitter = shell
        shell.addWidget(self._build_sidebar())
        self.right_stack = FadeStack()
        self.right_stack.addWidget(self._build_game_page())
        self.right_stack.addWidget(self._build_downloads_page())
        self.right_stack.addWidget(self._build_home())
        shell.addWidget(self.right_stack)
        shell.setStretchFactor(0, 0)
        shell.setStretchFactor(1, 1)
        shell.setSizes([265, 1175])
        return shell

    def _build_sidebar(self):
        sidebar = QFrame()
        sidebar.setObjectName('steamSidebar')
        sidebar.setMinimumWidth(225)
        sidebar.setMaximumWidth(370)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(12, 16, 10, 12)
        layout.setSpacing(10)
        layout.addWidget(button('⌂  Kütüphane ana sayfası', self.show_home, 'tabActive'))
        self.search = QLineEdit()
        self.search.setPlaceholderText('Oyun ara…  Ctrl+F')
        self.search.setClearButtonEnabled(True)
        self.search.setAccessibleName('Kütüphanede oyun ara')
        self._search_debounce = QTimer(self)
        self._search_debounce.setSingleShot(True)
        self._search_debounce.setInterval(150)
        self._search_debounce.timeout.connect(self.render_library)
        self.search.textChanged.connect(lambda _: self._search_debounce.start())
        layout.addWidget(self.search)
        filters = QHBoxLayout()
        self.platform = QComboBox()
        self.platform.addItem('Tümü')
        self.platform.setAccessibleName('Platform filtresi')
        self.channel = QComboBox()
        self.channel.addItems(['stable', 'beta', 'dev', 'nightly', 'archive'])
        self.channel.setAccessibleName('Yayın kanalı')
        self.platform.currentTextChanged.connect(self.render_library)
        self.channel.currentTextChanged.connect(self.render_library)
        filters.addWidget(self.platform, 1)
        filters.addWidget(self.channel, 1)
        layout.addLayout(filters)
        heading = QHBoxLayout()
        heading.addWidget(label('TÜM OYUNLAR', 'sectionLabel'))
        heading.addStretch()
        self.game_count = label('0 oyun')
        heading.addWidget(self.game_count)
        layout.addLayout(heading)
        self.library = QListWidget()
        self.library.currentItemChanged.connect(self.library_selection_changed)
        self.library.hide()
        layout.addWidget(self.library)
        self.library_grid = DesktopList()
        layout.addWidget(self.library_grid, 1)
        layout.addWidget(label('F11  Geniş ekran    •    F5  Yenile', 'eyebrow'))
        return sidebar

    def _build_game_page(self):
        # Recompose the proven detail controls; every existing backend attribute
        # and button remains the original object with its original connection.
        page = BASE.Launcher._build_game_page(self)
        page.setObjectName('steamBody')
        layout = page.layout()
        old = self.hero
        layout.removeWidget(old)
        old.hide()
        old.deleteLater()
        self.hero = SteamHero()
        layout.insertWidget(0, self.hero)
        action_bar = self.info_card.parentWidget()
        action_layout = action_bar.layout()
        # Two lines keep action buttons readable at 1080px window width.
        stats = QWidget()
        stats_layout = QHBoxLayout(stats)
        stats_layout.setContentsMargins(30, 8, 30, 10)
        stats_layout.setSpacing(28)
        while action_layout.count() > 2:
            item = action_layout.takeAt(2)
            if item.layout():
                stats_layout.addLayout(item.layout())
            elif item.widget():
                widget = item.widget()
                if widget is self.state_badge:
                    stats_layout.addWidget(widget)
                else:
                    widget.deleteLater()
        stats_layout.addStretch()
        layout.insertWidget(2, stats)
        action_layout.setContentsMargins(28, 12, 28, 12)
        action_layout.addStretch()
        self.play_button = button('▶  OYNA', self.play_current_game, 'play')
        self.play_button.hide()
        self.info_card.layout().insertWidget(0, self.play_button)
        self.game_menu_button = button('•••', self._open_game_menu)
        self.game_menu_button.setToolTip('Oyun seçenekleri')
        action_layout.addWidget(self.game_menu_button)
        # Native QPushButtons improve keyboard focus over the original labels.
        for attr, text, index in [('tab_overview', 'GENEL BAKIŞ', 0), ('tab_shots', 'EKRAN GÖRÜNTÜLERİ', 1)]:
            old = getattr(self, attr)
            replacement = button(text, lambda checked=False, i=index: self._show_detail_tab(i), 'tabActive' if index == 0 else 'tab')
            old.parentWidget().layout().replaceWidget(old, replacement, Qt.FindChildrenRecursively)
            old.deleteLater()
            setattr(self, attr, replacement)
        self.description.setMinimumWidth(120)
        self.meta.setWordWrap(True)
        self.title.setWordWrap(True)
        self.title.setTextFormat(Qt.PlainText)
        self.description.setTextFormat(Qt.PlainText)
        scroller = QScrollArea()
        scroller.setWidgetResizable(True)
        scroller.setWidget(page)
        self.detail_columns = containing_layout(self.detail_stack.parentWidget().layout(), self.detail_stack)
        self.detail_viewport = scroller.viewport()
        self.detail_viewport.installEventFilter(self)
        return scroller

    def _finish_details(self):
        # Functional constructors insert these after _build_ui.
        for native in (self.install_button, self.verify_button, self.uninstall_button):
            native.setCursor(Qt.PointingHandCursor)
            native.clicked.connect(lambda: QTimer.singleShot(0, self._sync_desktop_state))
        self.verify_button.setText('DOĞRULA')
        self.uninstall_button.setMinimumWidth(65)
        self.install_button.setMinimumWidth(95)
        # Constructors in v7/v8 insert maintenance buttons after _build_ui.
        # Give them their own row: Windows font metrics make a single row of
        # PLAY / INSTALL / VERIFY / UNINSTALL wider than the detail viewport.
        action_bar = self.info_card.parentWidget()
        page_layout = action_bar.parentWidget().layout()
        maintenance = QWidget()
        maintenance_layout = QHBoxLayout(maintenance)
        maintenance_layout.setContentsMargins(28, 6, 28, 10)
        for native in (self.verify_button, self.uninstall_button):
            self.info_card.layout().removeWidget(native)
            maintenance_layout.addWidget(native)
        maintenance_layout.addStretch()
        page_layout.insertWidget(page_layout.indexOf(action_bar) + 1, maintenance)
        # Transfer controls must also fit while an installed game is updating.
        action_bar.layout().removeWidget(self.action_dl)
        self.action_dl.layout().setContentsMargins(28, 8, 28, 10)
        self.action_dl.layout().addStretch()
        page_layout.insertWidget(page_layout.indexOf(maintenance) + 1, self.action_dl)
        self.addon_panel.setMaximumWidth(16777215)
        # Keep the original package controls, presented as an actual detail tab.
        self.addon_panel.parentWidget().layout().removeWidget(self.addon_panel)
        self.detail_stack.addWidget(self.addon_panel)
        self.tab_addons = button('EK İÇERİKLER', lambda: self._show_detail_tab(2), 'tab')
        tabs = containing_layout(self.tab_overview.parentWidget().layout(), self.tab_overview)
        tabs.insertWidget(2, self.tab_addons)
        self._sync_desktop_state()

    def _build_side_panels(self):
        panels = BASE.Launcher._build_side_panels(self)
        self.detail_side_panels = panels
        panels.setFixedWidth(248)
        # Paths can be long; wrap them without imposing a window-wide minimum.
        self.panel_path.setWordWrap(True)
        self.panel_path.setMinimumWidth(0)
        self.panel_path.setTextInteractionFlags(Qt.TextSelectableByMouse)
        return panels

    def _layout_details(self):
        compact = self.detail_viewport.width() < 880
        self.detail_columns.setDirection(QBoxLayout.TopToBottom if compact else QBoxLayout.LeftToRight)
        self.detail_side_panels.setMinimumWidth(0 if compact else 248)
        self.detail_side_panels.setMaximumWidth(16777215 if compact else 248)

    def _build_downloads_page(self):
        page = QFrame()
        page.setObjectName('steamBody')
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 22, 28, 22)
        layout.setSpacing(18)
        layout.addWidget(label('AKTARIM MERKEZİ', 'eyebrow'))
        layout.addWidget(label('İndirmeler', 'heading'))
        metrics = QHBoxLayout()
        metrics.setSpacing(40)
        self.dlp_net = self._metric_column(metrics, 'ANLIK HIZ')
        self.dlp_peak = self._metric_column(metrics, 'EN YÜKSEK HIZ')
        self.dlp_streams = self._metric_column(metrics, 'PARALEL AKIŞ')
        metrics.addStretch()
        self.dlp_limit = label('İndirmeler sırasında bütünlük kontrol edilir.')
        metrics.addWidget(self.dlp_limit)
        layout.addLayout(metrics)
        self.transfer_graph = TransferGraph()
        layout.addWidget(self.transfer_graph)
        active = QFrame()
        active.setObjectName('panel')
        active_layout = QHBoxLayout(active)
        active_layout.setContentsMargins(18, 18, 18, 18)
        active_layout.setSpacing(20)
        self.dlp_hero = BASE.DownloadHeroPanel()
        self.dlp_hero.setFixedSize(180, 130)
        active_layout.addWidget(self.dlp_hero)
        transfer = QVBoxLayout()
        transfer.setSpacing(10)
        self.dlp_title = label('Etkin indirme yok', 'rowValue')
        self.dlp_title.setWordWrap(True)
        self.dlp_detail = label('Başlamak için kütüphanenden bir oyun seç.')
        self.dlp_detail.setWordWrap(True)
        transfer.addWidget(self.dlp_title)
        transfer.addWidget(self.dlp_detail)
        self.dlp_bar = QProgressBar()
        self.dlp_bar.setRange(0, 100)
        self.dlp_bar.setValue(0)
        self.dlp_bar.setTextVisible(False)
        self.dlp_bar.setObjectName('fatBar')
        transfer.addWidget(self.dlp_bar)
        numbers = QHBoxLayout()
        self.dlp_bytes = label('—')
        self.dlp_percent = label('%0')
        numbers.addWidget(self.dlp_bytes)
        numbers.addStretch()
        numbers.addWidget(self.dlp_percent)
        transfer.addLayout(numbers)
        bottom = QHBoxLayout()
        self.dlp_eta = label('Kalan tahmini süre: —')
        self.dlp_pause = button('DURAKLAT', self.toggle_pause, 'pauseButton')
        self.dlp_pause.hide()
        bottom.addWidget(self.dlp_eta)
        bottom.addStretch()
        bottom.addWidget(self.dlp_pause)
        transfer.addLayout(bottom)
        active_layout.addLayout(transfer, 1)
        layout.addWidget(active)
        self.dlp_queue_caption = label('SIRADAKİ (0)', 'panelTitle')
        self.dlp_queue_body = label('Tek seferde bir indirme çalışır.')
        layout.addWidget(self.dlp_queue_caption)
        layout.addWidget(self.dlp_queue_body)
        self.dlp_done_caption = label('TAMAMLANDI (0)', 'panelTitle')
        layout.addWidget(self.dlp_done_caption)
        self.dlp_done_empty = label('Henüz tamamlanmış kurulum yok.')
        layout.addWidget(self.dlp_done_empty)
        completed = QWidget()
        completed.setObjectName('completedContent')
        self.dlp_rows_layout = QVBoxLayout(completed)
        self.dlp_rows_layout.setContentsMargins(0, 0, 0, 0)
        self.dlp_rows_layout.setSpacing(8)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(completed)
        layout.addWidget(scroll, 1)
        self._completed_rows = []
        return page

    def _build_home(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        surface = QFrame()
        surface.setObjectName('steamBody')
        body = QVBoxLayout(surface)
        body.setContentsMargins(26, 20, 26, 24)
        body.setSpacing(16)
        heading = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(4)
        titles.addWidget(label('SANA AİT BİR OYUN ALANI', 'eyebrow'))
        titles.addWidget(label('Kütüphanene hoş geldin', 'heading'))
        heading.addLayout(titles)
        heading.addStretch()
        self.home_count = label('Katalog yükleniyor…')
        heading.addWidget(self.home_count)
        body.addLayout(heading)
        self.home_hero = SteamHero()
        self.home_hero.setMinimumHeight(260)
        self.home_hero.setMaximumHeight(290)
        body.addWidget(self.home_hero)
        featured = QHBoxLayout()
        self.home_meta = label('Oyunlarını tek bir yerde keşfet ve yönet.')
        featured.addWidget(self.home_meta, 1)
        self.home_action = button('OYUNU İNCELE  →', self.show_current_game, 'tabActive')
        self.home_action.setEnabled(False)
        featured.addWidget(self.home_action)
        body.addLayout(featured)
        shelf_heading = QHBoxLayout()
        self.shelf_title = label('Tüm oyunlar', 'heading')
        shelf_heading.addWidget(self.shelf_title)
        shelf_heading.addStretch()
        self.all_filter = button('Tümü', lambda: self._set_home_filter(False), 'tabActive')
        self.installed_filter = button('Kurulu', lambda: self._set_home_filter(True), 'tab')
        shelf_heading.addWidget(self.all_filter)
        shelf_heading.addWidget(self.installed_filter)
        self.home_sort = QComboBox()
        self.home_sort.addItems(['Ada göre A–Z', 'Ada göre Z–A', 'Boyuta göre'])
        self.home_sort.setAccessibleName('Oyunları sırala')
        self.home_sort.currentIndexChanged.connect(self._refresh_shelf)
        shelf_heading.addWidget(self.home_sort)
        body.addLayout(shelf_heading)
        self.home_empty = label('Kütüphanen hazırlanıyor…')
        self.home_empty.setAlignment(Qt.AlignCenter)
        self.home_empty.setMinimumHeight(100)
        body.addWidget(self.home_empty)
        self.shelf = QWidget()
        self.shelf_layout = QGridLayout(self.shelf)
        self.shelf_layout.setContentsMargins(0, 0, 0, 0)
        self.shelf_layout.setHorizontalSpacing(18)
        self.shelf_layout.setVerticalSpacing(18)
        self.shelf.installEventFilter(self)
        body.addWidget(self.shelf)
        body.addStretch()
        scroll.setWidget(surface)
        self.home_scroll = scroll
        scroll.verticalScrollBar().valueChanged.connect(self._request_shelf_covers)
        return scroll

    def show_home(self):
        if not hasattr(self, 'right_stack'):
            return
        self._show_right_page(2)
        self._request_shelf_covers()

    def show_current_game(self):
        if self.current_game:
            self._show_right_page(0)

    def _open_desktop_game(self, row):
        self._select_source_row(row)
        self.show_current_game()

    def _show_right_page(self, index):
        if not hasattr(self, 'right_stack'):
            return
        super()._show_right_page(index)
        self.nav_library.setObjectName('navActive' if index != 1 else 'nav')
        self.nav_library.style().unpolish(self.nav_library)
        self.nav_library.style().polish(self.nav_library)

    def _show_detail_tab(self, index):
        super()._show_detail_tab(index)
        if hasattr(self, 'tab_addons'):
            self.tab_addons.setObjectName('tabActive' if index == 2 else 'tab')
            self.tab_addons.style().unpolish(self.tab_addons)
            self.tab_addons.style().polish(self.tab_addons)

    def _handle_escape(self):
        if self._big_picture:
            super()._handle_escape()
        elif self.right_stack.currentIndex() != 2:
            self.show_home()

    def _set_home_filter(self, installed):
        self._home_installed_only = installed
        for widget, active in ((self.all_filter, not installed), (self.installed_filter, installed)):
            widget.setObjectName('tabActive' if active else 'tab')
            widget.style().unpolish(widget)
            widget.style().polish(widget)
        self._refresh_shelf()

    def render_library(self):
        super().render_library()
        self._refresh_shelf()
        self._sync_desktop_state()
        if self._view_ready:
            self._apply_motion(self.motion_toggle.isChecked())

    def _refresh_shelf(self):
        if not hasattr(self, 'shelf'):
            return
        installed = self._installed_keys()
        rows = []
        for row in range(self.library.count()):
            game, channel = self.library.item(row).data(Qt.UserRole)
            key = self._key(game, channel)
            if not self._home_installed_only or key in installed:
                rows.append((key, game, channel))
        sort = self.home_sort.currentIndex()
        if sort == 1:
            rows.reverse()
        elif sort == 2:
            rows.sort(key=lambda r: int((r[1].get('channels', {}).get(r[2]) or {}).get('size') or 0), reverse=True)
        self._home_rows = rows
        keys = {r[0] for r in rows}
        for key in list(self._cards):
            if key not in keys:
                widget = self._cards.pop(key)
                self.shelf_layout.removeWidget(widget)
                widget.deleteLater()
        for key, game, channel in rows:
            title = str(game.get('title') or 'İsimsiz oyun')
            if key not in self._cards:
                card = LibraryCard(key, title)
                card.activated.connect(self._activate_card)
                self._cards[key] = card
            card = self._cards[key]
            card.title = title
            card.installed = key in installed
            card.percent = self._card_progress.get(key)
            card.motion_enabled = not self.motion_toggle.isChecked()
            card.setAccessibleName(title)
            card.setToolTip(title)
            url = str((game.get('artwork') or {}).get('cover') or '')
            if getattr(card, 'cover_url', '') != url:
                card.pixmap = QPixmap()
            card.cover_url = url
            if url in self._tile_cover_cache:
                card.pixmap = self._tile_cover_cache[url]
            card.update()
        self.home_count.setText(f'{self.library.count()} oyun  •  {len(installed)} kurulu')
        self.shelf_title.setText('Kurulu oyunlar' if self._home_installed_only else 'Tüm oyunlar')
        self.home_empty.setVisible(not rows)
        self.home_empty.setText('Bu görünümde oyun yok. Aramayı, platformu veya yayın kanalını değiştir.' if not self._home_installed_only else 'Bu filtrede kurulu oyun bulunamadı. Tümü sekmesinden oyun seçebilirsin.')
        self._layout_shelf(force=True)
        self._sync_desktop_state()

    def _layout_shelf(self, force=False):
        if not hasattr(self, 'shelf'):
            return
        columns = max(1, (self.shelf.width() + 18) // 184)
        if columns == self._home_columns and not force:
            return
        old_columns = self._home_columns
        self._home_columns = columns
        while self.shelf_layout.count():
            self.shelf_layout.takeAt(0)
        for column in range(max(old_columns, columns) + 1):
            self.shelf_layout.setColumnStretch(column, 0)
        for index, (key, _, _) in enumerate(self._home_rows):
            self.shelf_layout.addWidget(self._cards[key], index // columns, index % columns, Qt.AlignLeft)
        self.shelf_layout.setColumnStretch(columns, 1)
        QTimer.singleShot(0, self._request_shelf_covers)

    def eventFilter(self, watched, event):
        if watched is getattr(self, 'shelf', None) and event.type() == QEvent.Resize:
            self._layout_shelf()
        if watched is getattr(self, 'detail_viewport', None) and event.type() == QEvent.Resize:
            self._layout_details()
        return super().eventFilter(watched, event)

    def _request_shelf_covers(self, *_):
        if not getattr(self, '_view_ready', False) or not self.home_scroll.isVisible():
            return
        viewport = self.home_scroll.viewport()
        for key, card in self._cards.items():
            top = card.mapTo(viewport, card.rect().topLeft()).y()
            if top + card.height() < -150 or top > viewport.height() + 200:
                continue
            if card.cover_url and card.pixmap.isNull() and (key, card.cover_url) not in self._cover_pending:
                self._cover_pending.add((key, card.cover_url))
                self._on_cover_requested(key, card.cover_url)

    def _activate_card(self, key):
        row = self._source_row_map().get(key)
        if row is not None:
            self._open_desktop_game(row)

    def _apply_cover(self, key, pixmap):
        super()._apply_cover(key, pixmap)
        if key in self._cards:
            self._cover_pending.discard((key, self._cards[key].cover_url))
            self._cards[key].pixmap = pixmap
            self._cards[key].update()

    def _cover_loaded(self, key, url, raw):
        self._cover_pending.discard((key, url))
        pixmap = QPixmap()
        if not raw or not pixmap.loadFromData(raw):
            return
        self._tile_cover_cache[url] = pixmap
        # A catalog refresh can change the artwork URL while a request is in
        # flight. Apply to each view only if it still expects this exact URL.
        for view in (self.library_grid, self.library_grid_bp):
            item = view._items.get(key)
            if item is not None and item.cover_url == url:
                view.set_tile_cover(key, pixmap)
                view._sync_item_motion()
        card = self._cards.get(key)
        if card is not None and card.cover_url == url:
            card.pixmap = pixmap
            card.update()

    def _set_tile_progress(self, key, percent):
        super()._set_tile_progress(key, percent)
        if percent is None:
            self._card_progress.pop(key, None)
        elif key:
            self._card_progress[key] = percent
        if key in self._cards:
            self._cards[key].percent = percent
            self._cards[key].update()

    def artwork_loaded(self, token, raw):
        super().artwork_loaded(token, raw)
        if token == self.art_token:
            self._sync_home_hero()

    def library_selection_changed(self, current, previous_item):
        super().library_selection_changed(current, previous_item)
        self._sync_home_hero()
        self._sync_desktop_state()

    def _sync_home_hero(self):
        if not hasattr(self, 'home_hero'):
            return
        self.home_hero.set_art(self.hero.hero, self.hero.logo, str((self.current_game or {}).get('title') or 'Kütüphaneni keşfet'))
        self.home_meta.setText(self.meta.text() if self.current_game else 'Oyunlarını tek bir yerde keşfet ve yönet.')
        self.home_action.setEnabled(bool(self.current_game))

    def update_install_state_ui(self):
        super().update_install_state_ui()
        self._sync_desktop_state()

    def _sync_desktop_state(self):
        if not self._view_ready:
            return
        game = self.current_game
        installed = bool(game and self._record_path_exists(self._record()))
        busy = self._operation_busy()
        self.play_button.setVisible(installed)
        self.play_button.setEnabled(installed and not busy)
        self.game_menu_button.setEnabled(installed and not busy)
        if not game:
            self.verify_button.setEnabled(False)
            self.uninstall_button.setEnabled(False)
        selected = self._key(game, self.current_channel) if game else None
        for key, card in self._cards.items():
            card.selected = key == selected
            card.update()

    def _operation_busy(self):
        return bool(self.download_control or self._addon_busy or self._active_repair_key or getattr(self, '_active_uninstall_key', None))

    def _set_download_controls(self, active):
        super()._set_download_controls(active)
        if active:
            self.transfer_graph.clear()
            self._reset_transfer_metrics()
        self._sync_desktop_state()

    def _reset_transfer_metrics(self):
        for metric in (self.dlp_net, self.dlp_peak, self.dlp_streams, self.dlp_bytes):
            metric.setText('—')
        self.dlp_percent.setText('%0')
        self.dlp_bar.setValue(0)
        self.dlp_eta.setText('Kalan tahmini süre: —')

    def _clear_active_download_ui(self, message):
        super()._clear_active_download_ui(message)
        self.transfer_graph.clear()
        self._reset_transfer_metrics()
        self.dlp_hero.set_hero(None)

    def show_empty_state(self, title, description):
        super().show_empty_state(title, description)
        self._sync_home_hero()
        self._sync_desktop_state()
        if hasattr(self, 'addon_panel'):
            self._refresh_addon_panel()

    def install_progress(self, percent, text):
        super().install_progress(percent, text)
        _, speed, _ = BASE.split_progress_text(text)
        # The downloader emits IEC units (MiB/sn); older views only parsed MB.
        normalized = speed
        for iec, legacy in (('KiB', 'KB'), ('MiB', 'MB'), ('GiB', 'GB'), ('TiB', 'TB')):
            normalized = normalized.replace(iec, legacy)
        if normalized.endswith('/s'):
            normalized = normalized[:-2] + '/sn'
        speed_bytes = BASE.parse_speed_bytes(normalized)
        self.transfer_graph.add_sample(speed_bytes)
        if speed_bytes > self._dl_peak_bytes:
            self._dl_peak_bytes = speed_bytes
            self._dl_peak_text = speed
            self.dlp_peak.setText(speed)
        self.status.setToolTip(self.status.text())

    def _launch_preference_key(self):
        key = self._key(self.current_game, self.current_channel)
        return 'executables/' + hashlib.sha256(key.encode('utf-8')).hexdigest()

    def _choose_executable(self):
        record = self._record()
        if self._operation_busy() or not record or not self._record_path_exists(record):
            return None
        root = Path(record['install_path']).resolve()
        selected, _ = QFileDialog.getOpenFileName(self, 'Oyunun çalıştırılacak dosyasını seç', str(root), 'Windows uygulaması (*.exe)')
        if not selected:
            return None
        path = Path(selected).resolve()
        if not path.is_file() or path.suffix.lower() != '.exe' or not path.is_relative_to(root):
            QMessageBox.warning(self, 'Dosya seçilemedi', 'Kurulu oyunun klasörü içindeki bir .exe dosyasını seç.')
            return None
        self.desktop_preferences.setValue(self._launch_preference_key(), str(path.relative_to(root)))
        return path

    def play_current_game(self):
        if not self.current_game or self._operation_busy() or not self.play_button.isEnabled():
            return
        record = self._record()
        if not record or not self._record_path_exists(record):
            return
        root = Path(record['install_path']).resolve()
        relative = self.desktop_preferences.value(self._launch_preference_key(), '')
        path = (root / str(relative)).resolve() if relative else None
        if path is None or not path.is_relative_to(root) or not path.is_file() or path.suffix.lower() != '.exe':
            path = self._choose_executable()
        if path is None:
            return
        try:
            subprocess.Popen([str(path)], cwd=str(path.parent), shell=False)
        except OSError as exc:
            QMessageBox.warning(self, 'Oyun başlatılamadı', str(exc))
            return
        self.status.setText(f"Başlatıldı: {self.current_game.get('title', 'Oyun')}")

    def _open_game_menu(self):
        if not self.current_game or self._operation_busy() or not self.game_menu_button.isEnabled():
            return
        menu = QMenu(self)
        menu.addAction('Oyun klasörünü aç', lambda: self._open_install_folder(self._key(self.current_game, self.current_channel)))
        menu.addAction('Çalıştırılacak dosyayı seç…', self._choose_executable)
        menu.addSeparator()
        menu.addAction('Dosyaları doğrula', self.verify_button.click)
        menu.exec(self.game_menu_button.mapToGlobal(self.game_menu_button.rect().bottomLeft()))

    def _motion_changed(self, reduced):
        self.desktop_preferences.setValue('reduce_motion', reduced)
        self._apply_motion(reduced)

    def _apply_motion(self, reduced):
        self.motion_toggle.blockSignals(True)
        self.motion_toggle.setChecked(reduced)
        self.motion_toggle.blockSignals(False)
        self.right_stack.motion_enabled = not reduced
        if reduced:
            self.right_stack._fade.stop()
            self.right_stack._effect.setOpacity(1)
        for widget in self.findChildren(MotionButton) + self.findChildren(LibraryCard):
            widget.motion_enabled = not reduced
            if reduced:
                if isinstance(widget, MotionButton):
                    widget._motion.stop()
                else:
                    widget._animation.stop()
                    widget._frame(0)
        for hero in (self.hero, self.home_hero):
            hero.motion_enabled = not reduced
            hero._update_motion()
        for view in (self.library_grid, self.library_grid_bp):
            view.set_motion_enabled(not reduced)
        if getattr(self, '_progress_anim', None):
            self._progress_anim.setDuration(0 if reduced else 210)


def main():
    BASE.base.install_exception_hook()
    app = QApplication(sys.argv)
    app.setApplicationName('Drowned Launcher')
    app.setOrganizationName('Drowned')
    app.setStyle('Fusion')
    app.setStyleSheet(STYLE)
    apply_palette(app)
    win = Launcher()
    win.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
