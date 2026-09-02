from __future__ import annotations

import sys

from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplashScreen,
    QVBoxLayout,
    QWidget,
)

import app_v16 as previous

APP_VERSION = "0.17.0"
BASE = previous.BASE


V17_STYLE = previous.V16_STYLE + r"""
/* v17: Epic Games-style library is the default (windowed) home view, not a
   toggle-only fullscreen mode. The couch-mode Big Picture shell already had
   everything an Epic-style screen needs (search, tab strip, capsule wall,
   per-game page) - it just used to require F11 + real OS fullscreen. */
QFrame#epicTopBar {
    background:#0d0f10; border-bottom:1px solid rgba(255,255,255,20);
}
QLabel#epicBrand {
    color:#ffffff; font-size:13px; font-weight:900; letter-spacing:2px;
}
QPushButton#epicClassic {
    background:transparent; border:1px solid rgba(255,255,255,30);
    color:rgba(255,255,255,190); border-radius:14px; padding:6px 14px;
    font-size:10px; font-weight:800;
}
QPushButton#epicClassic:hover { background:rgba(255,255,255,14); color:#fff; }

QFrame#bpHeader { background:#0d0f10; border-bottom:1px solid rgba(255,255,255,18); }
QFrame#bpFooter { background:#0d0f10; border-top:1px solid rgba(255,255,255,18); }
QLineEdit#bpSearch {
    background:rgba(255,255,255,9); border:1px solid rgba(255,255,255,26);
    border-radius:18px; padding:10px 18px; font-size:12px;
}
QLabel#bpTab, QLabel#bpTabActive {
    color:rgba(255,255,255,110); font-size:10px; font-weight:850; letter-spacing:1px;
    padding:10px 22px; border-bottom:2px solid transparent;
}
QLabel#bpTab:hover { color:#fff; }
QLabel#bpTabActive { color:#fff; border-bottom-color:#ffffff; background:transparent; }
QLabel#bpShoulder { color:rgba(255,255,255,55); font-size:9px; font-weight:800; }
QWidget#bigPictureRoot { background:#121415; }
"""


class Launcher(previous.Launcher):
    """Same backend, same Big Picture shell - but presented windowed and by
    default, the way Epic Games/Steam show their library, instead of behind
    an F11 kiosk-mode toggle."""

    def __init__(self):
        super().__init__()
        QApplication.instance().setStyleSheet(V17_STYLE)
        self.setWindowTitle(f"Drowned Launcher {APP_VERSION} • Epic-style Library")
        self.resize(max(self.width(), 1500), max(self.height(), 920))
        self._wrap_epic_home()
        self._show_epic_home()

    def _wrap_epic_home(self):
        """Insert a slim top bar above the Big Picture shell so refresh,
        settings and a way back to the classic list view are still reachable
        - the couch-mode footer/header never needed them since real Big
        Picture mode was entered via a button that lived in the (now hidden)
        classic shell."""
        wrapper = QWidget()
        outer = QVBoxLayout(wrapper)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        bar = QFrame()
        bar.setObjectName("epicTopBar")
        bar_l = QHBoxLayout(bar)
        bar_l.setContentsMargins(20, 10, 20, 10)
        bar_l.setSpacing(10)
        brand = QLabel("DROWNED")
        brand.setObjectName("epicBrand")
        bar_l.addWidget(brand)
        bar_l.addStretch(1)
        classic = QPushButton("Klasik görünüm")
        classic.setObjectName("epicClassic")
        classic.clicked.connect(self._show_classic_shell)
        refresh = QPushButton("↻")
        refresh.setObjectName("railButton")
        refresh.setToolTip("Kataloğu yenile")
        refresh.clicked.connect(self.load_catalog)
        settings = QPushButton("⚙")
        settings.setObjectName("railButton")
        settings.setToolTip("Ayarlar")
        settings.clicked.connect(self.open_settings)
        bar_l.addWidget(classic)
        bar_l.addWidget(refresh)
        bar_l.addWidget(settings)
        outer.addWidget(bar)

        self.main_stack.removeWidget(self.big_picture)
        outer.addWidget(self.big_picture, 1)
        # QStackedWidget explicitly hides every non-current page, including
        # the one just removed from it. Reparenting into a plain QVBoxLayout
        # does not clear that hidden flag on its own.
        self.big_picture.show()
        self.main_stack.addWidget(wrapper)
        self._epic_home_index = self.main_stack.count() - 1

    def _show_epic_home(self):
        self._big_picture = True
        self.main_stack.setCurrentIndex(self._epic_home_index)
        self.big_picture.search.setText(self.search.text())
        self.big_picture.show_grid()
        self.render_library()
        self._sync_big_picture_game()
        self.library_grid_bp.focus_selection()

    def _show_classic_shell(self):
        self._big_picture = False
        self.main_stack.setCurrentIndex(0)
        self.library_grid.focus_selection()

    def _toggle_big_picture(self):
        """F11 now means real OS fullscreen of whatever is on screen, fully
        decoupled from which library view is showing (that choice lives in
        _show_epic_home / _show_classic_shell instead)."""
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def _exit_big_picture(self):
        """Esc: drop out of OS fullscreen first, otherwise step back from a
        Big Picture game page to the grid. Never auto-jumps to the classic
        shell - that is an explicit button now."""
        if self.isFullScreen():
            self.showNormal()
            return
        if self._big_picture and self.big_picture.on_game_page:
            self.big_picture.show_grid()
            self.library_grid_bp.focus_selection()


def main():
    BASE.base.install_exception_hook()
    app = QApplication(sys.argv)
    app.setApplicationName("Drowned Launcher")
    app.setOrganizationName("Drowned")
    app.setStyle("Fusion")
    app.setStyleSheet(V17_STYLE)
    splash = QSplashScreen(BASE._splash_pixmap())
    splash.show()
    app.processEvents()
    win = Launcher()
    win.show()
    splash.finish(win)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
