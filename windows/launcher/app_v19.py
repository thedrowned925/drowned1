"""v19: a Steam-client presentation, rebuilt from scratch.

The window is frameless and carries Steam's own chrome: menu row, STORE /
LIBRARY / DOWNLOADS navigation, account pill, Big Picture button and window
controls. Below it sit the library (collapsible game list + home shelf and
collection wall + the game page with its blurred-hero backdrop), a
catalog storefront in the Steam store's navy palette and the Steam
downloads page with a live network graph. The original Big Picture couch
mode from app_v10/app_v11 is kept and reskinned.

Presentation-only, like every UI layer in this chain: every widget the
inherited backend writes to (install/verify buttons, status/progress,
dlp_* labels, stat_* and panel_* labels, hero, screenshot gallery, library
views) still exists under its historical attribute name, and the visible
controls call the unmodified install / verify / uninstall / pause / cancel /
optional-package methods.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from PySide6.QtCore import QEvent, QProcess, QRect, QRectF, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import (
    QColor,
    QDesktopServices,
    QIcon,
    QKeySequence,
    QLinearGradient,
    QPainter,
    QPixmap,
    QShortcut,
)
from PySide6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplashScreen,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

import app_v16 as previous
import steam_theme as T
from steam_library import LibraryHome, SidebarPanel
from steam_pages import (
    CompletedDownloadRow,
    DownloadsPage,
    GamePage,
    LaunchPicker,
    ScreenshotViewer,
    SteamBottomBar,
    StorePage,
)
from steam_format import (
    find_launch_candidates,
    human_size,
    long_date,
    parse_iso,
    short_date,
    speed_to_bytes,
    time_bucket,
)
from steam_theme import G, V19_STYLE
from steam_widgets import (
    ConnectionLabel,
    CrossFadeStack,
    EdgeGrips,
    ImageHub,
    SteamTitleBar,
    brand_pixmap,
)

APP_VERSION = "0.19.0"
BASE = previous.BASE  # app_v10: UI contracts and helpers

CHANNEL_LABELS = {
    "stable": "Kararlı",
    "beta": "Beta",
    "dev": "Geliştirici",
    "nightly": "Gecelik",
    "archive": "Arşiv",
}
ACTION_MENU_TEXT = {
    "YÜKLE": "Yükle",
    "GÜNCELLE": "Güncelle",
    "YENİDEN YÜKLE": "Yeniden yükle",
    "DEVAM ET": "Devam et",
}
# Busy button captions -> the DURUM stat. Spelled out because str.lower()
# turns the Turkish dotted capital I into "i" plus a combining dot.
BUSY_STATUS_TEXT = {
    "DOĞRULANIYOR…": "Doğrulanıyor",
    "KALDIRILIYOR…": "Kaldırılıyor",
    "İŞLENİYOR…": "İşleniyor",
    "İNDİRİLİYOR…": "İndiriliyor",
}


class MirrorButton(QPushButton):
    """Hidden stand-in for the legacy install/verify buttons. The backend
    keeps writing text and enabled state into it; `changed` lets the
    visible Steam controls follow immediately instead of polling."""

    changed = Signal()

    def setText(self, text):  # noqa: N802 - Qt naming
        super().setText(text)
        self.changed.emit()

    def setEnabled(self, enabled):  # noqa: N802 - Qt naming
        super().setEnabled(enabled)
        self.changed.emit()


class _RightStackAdapter:
    """app_v10's controller code toggles `right_stack` between the library
    (0) and downloads (1); the v19 page model is richer, so translate."""

    def __init__(self, owner: "Launcher"):
        self._owner = owner

    def currentIndex(self) -> int:  # noqa: N802 - Qt naming
        return 1 if self._owner._page == "downloads" else 0

    def setCurrentIndex(self, index: int):  # noqa: N802 - Qt naming
        self._owner._show_right_page(index)

    def count(self) -> int:
        return 2


def _truthy(value) -> bool:
    return value is True or str(value).strip().lower() in ("1", "true", "yes")


class Launcher(previous.Launcher):
    """Steam-client presentation over the unchanged launcher backend."""

    def __init__(self):
        self._v19_ready = False
        self._page = "home"
        self._library_page = "home"
        self._history: list[tuple[str, str | None]] = []
        self._history_index = -1
        self._states: dict[str, dict] = {}
        self._key_index: dict[str, tuple[dict, str]] = {}
        self._star_state = None
        self._states_dirty = True
        self._progress: dict[str, int] = {}
        self._favorites: set[str] = set()
        self._launch_targets: dict[str, str] = {}
        self._store_identity = None
        self._was_downloading = False
        self._peak_speed = 0.0
        self._maximized_before_big_picture = False
        self._last_synced_key = None
        self._shortcuts: list[QShortcut] = []
        self._sync_timer: QTimer | None = None
        super().__init__()
        app = QApplication.instance()
        app.setFont(T.ui_font(13))
        app.setStyleSheet(V19_STYLE)
        self.setWindowTitle(f"Drowned Launcher {APP_VERSION}")
        self.setWindowIcon(app_icon())
        self.setWindowFlags(
            Qt.Window | Qt.FramelessWindowHint | Qt.WindowMinMaxButtonsHint | Qt.WindowSystemMenuHint
        )
        self.setMinimumSize(1100, 700)
        self._adopt_legacy_widgets()
        self._install_shortcuts()
        self._v19_ready = True
        self._restore_window()
        self._compute_states()
        self._refresh_library_views()
        self._refresh_downloads_page()
        self._navigate("home")

    # ------------------------------------------------------------------
    # construction
    # ------------------------------------------------------------------
    def _build_ui(self):
        app = QApplication.instance()
        app.setFont(T.ui_font(13))
        self._images = ImageHub(BASE._fetch_image_bytes, self)
        self._load_preferences()

        root = QWidget()
        root.setObjectName("steamRoot")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self._chrome_widgets = []

        self.title_bar = SteamTitleBar(self)
        outer.addWidget(self.title_bar)
        self._chrome_widgets.append(self.title_bar)
        self.big_picture_button = self.title_bar.big_picture_button
        self.nav_library = self.title_bar.tabs["library"]
        self.nav_downloads = self.title_bar.tabs["downloads"]

        self.logs = QPlainTextEdit()
        self.logs.setReadOnly(True)
        self.logs.hide()
        self.connection = ConnectionLabel("RAW • bağlanıyor")

        self.main_stack = CrossFadeStack()
        self.main_stack.addWidget(self._build_steam_desktop())
        self.library_grid_bp = BASE.GameGridView()
        self.big_picture = BASE.BigPictureView(self.library_grid_bp)
        self.main_stack.addWidget(self.big_picture)
        outer.addWidget(self.main_stack, 1)

        self.bottom_bar = SteamBottomBar(self.connection)
        outer.addWidget(self.bottom_bar)
        self._chrome_widgets.append(self.bottom_bar)
        self.status = self.bottom_bar.status
        self.status_icon = self.bottom_bar.status_icon
        self.progress = self.bottom_bar.progress
        self.progress_text = self.bottom_bar.progress_text
        self._status_row = self.bottom_bar.status_row

        self._build_legacy_contracts(root)
        self.viewer = ScreenshotViewer(self._images, root)
        self._grips = EdgeGrips(root)

        self._wire_runtime()
        # Share one pixmap cache between the v0.19 widgets and app_v10's
        # Big Picture / status-bar artwork code.
        self._tile_cover_cache = self._images.cover_cache
        self._wire_steam()

    def _build_steam_desktop(self) -> QWidget:
        desktop = QWidget()
        layout = QVBoxLayout(desktop)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.desktop_stack = CrossFadeStack()

        self.store_page = StorePage(self._images)
        self.sidebar = SidebarPanel(self._images)
        self.home_page = LibraryHome(self._images)
        self.game_page = GamePage(self._images)
        self.library_stack = CrossFadeStack()
        self.library_stack.addWidget(self.home_page)
        self.library_stack.addWidget(self.game_page)
        self.library_splitter = QSplitter(Qt.Horizontal)
        self.library_splitter.setChildrenCollapsible(False)
        self.library_splitter.setHandleWidth(1)
        self.sidebar.setMinimumWidth(230)
        self.sidebar.setMaximumWidth(460)
        self.library_splitter.addWidget(self.sidebar)
        self.library_splitter.addWidget(self.library_stack)
        self.library_splitter.setStretchFactor(0, 0)
        self.library_splitter.setStretchFactor(1, 1)
        self.library_splitter.setSizes([292, 1200])
        self.main_splitter = self.library_splitter

        self.downloads_page = DownloadsPage(self._images, self.logs)
        self.desktop_stack.addWidget(self.store_page)
        self.desktop_stack.addWidget(self.library_splitter)
        self.desktop_stack.addWidget(self.downloads_page)
        layout.addWidget(self.desktop_stack)
        self.right_stack = _RightStackAdapter(self)

        # -- sidebar contracts ------------------------------------------
        self.search = self.sidebar.search
        self._search_debounce = QTimer(self)
        self._search_debounce.setSingleShot(True)
        self._search_debounce.setInterval(150)
        self._search_debounce.timeout.connect(self.render_library)
        self.search.textChanged.connect(lambda _text: self._search_debounce.start())
        self.library_grid = self.sidebar.list
        self.library_grid.set_state_provider(lambda key: self._states.get(key, {}))

        # -- game page contracts ----------------------------------------
        page = self.game_page
        self.hero = page.hero
        self.description = page.description
        self.stat_platform = page.stat_platform
        self.stat_channel = page.stat_channel
        self.stat_version = page.stat_version
        self.stat_size = page.stat_size
        self.panel_state = page.panel_state
        self.panel_path = page.panel_path
        self.panel_tag = page.panel_tag
        self.panel_repo = page.panel_repo
        self.panel_branch = page.panel_branch
        self.screenshot_gallery = page.screenshot_strip
        self.action_dl_caption = page.action_dl_caption
        self.action_dl_value = page.action_dl_value
        self.action_dl_bar = page.action_dl_bar

        # -- downloads page contracts -----------------------------------
        downloads = self.downloads_page
        self.dlp_hero = downloads.header
        self.dlp_net, self._dlp_peak_shown, self._dlp_total, self.dlp_streams = downloads.header.value_labels
        self.dlp_limit = downloads.header.limit_label
        self.dlp_title = downloads.title
        self.dlp_detail = downloads.detail
        self.dlp_eta = downloads.eta
        self.dlp_percent = downloads.percent
        self.dlp_bar = downloads.bar
        self.dlp_bytes = downloads.bytes
        self.dlp_pause = downloads.pause
        self.dlp_queue_caption = downloads.queue_caption
        self.dlp_queue_body = downloads.queue_body
        self.dlp_done_caption = downloads.done_caption
        self.dlp_done_empty = downloads.done_empty
        self.dlp_rows_layout = downloads.rows_layout
        self._completed_rows: list[QWidget] = []
        return desktop

    def _build_legacy_contracts(self, root: QWidget):
        """Widgets the inherited backend still writes to but the Steam
        layout presents differently. They live in a hidden container."""
        legacy = QWidget(root)
        legacy.setObjectName("legacyContracts")
        legacy.hide()
        layout = QVBoxLayout(legacy)
        action_bar = QFrame(legacy)
        layout.addWidget(action_bar)
        action_layout = QHBoxLayout(action_bar)
        self.info_card = QFrame(action_bar)
        action_layout.addWidget(self.info_card)
        info = QHBoxLayout(self.info_card)
        self.install_button = MirrorButton("YÜKLE")
        self.install_button.setObjectName("install")
        self.install_button.clicked.connect(self.install_current_game)
        self.install_button.setEnabled(False)
        self.verify_button = MirrorButton("DOSYALARI DOĞRULA")
        self.verify_button.setObjectName("secondary")
        self.verify_button.setEnabled(False)
        info.addWidget(self.install_button)
        info.addWidget(self.verify_button)

        self.action_dl = QWidget(legacy)
        layout.addWidget(self.action_dl)
        # app_v10 rewrites its own (never-updating) peak text on every tick;
        # the visible peak is tracked from the graph samples instead.
        self.dlp_peak = QLabel("-", legacy)
        layout.addWidget(self.dlp_peak)
        self.action_pause = QPushButton("DURAKLAT", legacy)
        layout.addWidget(self.action_pause)
        self.state_badge = QLabel("HAZIR", legacy)
        self.download_dot = QLabel("●", legacy)
        self.game_count = QLabel("0 oyun", legacy)
        self.title = QLabel("Kütüphane yükleniyor…", legacy)
        self.meta = QLabel("", legacy)
        self.cover = BASE.previous.CoverLabel()
        self.cover.setParent(legacy)

        self.library = QListWidget(legacy)
        self.library.currentItemChanged.connect(self.library_selection_changed)
        self.platform = QComboBox(legacy)
        self.platform.addItem("Tümü")
        self.channel = QComboBox(legacy)
        self.channel.addItems(["stable", "beta", "dev", "nightly", "archive"])
        self.platform.currentTextChanged.connect(self.render_library)
        self.channel.currentTextChanged.connect(self.render_library)
        for widget in (self.action_pause, self.state_badge, self.download_dot, self.game_count, self.title,
                       self.meta, self.library, self.platform, self.channel):
            layout.addWidget(widget)
        self._legacy = legacy

    def _wire_steam(self):
        bar = self.title_bar
        bar.navRequested.connect(lambda key: self._navigate("library" if key == "library" else key))
        bar.backRequested.connect(self._history_back)
        bar.forwardRequested.connect(self._history_forward)
        bar.settings_button.clicked.connect(self.open_settings)
        bar.menus["app"].aboutToShow.connect(self._fill_app_menu)
        bar.menus["view"].aboutToShow.connect(self._fill_view_menu)
        bar.menus["games"].aboutToShow.connect(self._fill_games_menu)
        bar.menus["help"].aboutToShow.connect(self._fill_help_menu)
        bar.account_menu.aboutToShow.connect(self._fill_account_menu)

        side = self.sidebar
        side.homeRequested.connect(lambda: self._navigate("home"))
        side.collectionRequested.connect(self._show_collection)
        side.filter_menu.aboutToShow.connect(self._fill_filter_menu)
        side.recent_toggle.setChecked(self._pref_sidebar_sort == "recent")
        side.ready_toggle.setChecked(self._pref_installed_only)
        self.library_grid.set_sort_mode(self._pref_sidebar_sort)
        self.library_grid.set_installed_only(self._pref_installed_only)
        side.sortModeChanged.connect(self._sidebar_sort_changed)
        side.installedOnlyChanged.connect(self._installed_only_changed)
        self.library_grid.rowClicked.connect(self._open_game_row)
        self.library_grid.rowDoubleClicked.connect(self._quick_action_row)
        self.library_grid.rowContextMenu.connect(
            lambda row, pos: self._show_context_menu(self._key_for_row(row), pos))

        home = self.home_page
        home.set_sort_value(self._pref_home_sort)
        home.size_slider.setValue(self._pref_capsule_width)
        home.grid.set_capsule_width(self._pref_capsule_width)
        home.set_loading()
        home.openRequested.connect(lambda key: self._navigate("game", key))
        home.actionRequested.connect(self._quick_action_key)
        home.contextRequested.connect(self._show_context_menu)
        home.sortChanged.connect(self._home_sort_changed)
        home.size_slider.valueChanged.connect(lambda value: self.settings.setValue("v19/capsuleWidth", int(value)))
        home.retryRequested.connect(self.load_catalog)
        home.clearFiltersRequested.connect(self._clear_filters)

        page = self.game_page
        page.action_button.clicked.connect(self._on_action_clicked)
        page.cancel_link.clicked.connect(self.cancel_download)
        page.star_button.toggled.connect(self._star_toggled)
        page.gear_menu.aboutToShow.connect(lambda: self._fill_manage_menu(page.gear_menu))
        page.screenshot_strip.openRequested.connect(
            lambda index: self.viewer.open(page.screenshot_strip.urls(), index))
        page.open_folder_link.clicked.connect(lambda: self._open_install_folder(self._current_key() or ""))
        page.repo_link.clicked.connect(self._open_repo)
        for key in ("store", "community", "discussions", "guides"):
            page.subnav.links[key].clicked.connect(lambda _c=False, k=key: self._open_steam_link(k))
        page.subnav.links["files"].clicked.connect(lambda: self._open_install_folder(self._current_key() or ""))

        downloads = self.downloads_page
        downloads.pause.clicked.connect(self._toggle_pause_clicked)
        downloads.cancel.clicked.connect(self.cancel_download)

        self.store_page.openRequested.connect(lambda key: self._navigate("game", key))
        self.bottom_bar.downloadsRequested.connect(lambda: self._navigate("downloads"))
        self.bottom_bar.refresh_button.clicked.connect(self.load_catalog)

        self.install_button.changed.connect(self._schedule_sync)
        self.verify_button.changed.connect(self._schedule_sync)
        self.main_stack.currentChanged.connect(self._main_stack_changed)

        self._graph_timer = QTimer(self)
        self._graph_timer.setInterval(1000)
        self._graph_timer.timeout.connect(self._graph_tick)

    def _adopt_legacy_widgets(self):
        # app_v12's optional-package panel was inserted into the hidden legacy
        # container; host it in the game page's optional content section.
        panel = getattr(self, "addon_panel", None)
        if panel is not None:
            panel.setParent(None)
            if panel.layout() is not None:
                panel.layout().setContentsMargins(16, 12, 16, 14)
            for label in panel.findChildren(QLabel):
                if label.objectName() == "panelTitle":
                    label.hide()
            self.game_page.dlc_layout.addWidget(panel)
            panel.show()
        for widget in (getattr(self, "uninstall_button", None), getattr(self, "pause_button", None),
                       getattr(self, "cancel_button", None)):
            if widget is not None:
                widget.installEventFilter(self)
        self.logs.installEventFilter(self)
        for button in (getattr(self, "pause_button", None), getattr(self, "cancel_button", None)):
            if button is not None:
                button.setCursor(Qt.PointingHandCursor)

    def _install_shortcuts(self):
        bindings = (
            ("F5", self.load_catalog),
            ("Ctrl+F", self._focus_search),
            ("Alt+Left", self._history_back),
            ("Alt+Right", self._history_forward),
            ("Ctrl+1", lambda: self._navigate("store")),
            ("Ctrl+2", lambda: self._navigate("library")),
            ("Ctrl+3", lambda: self._navigate("downloads")),
        )
        for sequence, handler in bindings:
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.activated.connect(handler)
            self._shortcuts.append(shortcut)

    # ------------------------------------------------------------------
    # preferences and window state
    # ------------------------------------------------------------------
    def _load_preferences(self):
        settings = self.settings
        try:
            self._favorites = set(json.loads(str(settings.value("v19/favorites", "[]") or "[]")))
        except (TypeError, ValueError):
            self._favorites = set()
        try:
            self._launch_targets = dict(json.loads(str(settings.value("v19/launchTargets", "{}") or "{}")))
        except (TypeError, ValueError):
            self._launch_targets = {}
        self._pref_sidebar_sort = str(settings.value("v19/sidebarSort", "alpha") or "alpha")
        self._pref_installed_only = _truthy(settings.value("v19/installedOnly", "false"))
        self._pref_home_sort = str(settings.value("v19/homeSort", "alpha") or "alpha")
        try:
            self._pref_capsule_width = int(settings.value("v19/capsuleWidth", 170))
        except (TypeError, ValueError):
            self._pref_capsule_width = 170

    def _save_favorites(self):
        self.settings.setValue("v19/favorites", json.dumps(sorted(self._favorites)))

    def _restore_window(self):
        geometry = self.settings.value("v19/geometry")
        if geometry:
            self.restoreGeometry(geometry)
        splitter = self.settings.value("v19/splitter")
        if splitter:
            self.library_splitter.restoreState(splitter)
        if _truthy(self.settings.value("v19/maximized", "false")):
            self.setWindowState(self.windowState() | Qt.WindowMaximized)

    def closeEvent(self, event):  # noqa: N802 - Qt naming
        if not getattr(self, "_big_picture", False) and not self.isFullScreen():
            self.settings.setValue("v19/maximized", "true" if self.isMaximized() else "false")
            if not self.isMaximized():
                self.settings.setValue("v19/geometry", self.saveGeometry())
        self.settings.setValue("v19/splitter", self.library_splitter.saveState())
        self._images.shutdown()
        super().closeEvent(event)

    def changeEvent(self, event):  # noqa: N802 - Qt naming
        super().changeEvent(event)
        if event.type() == QEvent.WindowStateChange and hasattr(self, "title_bar"):
            self.title_bar.sync_window_state()
            self._grips.set_enabled(not (self.isMaximized() or self.isFullScreen()))

    def resizeEvent(self, event):  # noqa: N802 - Qt naming
        super().resizeEvent(event)
        if hasattr(self, "_grips"):
            self._grips.update_geometry()
            self._place_viewer()

    def mousePressEvent(self, event):  # noqa: N802 - Qt naming
        if event.button() == Qt.BackButton:
            self._history_back()
            return
        if event.button() == Qt.ForwardButton:
            self._history_forward()
            return
        super().mousePressEvent(event)

    def eventFilter(self, watched, event):  # noqa: N802 - Qt naming
        kind = event.type()
        if kind in (QEvent.EnabledChange, QEvent.ShowToParent, QEvent.HideToParent):
            if watched is getattr(self, "logs", None):
                self.downloads_page.log_section.setVisible(not self.logs.isHidden())
            else:
                self._schedule_sync()
        return False

    def _place_viewer(self):
        root = self.centralWidget()
        if root is None:
            return
        top = 0 if self.title_bar.isHidden() else self.title_bar.height()
        self.viewer.setGeometry(QRect(0, top, root.width(), root.height() - top))

    # ------------------------------------------------------------------
    # navigation
    # ------------------------------------------------------------------
    def _current_key(self) -> str | None:
        if not self.current_game:
            return None
        return self._key(self.current_game, self.current_channel)

    def _navigate(self, page: str, key: str | None = None, record: bool = True):
        if page == "library":
            page = self._library_page
        if page == "game":
            if key is not None and key != self._current_key() and not self._select_key(key):
                page = "home"
            if not self.current_game:
                page = "home"
        if page == "store":
            self.desktop_stack.setCurrentWidget(self.store_page)
            tab = "store"
        elif page == "downloads":
            self.desktop_stack.setCurrentWidget(self.downloads_page)
            tab = "downloads"
            self._refresh_downloads_page()
        else:
            self.desktop_stack.setCurrentWidget(self.library_splitter)
            self._library_page = page
            self.library_stack.setCurrentWidget(self.game_page if page == "game" else self.home_page)
            self.sidebar.set_home_active(page == "home")
            tab = "library"
        self._page = page
        self.title_bar.set_active_tab(tab)
        if record:
            entry = (page, self._current_key() if page == "game" else None)
            if not self._history or self._history[self._history_index] != entry:
                del self._history[self._history_index + 1:]
                self._history.append(entry)
                if len(self._history) > 60:
                    self._history.pop(0)
                self._history_index = len(self._history) - 1
        self.title_bar.set_history_state(self._history_index > 0, self._history_index < len(self._history) - 1)

    def _history_back(self):
        if self._history_index > 0:
            self._history_index -= 1
            page, key = self._history[self._history_index]
            self._navigate(page, key, record=False)

    def _history_forward(self):
        if self._history_index < len(self._history) - 1:
            self._history_index += 1
            page, key = self._history[self._history_index]
            self._navigate(page, key, record=False)

    def _show_right_page(self, index: int):
        self._navigate("downloads" if index == 1 else "library")

    def _show_collection(self):
        self._navigate("home")
        QTimer.singleShot(0, self.home_page.scroll_to_grid)

    def _focus_search(self):
        if self._page in ("store", "downloads"):
            self._navigate("library")
        self.search.setFocus(Qt.ShortcutFocusReason)
        self.search.selectAll()

    def _main_stack_changed(self, index: int):
        in_big_picture = index == 1
        if in_big_picture:
            self._maximized_before_big_picture = self.isMaximized()
        elif self._maximized_before_big_picture:
            # app_v10 leaves Big Picture through showNormal(); come back to
            # the maximised desktop window the user left.
            self._maximized_before_big_picture = False
            QTimer.singleShot(0, self.showMaximized)
        self._set_big_picture_shimmer(in_big_picture)
        if in_big_picture and self.viewer.is_open():
            self.viewer.close_viewer()
        self._place_viewer()

    # ------------------------------------------------------------------
    # library data helpers
    # ------------------------------------------------------------------
    def _visible_rows(self) -> list[tuple[str, dict, str, int]]:
        rows = []
        for row in range(self.library.count()):
            payload = self.library.item(row).data(Qt.UserRole)
            if payload:
                game, channel = payload
                rows.append((self._key(game, channel), game, channel, row))
        return rows

    def _key_for_row(self, row: int) -> str | None:
        if 0 <= row < self.library.count():
            payload = self.library.item(row).data(Qt.UserRole)
            if payload:
                return self._key(payload[0], payload[1])
        return None

    def _row_for_key(self, key: str) -> int:
        for row in range(self.library.count()):
            payload = self.library.item(row).data(Qt.UserRole)
            if payload and self._key(payload[0], payload[1]) == key:
                return row
        return -1

    def _catalog_entry(self, key: str):
        entry = self._key_index.get(key)
        if entry is not None:
            return entry
        for game in self.catalog.get("games") or []:
            for channel in (game.get("channels") or {}):
                if self._key(game, channel) == key:
                    return game, channel
        return None, None

    def _select_key(self, key: str) -> bool:
        row = self._row_for_key(key)
        if row < 0:
            game, channel = self._catalog_entry(key)
            if game is None:
                return False
            self._reset_filters(channel)
            row = self._row_for_key(key)
            if row < 0:
                return False
        if self.library.currentRow() != row:
            self.library.setCurrentRow(row)
        return True

    def _reset_filters(self, channel: str | None = None):
        for widget, action in (
            (self.search, lambda: self.search.clear()),
            (self.platform, lambda: self.platform.setCurrentIndex(0)),
            (self.channel, lambda: self.channel.setCurrentText(channel or "stable")),
        ):
            widget.blockSignals(True)
            action()
            widget.blockSignals(False)
        if self.sidebar.ready_toggle.isChecked():
            self.sidebar.ready_toggle.blockSignals(True)
            self.sidebar.ready_toggle.setChecked(False)
            self.sidebar.ready_toggle.blockSignals(False)
            self._installed_only_changed(False)
        self.render_library()

    def _clear_filters(self):
        self._reset_filters(self.channel.currentText() or "stable")

    def _compute_states(self):
        registry = getattr(self, "install_registry", None) or {}
        records = registry.get("games") or {}
        partials = registry.get("partials") or {}
        control = getattr(self, "download_control", None)
        active = self._active_key() if control is not None else ""
        paused = bool(control is not None and control.paused)
        states: dict[str, dict] = {}
        index: dict[str, tuple[dict, str]] = {}
        for game in self.catalog.get("games") or []:
            for channel, data in (game.get("channels") or {}).items():
                if not isinstance(data, dict):
                    continue
                key = self._key(game, channel)
                index[key] = (game, channel)
                record = records.get(key)
                installed = bool(record) and self._record_path_exists(record)
                update = installed and str(record.get("tag") or "") != str(data.get("tag") or "")
                partial = False
                if not installed and key in partials:
                    try:
                        path = Path(str(partials[key].get("install_path") or ""))
                        partial = (path / ".drowned" / "state.json").is_file()
                    except Exception:
                        partial = False
                published = parse_iso(data.get("published_at"))
                installed_at = parse_iso(record.get("installed_at")) if installed else None
                moment = installed_at or published
                states[key] = {
                    "installed": installed,
                    "update": update,
                    "partial": partial,
                    "favorite": key in self._favorites,
                    "downloading": bool(active) and key == active,
                    "paused": paused and key == active,
                    "published": published,
                    "installed_at": installed_at,
                    "recent_ts": moment.timestamp() if moment else 0.0,
                }
        self._states = states
        self._key_index = index
        self._states_dirty = False

    def _grid_item(self, key: str, game: dict, channel: str) -> dict:
        state = self._states.get(key, {})
        data = (game.get("channels") or {}).get(channel) or {}
        artwork = game.get("artwork") or {}
        return {
            "key": key,
            "title": str(game.get("title") or ""),
            "cover_url": str(artwork.get("cover") or ""),
            "hero_url": str(artwork.get("hero") or ""),
            "logo_url": str(artwork.get("logo") or ""),
            "badge": "YENİ" if BASE.Launcher._is_recent(data) else "",
            "progress": self._progress.get(key),
            "action": "play" if state.get("installed") and not state.get("update") else "install",
            "published": state.get("published"),
            "installed_at": state.get("installed_at"),
            "size": int(data.get("size") or 0),
        }

    def _store_entries(self) -> list[dict]:
        entries = []
        for game in self.catalog.get("games") or []:
            channels = game.get("channels") or {}
            if not channels:
                continue
            channel = "stable" if "stable" in channels else next(iter(channels))
            data = channels.get(channel) or {}
            key = self._key(game, channel)
            state = self._states.get(key, {})
            artwork = game.get("artwork") or {}
            published = parse_iso(data.get("published_at"))
            tags = [str(game.get("platform") or "pc").upper(), CHANNEL_LABELS.get(channel, channel)]
            if state.get("installed"):
                tags.append("Yüklü")
            entries.append({
                "key": key,
                "title": str(game.get("title") or ""),
                "hero_url": str(artwork.get("hero") or ""),
                "cover_url": str(artwork.get("cover") or ""),
                "logo_url": str(artwork.get("logo") or ""),
                "shots": [str(url) for url in (artwork.get("screenshots") or [])[:4]],
                "published": published,
                "long_date": long_date(published),
                "date_text": short_date(published),
                "size_text": human_size(data.get("size") or 0),
                "tags": tags,
                "installed": bool(state.get("installed")),
            })
        entries.sort(key=lambda entry: entry["published"].timestamp() if entry["published"] else 0.0, reverse=True)
        return entries

    # ------------------------------------------------------------------
    # inherited extension points (presentation only)
    # ------------------------------------------------------------------
    def render_library(self):
        if getattr(self, "_v19_ready", False):
            self._compute_states()
        super().render_library()
        if getattr(self, "_v19_ready", False):
            self._refresh_library_views()

    def library_selection_changed(self, current, previous_item):
        super().library_selection_changed(current, previous_item)
        if getattr(self, "_v19_ready", False):
            self._sync_game_page()

    def update_install_state_ui(self):
        super().update_install_state_ui()
        if getattr(self, "_v19_ready", False):
            self._states_dirty = True
            self._schedule_sync()

    def artwork_loaded(self, token: str, raw: dict):
        super().artwork_loaded(token, raw)
        if not getattr(self, "_v19_ready", False) or token != self.art_token or not self.current_game:
            return
        artwork = self.current_game.get("artwork") or {}
        hero = self.hero.hero
        if not hero.isNull():
            if hero.width() > 1920:
                hero = hero.scaledToWidth(1920, Qt.SmoothTransformation)
            self._images.put("hero", str(artwork.get("hero") or ""), hero)
        if not self.hero.logo.isNull():
            self._images.put("logo", str(artwork.get("logo") or ""), self.hero.logo)
        self._schedule_sync()

    def catalog_error(self, message: str):
        QTimer.singleShot(0, self._refresh_library_views)
        super().catalog_error(message)

    def _cover_loaded(self, key: str, url: str, raw):
        # Same as app_v10, but apply the pixmap the shared cache kept, which
        # is the portrait recomposition for landscape-only cover art.
        if not raw:
            return
        pixmap = QPixmap()
        if not pixmap.loadFromData(raw):
            return
        self._tile_cover_cache[url] = pixmap
        self._apply_cover(key, self._tile_cover_cache[url])

    def _set_tile_progress(self, key: str, percent):
        super()._set_tile_progress(key, percent)
        if not key or not getattr(self, "_v19_ready", False):
            return
        if percent is None:
            self._progress.pop(key, None)
        else:
            self._progress[key] = int(percent)
        self.home_page.grid.update_item(key, progress=percent)
        self._schedule_sync()

    def _refresh_downloads_page(self):
        if not hasattr(self, "downloads_page"):
            return
        page = self.downloads_page
        for row in self._completed_rows:
            self.dlp_rows_layout.removeWidget(row)
            row.setParent(None)
            row.deleteLater()
        self._completed_rows = []
        records = [
            dict(record, key=key)
            for key, record in (self.install_registry.get("games") or {}).items()
            if self._record_path_exists(record)
        ]
        records.sort(key=lambda r: str(r.get("installed_at") or ""), reverse=True)
        self.dlp_done_caption.setText("Tamamlanan")
        page.done_count.setText(f"({len(records)})")
        self.dlp_done_empty.setVisible(not records)
        for record in records:
            key = str(record.get("key") or "")
            game, channel = self._catalog_entry(key)
            data = ((game or {}).get("channels") or {}).get(channel) or {}
            title = str(record.get("title") or (game or {}).get("title") or "?")
            parts = [f"v{record.get('version', '?')}", CHANNEL_LABELS.get(str(record.get("channel") or ""),
                                                                           str(record.get("channel") or "").upper())]
            if data.get("size"):
                parts.append(human_size(data.get("size")))
            finished = f"Tamamlandı: {short_date(record.get('installed_at'))}"
            row = CompletedDownloadRow(key, title, "  ·  ".join(p for p in parts if p), finished, True)
            row.playRequested.connect(self._play_key)
            row.openRequested.connect(self._open_install_folder)
            row.removeRequested.connect(self._forget_install_record)
            hero_url = str(((game or {}).get("artwork") or {}).get("hero") or "")
            art = self._images.request("wide", hero_url, lambda _u, pm, target=row, t=title: target.art.set_art(pm, t))
            if art is not None:
                row.art.set_art(art, title)
            self.dlp_rows_layout.addWidget(row)
            self._completed_rows.append(row)
        page.queue_count.setText("(0)")
        self.big_picture.dl_installed.setText(
            "\n".join(f"{r.get('title', '?')}   v{r.get('version', '?')}" for r in records)
            or "Henüz kurulu oyun yok."
        )

    # ------------------------------------------------------------------
    # view refresh
    # ------------------------------------------------------------------
    def _schedule_sync(self):
        if not getattr(self, "_v19_ready", False):
            return
        if self._sync_timer is None:
            self._sync_timer = QTimer(self)
            self._sync_timer.setSingleShot(True)
            self._sync_timer.setInterval(0)
            self._sync_timer.timeout.connect(self._run_sync)
        if not self._sync_timer.isActive():
            self._sync_timer.start()

    def _run_sync(self):
        if self._states_dirty:
            before = self._states
            self._compute_states()
            # update_install_state_ui runs on every selection change; only
            # rebuild the lists when an install/favourite state really moved.
            if self._states != before:
                self.library_grid.refresh_states()
                self._refresh_library_views()
        self._sync_game_page(light=True)
        self._sync_download_views()

    def _refresh_library_views(self):
        if not getattr(self, "_v19_ready", False):
            return
        games = self.catalog.get("games") or []
        self.title_bar.account_button.set_account(str(self.owner or "drowned"), f"{len(games)} oyun")
        if games and id(self.catalog) != self._store_identity:
            self._store_identity = id(self.catalog)
            self.store_page.set_games(self._store_entries())
        else:
            self.store_page.refresh_states(self._states)
        self.sidebar.set_filter_label(self._filter_label())

        if not games:
            if self.catalog_loading:
                self.home_page.set_loading()
            else:
                self.home_page.show_error(
                    "Katalog henüz alınamadı",
                    "Raw GitHub bağlantısı kurulamadı. Bağlantı hazır olduğunda tekrar dene.",
                )
            return
        rows = self._visible_rows()
        installed_only = self.sidebar.ready_toggle.isChecked()
        items = [
            self._grid_item(key, game, channel)
            for key, game, channel, _row in rows
            if not installed_only or self._states.get(key, {}).get("installed")
        ]
        if not items:
            self.home_page.show_filtered_empty()
            return
        sort = self.home_page.sort_value()
        if sort == "published":
            items.sort(key=lambda it: it["published"].timestamp() if it["published"] else 0.0, reverse=True)
        elif sort == "size":
            items.sort(key=lambda it: it["size"], reverse=True)
        else:
            items.sort(key=lambda it: it["title"].casefold())
        shelf_title, shelf = self._shelf_items(rows)
        self.home_page.set_content(shelf_title, shelf, items)
        self._feed_big_picture_covers()
        if self.main_stack.currentIndex() != 1:
            self._set_big_picture_shimmer(False)

    def _shelf_items(self, rows) -> tuple[str, list[dict]]:
        installed = [(key, game, channel) for key, game, channel, _r in rows
                     if self._states.get(key, {}).get("installed")]
        if installed:
            def installed_ts(item):
                moment = self._states[item[0]].get("installed_at")
                return moment.timestamp() if moment else 0.0

            installed.sort(key=installed_ts, reverse=True)
            picked, title, field = installed[:12], "SON YÜKLENENLER", "installed_at"
        else:
            newest = sorted(rows, key=lambda it: self._states.get(it[0], {}).get("recent_ts", 0.0), reverse=True)
            picked, title, field = [(k, g, c) for k, g, c, _r in newest[:10]], "YENİ EKLENENLER", "published"
        items = []
        for index, (key, game, channel) in enumerate(picked):
            item = self._grid_item(key, game, channel)
            item["wide"] = index == 0
            item["caption"] = time_bucket(self._states.get(key, {}).get(field))
            items.append(item)
        return title, items

    def _filter_label(self) -> str:
        channel = self.channel.currentText()
        platform = self.platform.currentText()
        parts = ["OYUNLAR"]
        if channel and channel != "stable":
            parts.append(CHANNEL_LABELS.get(channel, channel).upper())
        if platform and platform != "Tümü":
            parts.append(platform)
        return "  ·  ".join(parts)

    def _feed_big_picture_covers(self):
        for key, widget in list(getattr(self.library_grid_bp, "_items", {}).items()):
            if key.startswith("__skeleton_") or not getattr(widget, "_loading", False):
                continue
            pixmap = self._images.pixmap("cover", getattr(widget, "cover_url", ""))
            if pixmap is not None:
                widget.set_cover(pixmap)

    def _set_big_picture_shimmer(self, active: bool):
        """app_v10 capsules run an endless shimmer until their cover
        arrives; pause those animations while Big Picture is not shown."""
        for widget in list(getattr(self.library_grid_bp, "_items", {}).values()):
            animation = getattr(widget, "_shimmer_anim", None)
            if animation is None:
                continue
            if active and getattr(widget, "_loading", False):
                animation.start()
            elif not active:
                animation.stop()

    def _sync_game_page(self, light: bool = False):
        game = self.current_game
        if not game:
            return
        key = self._current_key()
        state = self._states.get(key, {})
        data = (game.get("channels") or {}).get(self.current_channel) or {}
        artwork = game.get("artwork") or {}
        title = str(game.get("title") or "")
        page = self.game_page
        if not light:
            self.hero.expect(key)
            if self.hero.hero.isNull():
                cached_hero = self._images.pixmap("hero", str(artwork.get("hero") or ""))
                if cached_hero is not None:
                    self.hero.set_art(cached_hero, self._images.pixmap("logo", str(artwork.get("logo") or "")), title)
            page.panel_published.setText(long_date(data.get("published_at")))
            page.set_steam_links((game.get("media") or {}).get("steam_app_id"))
            if key != self._last_synced_key:
                page.scroll_to_top()
                self._last_synced_key = key
        tags = []
        if state.get("installed"):
            tags.append("YEREL OLARAK YÜKLÜ")
        if state.get("update"):
            tags.append("GÜNCELLEME VAR")
        if BASE.Launcher._is_recent(data):
            tags.append("YENİ")
        tags.append(CHANNEL_LABELS.get(self.current_channel, self.current_channel).upper())
        self.hero.set_tags(tags)
        installed = bool(state.get("installed"))
        page.subnav.links["files"].setEnabled(installed)
        page.open_folder_link.setEnabled(installed)
        favorite = key in self._favorites
        if self._star_state != favorite:
            self._star_state = favorite
            page.star_button.blockSignals(True)
            page.star_button.setChecked(favorite)
            page.star_button.blockSignals(False)
            page.star_button.setIcon(T.glyph_icon(G.STAR_FILLED if favorite else G.STAR, 15,
                                                  "#e2c044" if favorite else T.TEXT_MUTED, "#ffffff"))
            page.star_button.setToolTip("Favorilerden çıkar" if favorite else "Favorilere ekle")
        page.dlc_host.setVisible(bool(getattr(self, "_addon_rows", [])))
        self._sync_action_state()

    def _action_state(self) -> tuple[str, str, bool, str]:
        """(mode, text, enabled, extra) for the big game-page button."""
        if not self.current_game:
            return "install", "YÜKLE", False, ""
        key = self._current_key()
        control = getattr(self, "download_control", None)
        if control is not None and self._active_key() == key:
            if control.paused:
                return "resume", "DEVAM ET", True, "download"
            return "pause", "DURAKLAT", True, "download"
        if getattr(self, "_active_uninstall_key", None) == key:
            return "busy", "KALDIRILIYOR…", False, ""
        if getattr(self, "_active_repair_key", None) == key:
            return "busy", "DOĞRULANIYOR…", False, ""
        if getattr(self, "_addon_busy", False):
            return "busy", "İŞLENİYOR…", False, ""
        text = self.install_button.text()
        enabled = self.install_button.isEnabled()
        record = self._record()
        if record and self._record_path_exists(record) and text == "YÜKLÜ":
            return "play", "OYNA", True, ""
        if control is not None:
            return "install", text, False, "blocked"
        if enabled:
            return "install", text, True, ""
        return "busy", text, False, ""

    def _sync_action_state(self):
        page = self.game_page
        mode, text, enabled, extra = self._action_state()
        page.action_button.set_state(mode, text, enabled)
        page.set_download_visible(extra == "download")
        if extra == "blocked":
            active_title = str((getattr(self, "_active_install_context", None) or {}).get("title") or "")
            page.set_blocked_note(f"Başka bir indirme sürüyor: {active_title}" if active_title else
                                  "Başka bir indirme sürüyor")
        else:
            page.set_blocked_note("")
        key = self._current_key()
        state = self._states.get(key, {}) if key else {}
        control = getattr(self, "download_control", None)
        if extra == "download":
            paused = bool(control is not None and control.paused)
            status = ("Duraklatıldı" if paused else "İndiriliyor", G.DOWNLOAD, T.STATUS_BLUE_LIGHT)
            done = self.dlp_bytes.text()
            page.dl_bytes.setText("" if done in ("", "-") else done)
        elif mode == "busy" and text.endswith("…"):
            status = (BUSY_STATUS_TEXT.get(text, "İşleniyor"), G.SYNC, T.STATUS_BLUE_LIGHT)
        elif state.get("update"):
            status = ("Güncelleme var", G.SYNC, T.STATUS_BLUE_LIGHT)
        elif state.get("installed"):
            status = ("Yüklü", G.CHECK, "#90ba3c")
        elif state.get("partial"):
            status = ("Yarım kaldı", G.DOWNLOAD, T.STATUS_BLUE_LIGHT)
        else:
            status = ("Yüklü değil", G.CLOUD, T.TEXT_MUTED)
        page.set_status(status[1], status[0], status[2])

    def _sync_download_views(self):
        control = getattr(self, "download_control", None)
        downloading = control is not None
        paused = bool(downloading and control.paused)
        page = self.downloads_page
        if downloading and not self._was_downloading:
            page.header.clear_samples()
            self._peak_speed = 0.0
            self._dlp_peak_shown.setText("-")
            self._graph_timer.start()
        elif not downloading and self._was_downloading:
            self._graph_timer.stop()
        self._was_downloading = downloading
        if downloading and not paused:
            self._note_speed(speed_to_bytes(self.dlp_net.text()))
        page.header.title.setText("DURAKLATILDI" if paused else "İNDİRİLİYOR" if downloading else "İNDİRME YOK")
        page.state.setText(("DURAKLATILDI" if paused else "İNDİRİLİYOR") if downloading else "")
        page.pause.set_paused(paused)
        page.cancel.setVisible(downloading)
        self.bottom_bar.dl_glyph.setVisible(not downloading)
        if downloading:
            key = self._active_key()
            game, _channel = self._catalog_entry(key)
            artwork = (game or {}).get("artwork") or {}
            title = str((game or {}).get("title") or self.dlp_title.text())
            art = self._images.request("wide", str(artwork.get("hero") or ""),
                                       lambda _u, pm, t=title: page.active_art.set_art(pm, t))
            page.active_art.set_art(art, title)
            if not page.header.has_hero():
                # The download may have started before its hero finished
                # loading, in which case app_v10 handed the banner nothing.
                hero = self._images.request("hero", str(artwork.get("hero") or ""),
                                            lambda _u, pm: page.header.set_hero(pm) if pm is not None else None)
                if hero is not None:
                    page.header.set_hero(hero)
            done = self.dlp_bytes.text().split("/")[0].strip()
            self._dlp_total.setText(done or "-")
            cover = self._images.pixmap("cover", str(artwork.get("cover") or ""))
            if cover is not None:
                self.status_icon.set_icon(cover)
        else:
            page.active_art.set_art(None, "")

    def _graph_tick(self):
        control = getattr(self, "download_control", None)
        if control is None:
            self._graph_timer.stop()
            return
        speed = 0.0 if control.paused else speed_to_bytes(self.dlp_net.text())
        self._note_speed(speed)
        self.downloads_page.header.push_sample(speed)

    def _note_speed(self, speed: float):
        if speed > getattr(self, "_peak_speed", 0.0):
            self._peak_speed = speed
            self._dlp_peak_shown.setText(f"{human_size(speed)}/sn")

    def _on_gamepad_action(self, action: str):
        """Desktop controller routing on top of app_v10/app_v11: the game
        list keeps the D-pad, RIGHT/LEFT hop between the list and the big
        PLAY/INSTALL button, and A presses whichever of the two has focus.
        Big Picture keeps the inherited handling untouched."""
        if getattr(self, "_big_picture", False) or not getattr(self, "_v19_ready", False):
            super()._on_gamepad_action(action)
            return
        focus = self.focusWidget()
        button = self.game_page.action_button
        in_list = focus is not None and self.library_grid.isAncestorOf(focus)
        if focus is button:
            if action == "activate":
                if button.isEnabled():
                    button.click()
                return
            if action in ("left", "back"):
                self.library_grid.focus_selection()
                return
            if action in ("up", "down", "right"):
                return
        elif action == "right" and (in_list or focus is None) and self._page == "game":
            button.setFocus(Qt.OtherFocusReason)
            return
        elif action == "activate" and isinstance(focus, QAbstractButton) and not isinstance(focus, QPushButton):
            if focus.isEnabled():
                focus.click()
            return
        super()._on_gamepad_action(action)

    # ------------------------------------------------------------------
    # actions
    # ------------------------------------------------------------------
    def _open_game_row(self, row: int):
        key = self._key_for_row(row)
        if key:
            self._navigate("game", key)

    def _quick_action_row(self, row: int):
        key = self._key_for_row(row)
        if key:
            self._quick_action_key(key)

    def _quick_action_key(self, key: str):
        self._navigate("game", key)
        if self._current_key() == key and self.game_page.action_button.isEnabled():
            self._on_action_clicked()

    def _on_action_clicked(self):
        mode = self.game_page.action_button.mode()
        if mode == "play":
            self._play_current_game()
        elif mode in ("pause", "resume"):
            self._toggle_pause_clicked()
        elif mode == "install":
            self.install_current_game()
            self._schedule_sync()

    def _toggle_pause_clicked(self):
        self.toggle_pause()
        self._schedule_sync()

    def _star_toggled(self, checked: bool):
        key = self._current_key()
        if key:
            self._set_favorite(key, checked)

    def _set_favorite(self, key: str, favorite: bool):
        if favorite:
            self._favorites.add(key)
        else:
            self._favorites.discard(key)
        self._save_favorites()
        self._states_dirty = True
        self._schedule_sync()

    def _sidebar_sort_changed(self, mode: str):
        self.settings.setValue("v19/sidebarSort", mode)
        self.library_grid.set_sort_mode(mode)

    def _installed_only_changed(self, value: bool):
        self.settings.setValue("v19/installedOnly", "true" if value else "false")
        self.library_grid.set_installed_only(value)
        self._refresh_library_views()

    def _home_sort_changed(self, value: str):
        self.settings.setValue("v19/homeSort", value)
        self._refresh_library_views()

    def _open_url(self, url: str):
        if url:
            QDesktopServices.openUrl(QUrl(url))

    def _open_repo(self):
        self._open_url(f"https://github.com/{self.owner}/{self.repo}")

    def _open_steam_link(self, kind: str):
        app_id = ((self.current_game or {}).get("media") or {}).get("steam_app_id")
        if not app_id:
            return
        urls = {
            "store": f"https://store.steampowered.com/app/{app_id}/",
            "community": f"https://steamcommunity.com/app/{app_id}",
            "discussions": f"https://steamcommunity.com/app/{app_id}/discussions/",
            "guides": f"https://steamcommunity.com/app/{app_id}/guides/",
        }
        self._open_url(urls.get(kind, ""))

    # -- launching ---------------------------------------------------------
    def _play_key(self, key: str):
        self._navigate("game", key)
        if self._current_key() == key:
            self._play_current_game()

    def _play_current_game(self, choose: bool = False):
        game = self.current_game
        if not game:
            return
        key = self._current_key()
        title = str(game.get("title") or "Oyun")
        record = self._record()
        if not record or not self._record_path_exists(record):
            QMessageBox.warning(self, "Oyun kurulu değil", f"{title} için geçerli bir kurulum klasörü bulunamadı.")
            return
        root = Path(str(record.get("install_path")))
        target = None if choose else self._saved_launch_target(key, root)
        if target is None:
            target = self._choose_launch_target(title, str(game.get("id") or ""), root, force_dialog=choose)
            if target is None:
                return
            self._remember_launch_target(key, root, target)
        self._start_target(title, target)

    def _choose_current_launch_target(self):
        self._play_current_game(choose=True)

    def _saved_launch_target(self, key: str, root: Path) -> Path | None:
        stored = self._launch_targets.get(key)
        if not stored:
            return None
        path = Path(stored)
        if not path.is_absolute():
            path = root / stored
        return path if path.is_file() else None

    def _remember_launch_target(self, key: str, root: Path, target: Path):
        try:
            value = target.relative_to(root).as_posix()
        except ValueError:
            value = str(target)
        self._launch_targets[key] = value
        self.settings.setValue("v19/launchTargets", json.dumps(self._launch_targets))

    def _choose_launch_target(self, title: str, game_id: str, root: Path, force_dialog: bool = False) -> Path | None:
        candidates = find_launch_candidates(root, title, game_id)
        if len(candidates) == 1 and not force_dialog:
            return candidates[0]
        if candidates:
            dialog = LaunchPicker(title, root, candidates, self)
            if dialog.exec() and dialog.chosen() is not None:
                return dialog.chosen()
            if not dialog.browse_requested:
                return None
        selected, _filter = QFileDialog.getOpenFileName(
            self, f"{title} için başlatma dosyası", str(root), "Oyun dosyası (*.exe *.lnk *.bat *.cmd)")
        return Path(selected) if selected else None

    def _start_target(self, title: str, target: Path):
        if target.suffix.lower() in (".lnk", ".url"):
            ok = QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))
        else:
            result = QProcess.startDetached(str(target), [], str(target.parent))
            ok = result[0] if isinstance(result, tuple) else bool(result)
        if ok:
            self.status.setText(f"Başlatıldı: {title}")
        else:
            QMessageBox.critical(
                self, "Oyun başlatılamadı",
                f"{target}\n\nDosya çalıştırılamadı. Yönet menüsünden farklı bir başlatma dosyası seçebilirsin.")

    # -- menus ---------------------------------------------------------------
    def _fill_manage_menu(self, menu: QMenu):
        menu.clear()
        key = self._current_key()
        state = self._states.get(key, {}) if key else {}
        installed = bool(state.get("installed"))
        action = menu.addAction("Yerel dosyalara göz at", lambda: self._open_install_folder(key or ""))
        action.setEnabled(installed)
        action = menu.addAction("Dosyaların bütünlüğünü doğrula", self.verify_current_game)
        action.setEnabled(bool(key) and self.verify_button.isEnabled())
        action = menu.addAction("Başlatma dosyasını seç…", self._choose_current_launch_target)
        action.setEnabled(installed)
        menu.addSeparator()
        favorite = bool(key) and key in self._favorites
        action = menu.addAction("Favorilerden çıkar" if favorite else "Favorilere ekle",
                                lambda: self._set_favorite(key, not favorite))
        action.setEnabled(bool(key))
        app_id = ((self.current_game or {}).get("media") or {}).get("steam_app_id")
        if app_id:
            menu.addAction("Mağaza sayfasını aç", lambda: self._open_steam_link("store"))
        menu.addSeparator()
        uninstall = getattr(self, "uninstall_button", None)
        action = menu.addAction("Kaldır…", self.uninstall_current_game)
        action.setEnabled(bool(key) and uninstall is not None and uninstall.isEnabled())

    def _show_context_menu(self, key: str | None, global_pos):
        if not key or not self._select_key(key):
            return
        self._sync_game_page()
        menu = QMenu(self)
        mode, text, enabled, _extra = self._action_state()
        label = {"play": "Oyna", "pause": "Duraklat", "resume": "Devam et"}.get(mode, ACTION_MENU_TEXT.get(text, text))
        primary = menu.addAction(label, self._on_action_clicked)
        primary.setEnabled(enabled)
        font = primary.font()
        font.setBold(True)
        primary.setFont(font)
        menu.addAction("Oyun sayfasını aç", lambda: self._navigate("game", key))
        menu.addSeparator()
        manage = menu.addMenu("Yönet")
        self._fill_manage_menu(manage)
        menu.exec(global_pos)

    def _fill_app_menu(self):
        menu = self.title_bar.menus["app"]
        menu.clear()
        menu.addAction("Kataloğu yenile\tF5", self.load_catalog)
        menu.addAction("Ayarlar…", self.open_settings)
        menu.addSeparator()
        menu.addAction("Çıkış", self.close)

    def _fill_view_menu(self):
        menu = self.title_bar.menus["view"]
        menu.clear()
        menu.addAction("Mağaza\tCtrl+1", lambda: self._navigate("store"))
        menu.addAction("Kütüphane\tCtrl+2", lambda: self._navigate("library"))
        menu.addAction("İndirmeler\tCtrl+3", lambda: self._navigate("downloads"))
        menu.addSeparator()
        menu.addAction("Big Picture modu\tF11", self._toggle_big_picture)
        menu.addSeparator()
        ready = menu.addAction("Yalnızca oynamaya hazır oyunlar")
        ready.setCheckable(True)
        ready.setChecked(self.sidebar.ready_toggle.isChecked())
        ready.toggled.connect(self.sidebar.ready_toggle.setChecked)
        recent = menu.addAction("Son eklenenlere göre sırala")
        recent.setCheckable(True)
        recent.setChecked(self.sidebar.recent_toggle.isChecked())
        recent.toggled.connect(self.sidebar.recent_toggle.setChecked)

    def _fill_games_menu(self):
        menu = self.title_bar.menus["games"]
        menu.clear()
        if not self.current_game:
            menu.addAction("Önce kütüphaneden bir oyun seç").setEnabled(False)
            return
        mode, text, enabled, _extra = self._action_state()
        title = str(self.current_game.get("title") or "")
        label = {"play": "Oyna", "pause": "Duraklat", "resume": "Devam et"}.get(mode, ACTION_MENU_TEXT.get(text, text))
        menu.addAction(f"{label}: {title}", self._on_action_clicked).setEnabled(enabled)
        menu.addAction("Oyun sayfasını aç", lambda: self._navigate("game", self._current_key()))
        menu.addSeparator()
        self._fill_manage_menu(menu.addMenu("Yönet"))

    def _fill_help_menu(self):
        menu = self.title_bar.menus["help"]
        menu.clear()
        menu.addAction("Katalog deposunu GitHub'da aç", self._open_repo)
        menu.addSeparator()
        menu.addAction("Drowned Launcher hakkında", self._show_about)

    def _fill_account_menu(self):
        menu = self.title_bar.account_menu
        menu.clear()
        menu.addAction(f"Katalog: {self.owner}/{self.repo} ({self.branch})").setEnabled(False)
        menu.addSeparator()
        menu.addAction("Kaynağı değiştir…", self.open_settings)
        menu.addAction("Kataloğu yenile\tF5", self.load_catalog)
        menu.addAction("GitHub'da görüntüle", self._open_repo)

    def _fill_filter_menu(self):
        menu = self.sidebar.filter_menu
        menu.clear()
        counts: dict[str, int] = {}
        for game in self.catalog.get("games") or []:
            for channel in (game.get("channels") or {}):
                counts[channel] = counts.get(channel, 0) + 1
        header = menu.addAction("KANAL")
        header.setEnabled(False)
        current = self.channel.currentText()
        for index in range(self.channel.count()):
            channel = self.channel.itemText(index)
            action = menu.addAction(f"{CHANNEL_LABELS.get(channel, channel)}  ({counts.get(channel, 0)})")
            action.setCheckable(True)
            action.setChecked(channel == current)
            action.triggered.connect(lambda _c=False, c=channel: self.channel.setCurrentText(c))
        menu.addSeparator()
        header = menu.addAction("PLATFORM")
        header.setEnabled(False)
        current = self.platform.currentText()
        for index in range(self.platform.count()):
            platform = self.platform.itemText(index)
            action = menu.addAction(platform)
            action.setCheckable(True)
            action.setChecked(platform == current)
            action.triggered.connect(lambda _c=False, p=platform: self.platform.setCurrentText(p))

    def _show_about(self):
        QMessageBox.about(
            self,
            "Drowned Launcher hakkında",
            f"Drowned Launcher {APP_VERSION}\n\n"
            "Steam istemcisi düzeninde kütüphane, mağaza ve indirmeler.\n"
            f"Katalog kaynağı: {self.owner}/{self.repo} ({self.branch})",
        )


def app_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(brand_pixmap(size))
    return icon


def _splash_pixmap() -> QPixmap:
    pixmap = QPixmap(440, 250)
    pixmap.fill(QColor(T.CHROME))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setRenderHint(QPainter.TextAntialiasing)
    gradient = QLinearGradient(0, 0, 0, pixmap.height())
    gradient.setColorAt(0.0, QColor("#1f2b3a"))
    gradient.setColorAt(1.0, QColor(T.CHROME))
    painter.fillRect(pixmap.rect(), gradient)
    painter.drawPixmap(pixmap.width() // 2 - 23, 62, brand_pixmap(46))
    painter.setPen(QColor("#ffffff"))
    painter.setFont(T.ui_font(24, 800, spacing=4.0, display=True))
    painter.drawText(QRectF(0, 118, pixmap.width(), 36), Qt.AlignCenter, "DROWNED")
    painter.setPen(QColor(T.TEXT_MUTED))
    painter.setFont(T.ui_font(12))
    painter.drawText(QRectF(0, 158, pixmap.width(), 22), Qt.AlignCenter, "Kütüphane hazırlanıyor")
    painter.fillRect(QRectF(150, 200, 140, 3), QColor("#2a2f38"))
    painter.fillRect(QRectF(150, 200, 64, 3), QColor(T.ACCENT))
    painter.end()
    return pixmap


def main():
    BASE.base.install_exception_hook()
    app = QApplication(sys.argv)
    app.setApplicationName("Drowned Launcher")
    app.setOrganizationName("Drowned")
    app.setStyle("Fusion")
    app.setFont(T.ui_font(13))
    app.setStyleSheet(V19_STYLE)
    app.setWindowIcon(app_icon())
    splash = QSplashScreen(_splash_pixmap())
    splash.show()
    app.processEvents()
    win = Launcher()
    win.show()
    splash.finish(win)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
