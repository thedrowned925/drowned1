from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QPushButton

import app_v10 as previous
from library_navigation import GameGridView, GameListView
from xinput_v2 import GamepadPoller

APP_VERSION = "0.11.0"

# Keep the app_v10 visual composition exactly as designed, but replace the two
# UI input adapters before its _build_ui/_wire_runtime methods run.
previous.GameGridView = GameGridView
previous.GameListView = GameListView
previous.GamepadPoller = GamepadPoller


class Launcher(previous.Launcher):
    """app_v10 presentation with corrected Big Picture UI navigation only."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Drowned Launcher {APP_VERSION}")

        # app_v10's legacy tileActivated connection remains harmless: the new
        # views intentionally do not emit it. Selection and activation are now
        # separate, explicit UI events.
        for view in (self.library_grid, self.library_grid_bp):
            view.selectionChanged.connect(self._select_source_row)
        self.library_grid.gameActivated.connect(self._select_source_row)
        self.library_grid_bp.gameActivated.connect(self._open_big_picture_game)

        # A mouse user should never be trapped on the couch game page. This is
        # intentionally a small overlay-style link and does not change the
        # existing page layout or action set.
        self.bp_back_button = QPushButton("← KÜTÜPHANE")
        self.bp_back_button.setObjectName("linkButton")
        self.bp_back_button.setCursor(Qt.PointingHandCursor)
        self.bp_back_button.clicked.connect(self._back_to_big_picture_grid)
        hero_layout = self.big_picture.game_hero.layout()
        if hero_layout is not None:
            hero_layout.insertWidget(0, self.bp_back_button, 0, Qt.AlignLeft)

        # Esc now behaves like B: first leave the game page, then leave Big
        # Picture. Previously it always tore down Big Picture immediately.
        try:
            self._esc_shortcut.activated.disconnect()
        except (RuntimeError, TypeError):
            pass
        self._esc_shortcut.activated.connect(self._handle_escape)

        # Re-apply source row IDs after the initial view construction.
        self._restore_source_rows()

    # -- source-row mapping -------------------------------------------------

    def _source_row_map(self) -> dict[str, int]:
        mapping: dict[str, int] = {}
        for row in range(self.library.count()):
            payload = self.library.item(row).data(Qt.UserRole)
            if not payload:
                continue
            game, channel = payload
            mapping[self._key(game, channel)] = row
        return mapping

    def _restore_source_rows(self) -> None:
        if not hasattr(self, "library_grid"):
            return
        mapping = self._source_row_map()
        for view in (self.library_grid, self.library_grid_bp):
            view.set_source_rows(mapping)
            view.set_current_row(self.library.currentRow())

    def render_library(self):
        super().render_library()
        self._restore_source_rows()

    def _select_source_row(self, row: int) -> None:
        if row < 0 or row >= self.library.count():
            return
        if self.library.currentRow() != row:
            self.library.setCurrentRow(row)
        else:
            # Selecting the already-current capsule still needs the Big
            # Picture mirror to be current before an activation opens it.
            self._sync_big_picture_game()

    # -- Big Picture page transitions --------------------------------------

    def _open_big_picture_game(self, row: int) -> None:
        if not self._big_picture:
            self._select_source_row(row)
            return
        self._select_source_row(row)
        if not self.current_game:
            return
        self._sync_big_picture_game()
        self.big_picture.show_game_page()

    def _back_to_big_picture_grid(self) -> None:
        if not self._big_picture:
            return
        self.big_picture.show_grid()
        if self.big_picture.tab_index != previous.BigPictureView.TAB_DOWNLOADS:
            self.library_grid_bp.focus_selection()

    def _handle_escape(self) -> None:
        if not self._big_picture:
            return
        if self.big_picture.on_game_page:
            self._back_to_big_picture_grid()
        else:
            self._exit_big_picture()

    def _enter_big_picture(self):
        # Ensure there is always an actionable selection before the full-screen
        # shell receives A/Enter.
        if self.library.currentRow() < 0 and self.library.count() > 0:
            self.library.setCurrentRow(0)
        super()._enter_big_picture()
        self._restore_source_rows()
        if self.big_picture.tab_index != previous.BigPictureView.TAB_DOWNLOADS:
            if not self.library_grid_bp.contains_source_row(self.library.currentRow()):
                first = self.library_grid_bp.first_source_row()
                if first is not None:
                    self.library.setCurrentRow(first)
            self.library_grid_bp.focus_selection()

    def _on_bp_tab_changed(self, index: int):
        super()._on_bp_tab_changed(index)
        self._restore_source_rows()
        if index == previous.BigPictureView.TAB_DOWNLOADS:
            return
        if not self.library_grid_bp.contains_source_row(self.library.currentRow()):
            first = self.library_grid_bp.first_source_row()
            if first is not None:
                self.library.setCurrentRow(first)
        if self._big_picture:
            self.library_grid_bp.focus_selection()

    def artwork_loaded(self, token: str, raw: dict):
        # Keep app_v10's exact artwork pipeline, then refresh the couch hero
        # after the async hero image actually arrives.
        super().artwork_loaded(token, raw)
        self._sync_big_picture_game()

    # -- controller navigation ---------------------------------------------

    def _cycle_big_picture_tab(self, delta: int) -> None:
        if self.big_picture.on_game_page:
            self._back_to_big_picture_grid()
        self.big_picture.cycle_tab(delta)
        if self.big_picture.tab_index != previous.BigPictureView.TAB_DOWNLOADS:
            self._restore_source_rows()
            if not self.library_grid_bp.contains_source_row(self.library.currentRow()):
                first = self.library_grid_bp.first_source_row()
                if first is not None:
                    self.library.setCurrentRow(first)
            self.library_grid_bp.focus_selection()

    def _on_gamepad_action(self, action: str):
        if action == "toggle_big_picture":
            self._toggle_big_picture()
            return

        if not self._big_picture:
            # Desktop controller behaviour from app_v10 remains intact. The
            # differentiated shoulders both map to its existing view switch.
            if action in ("previous_tab", "next_tab"):
                super()._on_gamepad_action("switch_view")
            else:
                super()._on_gamepad_action(action)
            return

        if action == "previous_tab":
            self._cycle_big_picture_tab(-1)
            return
        if action == "next_tab":
            self._cycle_big_picture_tab(1)
            return

        if self.big_picture.on_game_page:
            if action == "back":
                self._back_to_big_picture_grid()
            elif action == "activate":
                self.big_picture.activate_focused_action()
            elif action in ("left", "up"):
                self.big_picture.move_action_focus(-1)
            elif action in ("right", "down"):
                self.big_picture.move_action_focus(1)
            return

        # Downloads is an informational page at the moment. Do not let A or
        # the D-pad secretly operate the hidden game grid behind it.
        if self.big_picture.tab_index == previous.BigPictureView.TAB_DOWNLOADS:
            if action == "back":
                self._exit_big_picture()
            return

        if action == "back":
            self._exit_big_picture()
            return
        if action == "activate":
            self.library_grid_bp.activate_current()
            return
        if action in ("left", "right", "up", "down"):
            self.library_grid_bp.move_direction(action)


def main():
    previous.base.install_exception_hook()
    app = QApplication(sys.argv)
    app.setApplicationName("Drowned Launcher")
    app.setOrganizationName("Drowned")
    app.setStyle("Fusion")
    app.setStyleSheet(previous.STEAM_STYLE)

    splash = previous.QSplashScreen(previous._splash_pixmap())
    splash.show()
    app.processEvents()

    win = Launcher()
    win.show()
    splash.finish(win)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
