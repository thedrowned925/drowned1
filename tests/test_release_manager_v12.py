from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
V12 = ROOT / "windows" / "release-manager" / "app_v12.py"


class ReleaseManagerV12Tests(unittest.TestCase):
    def test_automation_page_has_steam_app_id_field(self):
        source = V12.read_text(encoding="utf-8")
        self.assertIn("self.prep_steam_app_id = QLineEdit()", source)
        self.assertIn('form.insertRow(1, "Steam App ID", row_widget)', source)
        self.assertIn("Steam bilgilerini getir", source)

    def test_steam_id_is_synced_into_existing_publish_pipeline(self):
        source = V12.read_text(encoding="utf-8")
        self.assertIn("self._steam_app_id = app_id", source)
        self.assertIn("self.steamdb_url.setText", source)
        self.assertIn("self.game_title.setText(title)", source)

    def test_new_game_clears_steam_state(self):
        source = V12.read_text(encoding="utf-8")
        self.assertIn("self.prep_steam_app_id.clear()", source)
        self.assertIn("self.steamdb_url.clear()", source)
        self.assertIn("self._steam_app_id = None", source)


if __name__ == "__main__":
    unittest.main()
