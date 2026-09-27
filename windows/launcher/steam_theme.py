"""Steam desktop-client look for Drowned Launcher v0.19.

Every colour in this module was sampled from screenshots of the real Steam
client: the 2023 desktop library (game page, sidebar, top chrome, bottom
bar), the 2021+ downloads page and the store navigation bar. Qt has no
official Steam component set, so the widgets built on top of this module are
an approximation drawn with Qt style sheets and QPainter, not Valve assets.

Icons come from the Windows system icon font (Segoe Fluent Icons on Windows
11, Segoe MDL2 Assets on Windows 10) instead of hand-drawn paths.
"""

from __future__ import annotations

import sys
from functools import lru_cache

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QIcon, QPainter, QPixmap

# ---------------------------------------------------------------------------
# Palette (sampled, see module docstring)
# ---------------------------------------------------------------------------
CHROME = "#171d25"            # menu row, nav row, bottom bar
CHROME_BOX = "#292d38"        # boxed buttons in the top-right cluster
CHROME_TEXT = "#8f949c"       # "Steam  View  Friends  Games  Help"
NAV_TEXT = "#dcdedf"          # STORE / COMMUNITY
NAV_ACTIVE = "#64a6fc"        # LIBRARY (active tab + underline)
ACCOUNT_BLUE = "#7caff4"

SIDEBAR = "#24272e"
SIDEBAR_TOP = "#1d1f24"
SIDEBAR_CONTROL = "#2a2c32"
GROUP_HEADER = "#2a2e39"
ROW_TEXT = "#dfe3ea"          # installed game in the left list
ROW_TEXT_DIM = "#8b919d"      # not installed
ROW_SELECTED = "#444e69"
ROW_HOVER = "#30343d"
STATUS_BLUE = "#72acec"       # "Melatonin - Update Queued"
STATUS_BLUE_LIGHT = "#9ecef6"

PAGE_TOP = "#2b2e39"
PAGE_BOTTOM = "#1c1e24"
PAGE_BASE = "#1d1f24"
PANEL = "#1b1d22"
PANEL_BORDER = "#131519"
SECTION_TEXT = "#a2a7ad"      # "POST-GAME SUMMARY"
TEXT = "#dcdedf"
TEXT_MUTED = "#8b929a"
TEXT_FAINT = "#5d6270"
STAT_LABEL = "#b7bcc2"

ACCENT = "#1a9fff"            # progress fill, links, focus
PLAY_LEFT = "#89c330"         # PLAY gradient, sampled left -> right
PLAY_RIGHT = "#71af4a"
INSTALL_LEFT = "#35a3f5"
INSTALL_RIGHT = "#1f5fd0"
DANGER = "#c24444"

DL_HEADER = "#0c101c"
DL_GRAPH = "#071a2c"
DL_ROW = "#181c24"
DL_TRACK = "#3c444c"
DL_PAUSE = "#1488ec"

STORE_BG = "#1b2838"
STORE_TEXT = "#c7d5e0"
STORE_MUTED = "#8f98a0"
STORE_FOCUS_LEFT = "#c6e6f8"  # hovered tab row / preview panel
STORE_FOCUS_RIGHT = "#95bbcd"
STORE_FOCUS_TEXT = "#10161b"

# ---------------------------------------------------------------------------
# Fonts
# ---------------------------------------------------------------------------
TEXT_FAMILIES = ["Segoe UI Variable Text", "Segoe UI Variable", "Segoe UI", "Arial"]
DISPLAY_FAMILIES = ["Segoe UI Variable Display", "Segoe UI Variable", "Segoe UI", "Arial"]
ICON_FAMILIES = ["Segoe Fluent Icons", "Segoe MDL2 Assets"]

_WEIGHTS = {
    300: QFont.Weight.Light,
    400: QFont.Weight.Normal,
    500: QFont.Weight.Medium,
    600: QFont.Weight.DemiBold,
    700: QFont.Weight.Bold,
    800: QFont.Weight.ExtraBold,
}


