from __future__ import annotations

import sys

from PySide6.QtWidgets import (
    QApplication,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QWidget,
)

import app_v11 as previous
from drowned_shared.steam_artwork import SteamArtworkError, parse_steam_app_id

APP_VERSION = "0.12.0"


class Manager(previous.Manager):
    """v12 adds Steam App ID metadata directly to the automated preparation flow.

    Downloading remains URL-driven and independent from Steam. The App ID is
    metadata only: it is copied into the existing Release Manager Steam/media
    pipeline so the published catalog keeps the correct Steam association.
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle(
            f"Drowned Release Manager {APP_VERSION} • Automated Preparation + Steam Metadata"
        )

    def _automation_tab(self):
        page = super()._automation_tab()

        self.prep_steam_app_id = QLineEdit()
        self.prep_steam_app_id.setPlaceholderText("Örn. 1222140 • Steam Store / SteamDB linki de kabul edilir")
        self.prep_steam_app_id.setClearButtonEnabled(True)

        self.prep_steam_fetch_button = QPushButton("Steam bilgilerini getir")
        self.prep_steam_fetch_button.clicked.connect(self.fetch_automation_steam_metadata)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.prep_steam_app_id, 1)
        row.addWidget(self.prep_steam_fetch_button)
        row_widget = QWidget()
        row_widget.setLayout(row)

        # v11 owns the source form. Insert directly below "Oyun adı" without
        # recreating or moving any of the existing download controls.
        form = self.prep_title.parentWidget().layout()
        if isinstance(form, QFormLayout):
            form.insertRow(1, "Steam App ID", row_widget)

        return page

    def _automation_steam_id(self, *, show_error: bool = True) -> int | None:
        raw = self.prep_steam_app_id.text().strip()
        if not raw:
            return None
        try:
            return int(parse_steam_app_id(raw))
        except SteamArtworkError as exc:
            if show_error:
                QMessageBox.warning(self, "Steam App ID", str(exc))
            return None

    def _sync_steam_id_to_publish(self, *, require_valid: bool = False) -> bool:
        raw = self.prep_steam_app_id.text().strip()
        app_id = self._automation_steam_id(show_error=bool(raw))
        if raw and app_id is None:
            return False
        if require_valid and app_id is None:
            QMessageBox.warning(self, "Steam App ID", "Geçerli bir Steam App ID gir.")
            return False
        self._steam_app_id = app_id
        if hasattr(self, "steamdb_url"):
            self.steamdb_url.setText(str(app_id) if app_id else "")
        return True

    def fetch_automation_steam_metadata(self):
        if not self._sync_steam_id_to_publish(require_valid=True):
            return
        # Reuse the established Steam importer instead of maintaining a second
        # metadata/artwork implementation in the automation page.
        self.fetch_steam_artwork()

    def _steam_artwork_done(self, result: dict):
        super()._steam_artwork_done(result)
        app_id = result.get("app_id")
        if app_id:
            self._steam_app_id = int(app_id)
            if hasattr(self, "prep_steam_app_id"):
                self.prep_steam_app_id.setText(str(app_id))
        if (
            hasattr(self, "prep_title")
            and not self.prep_title.text().strip()
            and result.get("name")
        ):
            self.prep_title.setText(str(result["name"]))

    def start_preparation(self):
        # A blank App ID is allowed for non-Steam games. If one is supplied it
        # must be valid and is persisted immediately, even if artwork fetching
        # was skipped.
        if not self._sync_steam_id_to_publish(require_valid=False):
            return
        super().start_preparation()

    def open_publish_tab(self):
        if not self._sync_steam_id_to_publish(require_valid=False):
            return
        title = self.prep_title.text().strip()
        if title:
            self.game_title.setText(title)
        super().open_publish_tab()

    def reset_for_new_game(self):
        # Remove any temporary Steam artwork belonging to the previous game,
        # then let v11 clear all preparation/publish state.
        try:
            self._cleanup_steam_temp(reset_previews=False)
        except Exception:
            pass
        super().reset_for_new_game()
        if hasattr(self, "prep_steam_app_id"):
            self.prep_steam_app_id.clear()
        if hasattr(self, "steamdb_url"):
            self.steamdb_url.clear()
        if hasattr(self, "steam_status"):
            self.steam_status.setText("SteamDB linki / App ID girilmedi.")
        self._steam_app_id = None


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Drowned Release Manager")
    app.setOrganizationName("Drowned")
    app.setStyle("Fusion")

    style_module = previous
    visited = set()
    while style_module and id(style_module) not in visited:
        visited.add(id(style_module))
        if hasattr(style_module, "MODERN_STYLE"):
            app.setStyleSheet(style_module.MODERN_STYLE)
            break
        style_module = getattr(style_module, "previous", None)

    win = Manager()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
