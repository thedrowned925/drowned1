import unittest

from drowned_shared.steam_artwork import SteamArtworkError, parse_steam_app_id


class SteamArtworkTests(unittest.TestCase):
    def test_parse_steamdb_url(self):
        self.assertEqual(parse_steam_app_id("https://steamdb.info/app/620/"), 620)

    def test_parse_store_url_and_plain_id(self):
        self.assertEqual(parse_steam_app_id("https://store.steampowered.com/app/400/Portal/"), 400)
        self.assertEqual(parse_steam_app_id("730"), 730)

    def test_invalid_input(self):
        with self.assertRaises(SteamArtworkError):
            parse_steam_app_id("https://steamdb.info/instantsearch/")


if __name__ == "__main__":
    unittest.main()
