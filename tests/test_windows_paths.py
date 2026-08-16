import unittest

from drowned_shared.util import safe_windows_dir_name


class WindowsInstallPathTests(unittest.TestCase):
    def test_colon_is_replaced_readably(self):
        self.assertEqual(
            safe_windows_dir_name("Grand Theft Auto: Vice City"),
            "Grand Theft Auto - Vice City",
        )

    def test_other_forbidden_characters_are_removed(self):
        result = safe_windows_dir_name('Game <Deluxe> / Test? * Edition|')
        for char in '<>:"/\\|?*':
            self.assertNotIn(char, result)

    def test_reserved_device_name_is_escaped(self):
        self.assertEqual(safe_windows_dir_name("CON"), "CON_")
        self.assertEqual(safe_windows_dir_name("com1"), "com1_")

    def test_trailing_space_and_dot_are_removed(self):
        self.assertEqual(safe_windows_dir_name("Game...   "), "Game")


if __name__ == "__main__":
    unittest.main()