def ui_font(px: float, weight: int = 400, *, spacing: float = 0.0, display: bool = False) -> QFont:
    """A text font at an exact pixel size. Letter spacing lives here because
    Qt style sheets have no letter-spacing property."""
    font = QFont()
    font.setFamilies(DISPLAY_FAMILIES if display else TEXT_FAMILIES)
    font.setPixelSize(max(1, round(px)))
    font.setWeight(_WEIGHTS.get(weight, QFont.Weight.Normal))
    if spacing:
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
    return font


def icon_font(px: float) -> QFont:
    font = QFont()
    font.setFamilies(ICON_FAMILIES)
    font.setPixelSize(max(1, round(px)))
    return font


class G:
    """Segoe Fluent Icons / MDL2 code points used by the UI."""

    HOME = "\uE80F"
    GRID = "\uF0E2"
    DOWNLOAD = "\uE896"
    PLAY = "\uE768"
    PLAY_SOLID = "\uF5B0"
    PAUSE = "\uE769"
    PAUSE_SOLID = "\uF8AE"
    CANCEL = "\uE711"
    MINIMIZE = "\uE921"
    MAXIMIZE = "\uE922"
    RESTORE = "\uE923"
    CLOSE = "\uE8BB"
    BACK = "\uE72B"
    FORWARD = "\uE72A"
    REFRESH = "\uE72C"
    SETTINGS = "\uE713"
    SEARCH = "\uE721"
    CLOCK = "\uE823"
    FOLDER = "\uE838"
    INFO = "\uE946"
    STAR = "\uE734"
    STAR_FILLED = "\uE735"
    CHEVRON_DOWN = "\uE70D"
    CHEVRON_LEFT = "\uE76B"
    CHEVRON_RIGHT = "\uE76C"
    ADD = "\uE710"
    GLOBE = "\uE774"
    GAME = "\uE7FC"
    CLOUD = "\uE753"
    CHECK = "\uE73E"
    DELETE = "\uE74D"
    DRIVE = "\uEDA2"
    TAG = "\uE8EC"
    CALENDAR = "\uE787"
    NETWORK = "\uE968"
    SYNC = "\uE895"
    WARNING = "\uE7BA"
    MORE = "\uE712"
    LIBRARY = "\uE8F1"
    STORE = "\uE719"
    MONITOR = "\uE7F4"
    LINK = "\uE71B"
    PACKAGE = "\uE7B8"
    SPEED = "\uEC4A"


def _device_ratio() -> float:
    screen = QGuiApplication.primaryScreen()
    return float(screen.devicePixelRatio()) if screen is not None else 1.0


def glyph_pixmap(glyph: str, px: float, color: str | QColor, box: int | None = None) -> QPixmap:
    ratio = _device_ratio()
    size = box or int(round(px * 1.35))
    pixmap = QPixmap(int(size * ratio), int(size * ratio))
    pixmap.setDevicePixelRatio(ratio)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setRenderHint(QPainter.TextAntialiasing)
    painter.setFont(icon_font(px))
    painter.setPen(QColor(color))
    painter.drawText(QRectF(0, 0, size, size), Qt.AlignCenter, glyph)
    painter.end()
    return pixmap


def glyph_icon(glyph: str, px: float, color: str, active: str | None = None, disabled: str | None = None) -> QIcon:
    icon = QIcon()
    icon.addPixmap(glyph_pixmap(glyph, px, color), QIcon.Normal, QIcon.Off)
    icon.addPixmap(glyph_pixmap(glyph, px, active or color), QIcon.Active, QIcon.Off)
    icon.addPixmap(glyph_pixmap(glyph, px, active or color), QIcon.Normal, QIcon.On)
    icon.addPixmap(glyph_pixmap(glyph, px, disabled or "#565c64"), QIcon.Disabled, QIcon.Off)
    return icon


@lru_cache(maxsize=1)
def animations_enabled() -> bool:
    """Honour Windows' "Show animations in Windows" accessibility switch
    (the desktop equivalent of prefers-reduced-motion)."""
    if sys.platform != "win32":
        return True
    try:
        import ctypes

        value = ctypes.c_int(1)
        spi_get_client_area_animation = 0x1042
        if ctypes.windll.user32.SystemParametersInfoW(
            spi_get_client_area_animation, 0, ctypes.byref(value), 0
        ):
            return bool(value.value)
    except Exception:
        pass
    return True


