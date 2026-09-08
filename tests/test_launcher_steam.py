"""Native integration regressions for the isolated launcher presentation.

Tests use temporary Qt settings, an in-memory registry and blocked network / OS
launch calls. Install launcher requirements to execute the UI cases.
"""
from __future__ import annotations

import copy
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
# Headless only when explicitly running tests, never in the launcher entry point.
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
try:
    from PySide6.QtCore import QAbstractAnimation, QBuffer, QIODevice, QSettings, Qt
    from PySide6.QtGui import QPixmap
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QCheckBox
except ImportError:
    QApplication = None


def game(game_id, title, size=100):
    return {'id': game_id, 'title': title, 'platform': 'pc',
            'description': 'Test game', 'artwork': {},
            'channels': {'stable': {'tag': game_id + '-v1', 'version': '1.0', 'size': size}}}


@unittest.skipIf(QApplication is None, 'Install windows/launcher/requirements.txt for native UI tests')
class LauncherSteamTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(ROOT / 'windows' / 'launcher'))
        import app_steam
        import app_v6
        cls.ui, cls.registry_module = app_steam, app_v6
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle('Fusion')
        cls.app.setStyleSheet(app_steam.STYLE)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.settings = QSettings(str(Path(self.temp.name) / 'legacy.ini'), QSettings.IniFormat)
        self.preferences = QSettings(str(Path(self.temp.name) / 'desktop.ini'), QSettings.IniFormat)
        self.settings.setValue('owner', 'existing-owner')
        self.settings.setValue('repo', 'existing-repo')
        self.settings.setValue('branch', 'existing-data-branch')
        self.settings.setValue('unrelated-option', 'preserve me')
        self.original_settings = {key: self.settings.value(key) for key in self.settings.allKeys()}
        self.registry = {'schema_version': 1, 'games': {}, 'partials': {}}
        patches = [
            patch.object(self.ui.BASE.base, 'QSettings', return_value=self.settings),
            patch.object(self.ui, 'QSettings', return_value=self.preferences),
            patch.object(self.registry_module, 'load_registry', return_value=self.registry),
            patch.object(self.ui.Launcher, 'load_catalog'),
            patch.object(self.ui.Launcher, 'load_artwork'),
            patch.object(self.ui.Launcher, '_on_cover_requested'),
            patch.object(self.ui.Launcher, '_on_screenshot_requested'),
            patch.object(self.ui.Launcher, '_request_image'),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.win = self.ui.Launcher()
        self.win.resize(1280, 800)
        self.win.show()
        self.app.processEvents()
        self.addCleanup(self._close_window)
        self.games = [game('alpha', 'Alpha'), game('beta', 'Beta', 300), game('gamma', 'Gamma', 200)]
        self.win.catalog_loaded({'games': copy.deepcopy(self.games)}, 'raw')
        self.app.processEvents()

    def _close_window(self):
        self.win.close()
        if self.win._gamepad:
            self.win._gamepad.stop()
        self.win.deleteLater()
        self.app.processEvents()

    def install_record(self, row):
        current, channel = self.win.library.item(row).data(Qt.UserRole)
        target = Path(self.temp.name) / current['id']
        target.mkdir(exist_ok=True)
        key = self.win._key(current, channel)
        self.registry['games'][key] = {'install_path': str(target), 'title': current['title'],
                                       'tag': current['channels'][channel]['tag'], 'version': '1.0'}
        return key, target

    def test_existing_settings_and_registry_are_unchanged_on_start_and_navigation(self):
        before = copy.deepcopy(self.registry)
        self.win.show_current_game()
        self.win._show_right_page(1)
        self.win.show_home()
        self.win._motion_changed(True)
        self.assertEqual(self.win.owner, 'existing-owner')
        self.assertEqual(self.win.branch, 'existing-data-branch')
        self.assertEqual({key: self.settings.value(key) for key in self.settings.allKeys()}, self.original_settings)
        self.assertEqual(self.registry, before)
        self.assertTrue(self.preferences.value('reduce_motion', type=bool))

    def test_installed_filter_and_sort_activate_correct_source_game(self):
        key, _ = self.install_record(2)
        self.win._set_home_filter(True)
        self.assertEqual(list(self.win._cards), [key])
        self.win._activate_card(key)
        self.assertEqual(self.win.current_game['id'], 'gamma')
        self.assertEqual(self.win.right_stack.currentIndex(), 0)
        self.win._set_home_filter(False)
        self.win.home_sort.setCurrentIndex(2)
        self.assertEqual(self.win._home_rows[0][1]['id'], 'beta')
        self.win._activate_card(self.win._home_rows[0][0])
        self.assertEqual(self.win.current_game['id'], 'beta')

    def test_search_empty_state_disables_stale_actions_and_clears_artwork(self):
        self.install_record(0)
        self.win.update_install_state_ui()
        self.assertTrue(self.win.play_button.isEnabled())
        self.win.search.setText('no-such-game')
        self.win.render_library()
        self.assertIsNone(self.win.current_game)
        self.assertFalse(self.win.play_button.isEnabled())
        self.assertFalse(self.win.install_button.isEnabled())
        self.assertFalse(self.win.verify_button.isEnabled())
        self.assertFalse(self.win.uninstall_button.isEnabled())
        self.assertEqual(len(self.win._cards), 0)
        self.assertTrue(self.win.home_hero.hero.isNull())

    def test_primary_buttons_call_existing_backend_once(self):
        # Signal connection time matters, so use the originally connected bound
        # implementation's first side-effect (folder picker) as the spy.
        self.win.show_current_game()
        self.win.current_game['channels']['stable']['manifest_url'] = 'https://example.invalid/manifest.json'
        with patch('app_v6.QFileDialog.getExistingDirectory', return_value='') as picker:
            QTest.mouseClick(self.win.install_button, Qt.LeftButton)
            self.assertEqual(picker.call_count, 1)

    def test_optional_packages_remain_native_controls_in_accessible_tab(self):
        selected = self.win.current_game
        selected['channels']['stable']['optional_packages'] = [
            {'id': 'textures', 'title': 'High-resolution textures', 'version': '1.0', 'size': 100}
        ]
        self.install_record(0)
        self.win._refresh_addon_panel()
        self.win.show_current_game()
        self.win.tab_addons.click()
        self.app.processEvents()
        self.assertEqual(self.win.detail_stack.currentWidget(), self.win.addon_panel)
        boxes = self.win.addon_panel.findChildren(QCheckBox)
        self.assertEqual(len(boxes), 1)
        self.assertTrue(boxes[0].isEnabled())
        self.assertFalse(boxes[0].isChecked())

    def test_late_artwork_response_cannot_replace_current_hero(self):
        self.win.art_token = 'current'
        image = QPixmap(20, 20)
        image.fill(Qt.red)
        self.win.hero.set_art(image, None, 'Current')
        self.win._sync_home_hero()
        expected = self.win.home_hero.hero.cacheKey()
        self.win.artwork_loaded('obsolete', {'hero': b'invalid'})
        self.assertEqual(self.win.home_hero.hero.cacheKey(), expected)

    def test_cover_refresh_ignores_stale_responses_and_releases_failed_requests(self):
        key = self.win._home_rows[0][0]
        current = self.win.library.item(0).data(Qt.UserRole)[0]
        current['artwork'] = {'cover': 'https://example.invalid/new.png'}
        self.win.library.item(0).setData(Qt.UserRole, (current, 'stable'))
        self.win._refresh_shelf()
        self.win.library_grid.set_items([(key, current, 'stable')])
        self.win.library_grid_bp.set_items([(key, current, 'stable')])
        image = QPixmap(20, 20)
        image.fill(Qt.red)
        buffer = QBuffer()
        buffer.open(QIODevice.WriteOnly)
        image.save(buffer, 'PNG')
        raw = bytes(buffer.data())
        new_url = current['artwork']['cover']
        self.win._cover_pending.add((key, new_url))
        self.win._cover_loaded(key, 'https://example.invalid/old.png', raw)
        self.assertTrue(self.win._cards[key].pixmap.isNull())
        self.win._cover_loaded(key, new_url, None)
        self.assertNotIn((key, new_url), self.win._cover_pending)
        self.win._cover_loaded(key, new_url, raw)
        self.assertFalse(self.win._cards[key].pixmap.isNull())
        self.assertIn(new_url, self.win._tile_cover_cache)

    def test_filtered_transfer_card_recovers_progress_when_shown_again(self):
        key = self.win._home_rows[0][0]
        self.win._set_tile_progress(key, 37)
        self.win._set_home_filter(True)
        self.assertNotIn(key, self.win._cards)
        self.win._set_home_filter(False)
        self.assertEqual(self.win._cards[key].percent, 37)
        self.win._set_tile_progress(key, None)
        self.assertIsNone(self.win._cards[key].percent)

    def test_reduce_motion_stops_an_in_progress_page_transition(self):
        self.win._apply_motion(False)
        self.win.show_current_game()
        self.win._motion_changed(True)
        self.assertEqual(self.win.right_stack._effect.opacity(), 1)
        self.assertEqual(self.win.right_stack._fade.state(), QAbstractAnimation.State.Stopped)

    def test_transfer_start_and_finish_clear_previous_metrics(self):
        from drowned_shared.install import DownloadControl
        self.win.download_control = DownloadControl()
        self.addCleanup(setattr, self.win, 'download_control', None)
        self.win.install_progress(70, '70 MiB / 100 MiB • 12 MiB/sn • 4 stream')
        self.win._set_download_controls(True)
        self.assertEqual(len(self.win.transfer_graph.samples), 0)
        self.assertEqual(self.win.dlp_peak.text(), '—')
        self.assertEqual(self.win.dlp_bar.value(), 0)
        self.win.install_progress(20, '20 MiB / 100 MiB • 2 MiB/sn • 4 stream')
        self.assertEqual(self.win.dlp_peak.text(), '2 MiB/sn')
        self.win._clear_active_download_ui('Tamamlandı')
        self.assertEqual(len(self.win.transfer_graph.samples), 0)
        self.assertEqual(self.win.dlp_net.text(), '—')
        self.assertEqual(self.win.dlp_percent.text(), '%0')

    def test_transfer_metrics_and_pause_mirror_existing_control(self):
        from drowned_shared.install import DownloadControl
        self.win._active_install_context = {'key': self.win._key(self.win.current_game, 'stable'), 'title': 'Alpha', 'channel': 'stable'}
        self.win.download_control = DownloadControl()
        self.win._set_download_controls(True)
        self.win.install_progress(37, '37 MiB / 100 MiB • 12 MiB/sn • 4 stream')
        self.assertEqual(self.win.dlp_bar.value(), 37)
        self.assertEqual(self.win.action_dl_bar.value(), 37)
        self.assertEqual(self.win.transfer_graph.samples[-1], 12 * 1024 * 1024)
        self.assertEqual(self.win.dlp_peak.text(), '12 MiB/sn')
        self.win.toggle_pause()
        self.assertTrue(self.win.download_control.paused)
        self.assertEqual(self.win.dlp_pause.text(), 'DEVAM ET')
        self.win.download_control = None
        self.win._active_install_context = None
        self.win._set_download_controls(False)

    def test_executable_choice_uses_separate_settings_and_no_shell(self):
        _, target = self.install_record(0)
        exe = target / 'game.exe'
        exe.write_bytes(b'test fixture')
        self.win.update_install_state_ui()
        with patch.object(self.ui.QFileDialog, 'getOpenFileName', return_value=(str(exe), '')):
            with patch.object(self.ui.subprocess, 'Popen') as launch:
                self.win.play_current_game()
                launch.assert_called_once_with([str(exe.resolve())], cwd=str(target.resolve()), shell=False)
        self.assertEqual(self.preferences.value(self.win._launch_preference_key()), 'game.exe')
        self.assertEqual({key: self.settings.value(key) for key in self.settings.allKeys()}, self.original_settings)

    def test_play_cannot_race_a_running_repair(self):
        self.install_record(0)
        self.win.update_install_state_ui()
        self.assertTrue(self.win.play_button.isEnabled())
        self.win._active_repair_key = self.win._key(self.win.current_game, 'stable')
        with patch.object(self.ui.subprocess, 'Popen') as launch, patch.object(self.ui.QFileDialog, 'getOpenFileName') as picker:
            self.win.play_current_game()
            launch.assert_not_called()
            picker.assert_not_called()
        self.win._sync_desktop_state()
        self.assertFalse(self.win.play_button.isEnabled())
        self.win._active_repair_key = None

    def test_executable_outside_installation_is_rejected(self):
        self.install_record(0)
        external = Path(self.temp.name) / 'outside.exe'
        external.write_bytes(b'test fixture')
        self.win.update_install_state_ui()
        with patch.object(self.ui.QFileDialog, 'getOpenFileName', return_value=(str(external), '')):
            with patch.object(self.ui.QMessageBox, 'warning') as warning, patch.object(self.ui.subprocess, 'Popen') as launch:
                self.win.play_current_game()
                warning.assert_called_once()
                launch.assert_not_called()

    def test_minimum_window_size_keeps_actions_inside_scrollable_page(self):
        self.install_record(0)
        self.win.update_install_state_ui()
        self.win.resize(1080, 700)
        self.win.show_current_game()
        self.app.processEvents()
        viewport = self.win.right_stack.widget(0).viewport()
        for widget in (self.win.play_button, self.win.install_button, self.win.verify_button, self.win.uninstall_button, self.win.game_menu_button):
            left = widget.mapTo(viewport, widget.rect().topLeft()).x()
            self.assertGreaterEqual(left, 0, widget.text())
            self.assertLessEqual(left + widget.width(), viewport.width(), widget.text())
        self.assertEqual(self.win.right_stack.widget(0).horizontalScrollBar().maximum(), 0)

    def test_narrow_details_fit_with_wide_sidebar_and_active_update(self):
        from drowned_shared.install import DownloadControl
        self.install_record(0)
        self.win.update_install_state_ui()
        self.win.resize(1080, 700)
        self.win.main_splitter.setSizes([370, 710])
        self.win.download_control = DownloadControl()
        self.addCleanup(setattr, self.win, 'download_control', None)
        self.win._set_download_controls(True)
        self.win.show_current_game()
        self.app.processEvents()
        page = self.win.right_stack.widget(0)
        viewport = page.viewport()
        for widget in (self.win.play_button, self.win.install_button, self.win.verify_button,
                       self.win.uninstall_button, self.win.game_menu_button, self.win.action_pause):
            with self.subTest(button=widget.text()):
                left = widget.mapTo(viewport, widget.rect().topLeft()).x()
                self.assertGreaterEqual(left, 0)
                self.assertLessEqual(left + widget.width(), viewport.width())
        self.assertEqual(page.horizontalScrollBar().maximum(), 0)

    def test_big_picture_escape_restores_desktop_page(self):
        self.win.show_home()
        self.win._enter_big_picture()
        self.assertTrue(self.win._big_picture)
        self.win._open_big_picture_game(1)
        self.assertTrue(self.win.big_picture.on_game_page)
        self.win._handle_escape()
        self.assertFalse(self.win.big_picture.on_game_page)
        self.win._handle_escape()
        self.assertFalse(self.win._big_picture)
        self.assertEqual(self.win.right_stack.currentIndex(), 2)


if __name__ == '__main__':
    unittest.main()