def mix(a: str | QColor, b: str | QColor, t: float) -> QColor:
    ca, cb = QColor(a), QColor(b)
    t = max(0.0, min(1.0, t))
    return QColor(
        round(ca.red() + (cb.red() - ca.red()) * t),
        round(ca.green() + (cb.green() - ca.green()) * t),
        round(ca.blue() + (cb.blue() - ca.blue()) * t),
        round(ca.alpha() + (cb.alpha() - ca.alpha()) * t),
    )


# ---------------------------------------------------------------------------
# Style sheet. Object names are grouped by surface. Painted widgets (nav
# tabs, capsules, the library list, hero, graphs) take their colours from
# the constants above instead.
# ---------------------------------------------------------------------------
V19_STYLE = r"""
/* The base font comes from QApplication.setFont(ui_font(13)); a font rule on
   QWidget here would override every setFont() call made by painted labels. */
* { outline: 0; }
QWidget { color: #dcdedf; }
QMainWindow { background: #171d25; }
QWidget#steamRoot { background: #171d25; }
QToolTip {
    background: #3d4450; color: #dcdedf; border: 1px solid #171a21;
    padding: 5px 8px; font-size: 12px;
}

/* ---- menus: Steam context menus are slate with an inverted hover row ---- */
QMenu {
    background: #3d4450; color: #dcdedf; border: 1px solid #252a32;
    padding: 4px 0; font-size: 13px;
}
QMenu::item { padding: 7px 34px 7px 16px; background: transparent; }
QMenu::item:selected { background: #dcdedf; color: #171d25; }
QMenu::item:disabled { color: #7c8591; }
QMenu::separator { height: 1px; background: #2c323b; margin: 4px 10px; }
QMenu::icon { padding-left: 10px; }

/* ---- scroll bars ---- */
QScrollBar:vertical { background: transparent; width: 12px; margin: 0; }
QScrollBar::handle:vertical {
    background: rgba(255, 255, 255, 38); min-height: 40px; border-radius: 3px; margin: 2px 3px;
}
QScrollBar::handle:vertical:hover { background: rgba(255, 255, 255, 72); }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QScrollBar:horizontal { background: transparent; height: 12px; margin: 0; }
QScrollBar::handle:horizontal {
    background: rgba(255, 255, 255, 38); min-width: 40px; border-radius: 3px; margin: 3px 2px;
}
QScrollBar::handle:horizontal:hover { background: rgba(255, 255, 255, 72); }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }
QScrollArea { background: transparent; border: 0; }
QScrollArea > QWidget > QWidget { background: transparent; }

/* ---- generic controls ---- */
QLineEdit {
    background: #2a2c32; color: #dcdedf; border: 1px solid transparent; border-radius: 3px;
    padding: 6px 8px; selection-background-color: #3d6c93;
}
QLineEdit:hover { background: #30333a; }
QLineEdit:focus { border: 1px solid rgba(100, 166, 252, 150); background: #30333a; }
QComboBox {
    background: #3d4450; color: #dcdedf; border: 0; border-radius: 2px;
    padding: 5px 10px; min-height: 18px;
}
QComboBox:hover { background: #4b5361; }
QComboBox::drop-down { border: 0; width: 18px; }
QComboBox QAbstractItemView {
    background: #3d4450; color: #dcdedf; border: 1px solid #252a32;
    selection-background-color: #dcdedf; selection-color: #171d25; padding: 2px;
}
QPushButton {
    background: #3d4450; color: #dcdedf; border: 0; border-radius: 2px;
    padding: 7px 14px; font-weight: 600;
}
QPushButton:hover { background: #4b5361; color: #ffffff; }
QPushButton:pressed { background: #353b46; }
QPushButton:disabled { background: #2a2e36; color: #5b616b; }
QCheckBox { color: #dcdedf; spacing: 10px; }
QCheckBox::indicator {
    width: 16px; height: 16px; border-radius: 2px; background: #1b1d22; border: 1px solid #4a515c;
}
QCheckBox::indicator:hover { border-color: #64a6fc; }
QCheckBox::indicator:checked { background: #1a9fff; border-color: #1a9fff; }
QCheckBox::indicator:disabled { background: #25272c; border-color: #33373f; }
QCheckBox:disabled { color: #6b717b; }
QProgressBar {
    background: #2a2f38; border: 0; border-radius: 0; min-height: 4px; max-height: 4px;
    color: transparent; text-align: center;
}
QProgressBar::chunk { background: #1a9fff; }
QPlainTextEdit {
    background: #14161a; color: #8b929a; border: 1px solid #0e1013; border-radius: 2px;
    padding: 8px 10px; font-family: "Cascadia Mono", Consolas, monospace; font-size: 11px;
    selection-background-color: #3d6c93;
}
QSplitter::handle { background: #101216; }
QDialog, QMessageBox, QInputDialog { background: #1f2227; }
QMessageBox QLabel, QDialog QLabel { color: #dcdedf; }
QFormLayout QLabel { color: #8b929a; }

/* ---- window chrome ---- */
QFrame#steamChrome { background: #171d25; }
QPushButton#chromeMenu {
    background: transparent; color: #8f949c; border: 0; border-radius: 2px;
    padding: 2px 9px; font-weight: 400; font-size: 13px;
}
QPushButton#chromeMenu:hover, QPushButton#chromeMenu:open { color: #dcdedf; background: rgba(255, 255, 255, 14); }
QPushButton#chromeMenu::menu-indicator { image: none; width: 0; }
QPushButton#chromeBox {
    background: #292d38; border: 0; border-radius: 2px; padding: 0;
    min-width: 34px; max-width: 34px; min-height: 24px; max-height: 24px;
}
QPushButton#chromeBox:hover { background: #3d4450; }
QPushButton#chromeFlat {
    background: transparent; border: 0; border-radius: 2px; padding: 0;
    min-width: 30px; max-width: 30px; min-height: 26px; max-height: 26px;
}
QPushButton#chromeFlat:hover { background: rgba(255, 255, 255, 18); }
QPushButton#chromeFlat:disabled { background: transparent; }
QPushButton#windowButton, QPushButton#windowClose {
    background: transparent; border: 0; border-radius: 0; padding: 0;
    min-width: 42px; max-width: 42px; min-height: 30px; max-height: 30px;
}
QPushButton#windowButton:hover { background: rgba(255, 255, 255, 22); }
QPushButton#windowClose:hover { background: #c42b1c; }
QPushButton#accountPill {
    background: #292d38; border: 0; border-radius: 2px; padding: 0 10px 0 4px;
    min-height: 24px; max-height: 24px; text-align: left;
}
QPushButton#accountPill:hover { background: #3d4450; }
QPushButton#accountPill::menu-indicator { image: none; width: 0; }

/* ---- library sidebar ---- */
QFrame#steamSidebar { background: #24272e; }
QFrame#sidebarTop { background: #1d1f24; }
QPushButton#sidebarHome {
    background: #2a2c32; color: #dcdedf; border: 0; border-radius: 2px;
    text-align: left; padding: 0 12px; min-height: 34px; max-height: 34px;
    font-size: 12px; font-weight: 700;
}
QPushButton#sidebarHome:hover { background: #3d4450; color: #ffffff; }
QPushButton#sidebarHome[active="true"] { background: #3d4450; color: #ffffff; }
QPushButton#sidebarIcon {
    background: #2a2c32; border: 0; border-radius: 2px; padding: 0;
    min-width: 34px; max-width: 34px; min-height: 34px; max-height: 34px;
}
QPushButton#sidebarIcon:hover { background: #3d4450; }
QPushButton#sidebarToggle {
    background: transparent; border: 0; border-radius: 2px; padding: 0;
    min-width: 30px; max-width: 30px; min-height: 30px; max-height: 30px;
}
QPushButton#sidebarToggle:hover { background: rgba(255, 255, 255, 16); }
QPushButton#sidebarToggle:checked { background: rgba(100, 166, 252, 40); }
QPushButton#sidebarDropdown {
    background: #2a2c32; color: #dcdedf; border: 0; border-radius: 2px;
    text-align: left; padding: 0 10px; min-height: 30px; max-height: 30px;
    font-size: 12px; font-weight: 700;
}
QPushButton#sidebarDropdown:hover, QPushButton#sidebarDropdown:open { background: #3d4450; }
QPushButton#sidebarDropdown::menu-indicator { image: none; width: 0; }
QLineEdit#sidebarSearch { background: #2a2c32; border-radius: 2px; padding: 6px 8px 6px 2px; }
QLineEdit#sidebarSearch:focus { background: #30333a; }

/* ---- sections, panels, text ---- */
QFrame#steamPanel {
    background: rgba(0, 0, 0, 70); border: 1px solid rgba(0, 0, 0, 110); border-radius: 3px;
}
QLabel#panelKey { color: #8b929a; font-size: 12px; }
QLabel#panelValue { color: #dcdedf; font-size: 12px; }
QLabel#muted { color: #8b929a; }
QLabel#faint { color: #5d6270; }
QLabel#gameDescription { color: #b8bcbf; font-size: 14px; }
QPushButton#linkButton {
    background: transparent; color: #64a6fc; border: 0; padding: 2px 0; font-weight: 600;
}
QPushButton#linkButton:hover { color: #ffffff; }
QPushButton#linkButton:disabled { color: #4d5460; }

/* ---- game page ---- */
QPushButton#subNavLink {
    background: transparent; color: #8b929a; border: 0; border-radius: 0;
    padding: 0 18px; min-height: 42px; font-size: 13px; font-weight: 400;
}
QPushButton#subNavLink:hover { color: #ffffff; background: rgba(255, 255, 255, 10); }
QPushButton#subNavLink:disabled { color: #50565f; background: transparent; }
QPushButton#squareButton {
    background: rgba(255, 255, 255, 22); border: 0; border-radius: 2px; padding: 0;
    min-width: 36px; max-width: 36px; min-height: 36px; max-height: 36px;
}
QPushButton#squareButton:hover { background: rgba(255, 255, 255, 48); }
QPushButton#squareButton::menu-indicator { image: none; width: 0; }
QPushButton#squareButton:checked { background: rgba(255, 255, 255, 48); }
QPushButton#inlineCancel {
    background: transparent; color: #8b929a; border: 0; padding: 2px 6px; font-weight: 600; font-size: 12px;
}
QPushButton#inlineCancel:hover { color: #ffffff; }
QLabel#statLabel { color: #b7bcc2; font-size: 11px; font-weight: 700; }
QLabel#statValue { color: #8b929a; font-size: 12px; }
QLabel#dlCaption { color: #dcdedf; font-size: 11px; font-weight: 700; }
QLabel#dlValue { color: #9ecef6; font-size: 12px; font-weight: 600; }
QLabel#blockedNote { color: #8b929a; font-size: 12px; }
QProgressBar#actionBar { min-height: 5px; max-height: 5px; background: rgba(255, 255, 255, 30); }

/* optional packages panel from app_v12, re-hosted in the game page */
QWidget#dlcHost QFrame#panel {
    background: rgba(0, 0, 0, 70); border: 1px solid rgba(0, 0, 0, 110); border-radius: 3px;
}
QWidget#dlcHost QLabel#panelTitle { color: #a2a7ad; font-size: 12px; font-weight: 700; }
QWidget#dlcHost QFrame#infoCard { background: rgba(255, 255, 255, 8); border-radius: 2px; }

/* ---- downloads page ---- */
QFrame#dlActiveRow { background: #181c24; }
QLabel#dlTitle { color: #ffffff; font-size: 15px; font-weight: 700; }
QLabel#dlMuted { color: #8b929a; font-size: 12px; }
QLabel#dlState { color: #dcdedf; font-size: 11px; font-weight: 700; }
QLabel#dlPercent { color: #dcdedf; font-size: 11px; font-weight: 700; }
QLabel#dlStatValue { color: #ffffff; font-size: 14px; font-weight: 700; }
QLabel#dlStatLabel { color: #8e949c; font-size: 10px; font-weight: 700; }
QLabel#dlHeaderTitle { color: #ffffff; font-size: 15px; font-weight: 800; }
QLabel#dlLegend { color: #8e949c; font-size: 10px; font-weight: 700; }
QLabel#dlSection { color: #ffffff; font-size: 15px; font-weight: 400; }
QLabel#dlSectionCount { color: #8b909a; font-size: 15px; }
QProgressBar#dlBar { min-height: 6px; max-height: 6px; background: #3c444c; }
QProgressBar#dlRowBar { min-height: 4px; max-height: 4px; background: #283038; }
QProgressBar#dlRowBar::chunk { background: #686c78; }
QPushButton#dlPause {
    background: #1488ec; border: 0; border-radius: 2px; padding: 0; color: #ffffff;
    min-width: 34px; max-width: 34px; min-height: 34px; max-height: 34px;
    font-family: "Segoe Fluent Icons", "Segoe MDL2 Assets"; font-size: 14px;
}
QPushButton#dlPause:hover { background: #2a9af5; }
QPushButton#dlIcon {
    background: #3c404c; border: 0; border-radius: 2px; padding: 0;
    min-width: 30px; max-width: 30px; min-height: 30px; max-height: 30px;
}
QPushButton#dlIcon:hover { background: #4b5160; }
QPushButton#dlPlay {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #89c330, stop:1 #71af4a);
    color: #ffffff; border: 0; border-radius: 2px; padding: 0 14px;
    min-height: 30px; max-height: 30px; font-size: 12px; font-weight: 700;
}
QPushButton#dlPlay:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #9ad33e, stop:1 #7fbd57);
}
QFrame#dlRow { background: rgba(0, 0, 0, 38); border-radius: 2px; }
QFrame#dlRow:hover { background: rgba(255, 255, 255, 10); }

/* ---- bottom bar ---- */
QFrame#steamBottomBar { background: #171d25; border-top: 1px solid #0f1318; }
QPushButton#bottomFlat {
    background: transparent; color: #8d919a; border: 0; border-radius: 0;
    padding: 0 12px; min-height: 38px; font-size: 13px; font-weight: 400;
}
QPushButton#bottomFlat:hover { color: #dcdedf; background: rgba(255, 255, 255, 8); }
QLabel#bottomStatus { color: #8d919a; font-size: 12px; }
QLabel#bottomPercent { color: #dcdedf; font-size: 12px; font-weight: 700; }
QLabel#connectionState { color: #8d919a; font-size: 12px; padding: 0 12px; }
QLabel#connectionState[state="error"] { color: #e0785f; }
QLabel#connectionState[state="cache"] { color: #d7b75a; }
QLabel#connectionState[state="busy"] { color: #9ecef6; }
QProgressBar#bottomProgress { min-width: 180px; max-width: 320px; }
QFrame#steamBottomBar QPushButton#pauseButton, QFrame#steamBottomBar QPushButton#danger {
    background: #2a2f38; color: #dcdedf; border: 0; border-radius: 2px;
    padding: 3px 10px; min-height: 20px; font-size: 11px; font-weight: 700;
}
QFrame#steamBottomBar QPushButton#pauseButton:hover, QFrame#steamBottomBar QPushButton#danger:hover {
    background: #3d4450; color: #ffffff;
}

/* ---- store (Steam keeps the classic navy palette there) ---- */
QPushButton#storeNavLink {
    background: transparent; color: #e5e5e5; border: 0; border-radius: 0;
    padding: 0 16px; min-height: 36px; font-size: 13px; font-weight: 400;
}
QPushButton#storeNavLink:hover { color: #ffffff; background: rgba(255, 255, 255, 26); }
QLineEdit#storeSearch {
    background: #316282; color: #ffffff; border: 1px solid rgba(0, 0, 0, 80);
    border-radius: 3px; padding: 5px 10px;
}
QLineEdit#storeSearch:focus { background: #3a7197; border-color: rgba(0, 0, 0, 120); }
QPushButton#storeMore {
    background: rgba(103, 193, 245, 50); color: #67c1f5; border: 0; border-radius: 2px;
    padding: 6px 16px; font-weight: 400;
}
QPushButton#storeMore:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #66c0f4, stop:1 #417a9b);
    color: #ffffff;
}
QPushButton#storeCta {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #75b022, stop:1 #588a1b);
    color: #d2efa9; border: 0; border-radius: 2px; padding: 7px 16px; font-weight: 400; font-size: 14px;
}
QPushButton#storeCta:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #8ed629, stop:1 #6aa621);
    color: #ffffff;
}

/* ---- Big Picture (app_v10 widgets, Steam Deck-style skin) ---- */
QWidget#bigPictureRoot {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1e2330, stop:0.55 #14171e, stop:1 #0e1015);
}
QFrame#bpHeader { background: transparent; }
QLineEdit#bpSearch {
    background: #23262e; color: #ffffff; border: 2px solid transparent; border-radius: 8px;
    padding: 10px 16px; font-size: 16px; min-height: 22px;
}
QLineEdit#bpSearch:focus { border-color: #1a9fff; background: #2a2e37; }
QLabel#bpClock { color: #ffffff; font-size: 18px; font-weight: 600; }
QLabel#bpShoulder {
    color: #dcdedf; background: #3d4450; border: 0; border-radius: 4px;
    padding: 4px 9px; font-size: 12px; font-weight: 700;
}
QLabel#bpTab {
    color: #8b929a; background: transparent; border-radius: 18px;
    padding: 9px 20px; font-size: 15px; font-weight: 700;
}
QLabel#bpTab:hover { color: #ffffff; }
QLabel#bpTabActive {
    color: #ffffff; background: #3d4450; border-radius: 18px;
    padding: 9px 20px; font-size: 15px; font-weight: 700;
}
QFrame#bpFooter { background: #0e1015; border-top: 1px solid #23262e; }
QLabel#bpSteamPill {
    color: #0e1015; background: #dcdedf; border-radius: 10px;
    padding: 3px 12px; font-size: 12px; font-weight: 800;
}
QLabel#bpFooterText { color: #dcdedf; font-size: 12px; font-weight: 700; }
QLabel#bpGlyph {
    color: #0e1015; background: #dcdedf; border-radius: 10px; font-size: 11px; font-weight: 800;
    min-width: 20px; max-width: 20px; min-height: 20px; max-height: 20px;
}
QLabel#bpHint { color: #b7bcc2; font-size: 12px; font-weight: 700; }
QLabel#bpBigTitle { color: #ffffff; font-size: 32px; font-weight: 700; }
QLabel#bpMeta { color: #8b929a; font-size: 14px; }
QLabel#bpSectionTitle { color: #ffffff; font-size: 20px; font-weight: 700; }
QLabel#bigMetric { color: #ffffff; font-size: 18px; font-weight: 700; }
QLabel#statName { color: #8b929a; font-size: 10px; font-weight: 700; }
QScrollArea#bpGrid { background: transparent; border: 0; }
QWidget#gameGridContent { background: transparent; }
QWidget#bigPictureRoot QPushButton {
    background: #3d4450; color: #dcdedf; border: 2px solid transparent; border-radius: 6px;
    padding: 10px 24px; font-size: 15px; font-weight: 700; min-height: 24px;
}
QWidget#bigPictureRoot QPushButton:hover { background: #4b5361; color: #ffffff; }
QWidget#bigPictureRoot QPushButton:focus { border-color: #ffffff; background: #4b5361; color: #ffffff; }
QWidget#bigPictureRoot QPushButton#install {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #89c330, stop:1 #71af4a); color: #ffffff;
}
QWidget#bigPictureRoot QPushButton#install:focus { border-color: #ffffff; }
QWidget#bigPictureRoot QPushButton#pauseButton { background: #1a9fff; color: #ffffff; }
QWidget#bigPictureRoot QPushButton#danger { background: #5a2a2e; color: #ffd9dc; }
QWidget#bigPictureRoot QPushButton:disabled { background: #25282f; color: #5b616b; }
QWidget#bigPictureRoot QPushButton#linkButton {
    background: transparent; color: #64a6fc; border: 0; padding: 4px 0; font-size: 14px;
}
QWidget#bigPictureRoot QProgressBar#fatBar {
    min-height: 8px; max-height: 8px; background: #2a2f38; border-radius: 4px;
}
QWidget#bigPictureRoot QProgressBar#fatBar::chunk { background: #1a9fff; border-radius: 4px; }
"""
