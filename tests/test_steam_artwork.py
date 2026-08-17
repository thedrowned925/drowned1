import unittest

from drowned_shared.steam_artwork import (
    SteamArtworkError,
    collect_steam_screenshot_urls,
    collect_steam_trailers,
    parse_steam_app_id,
)


class SteamArtworkTests(unittest.TestCase):
    def test_parse_steamdb_url(self):
        self.assertEqual(parse_steam_app_id("https://steamdb.info/app/620/"), 620)

    def test_parse_store_url_and_plain_id(self):
        self.assertEqual(parse_steam_app_id("https://store.steampowered.com/app/400/Portal/"), 400)
        self.assertEqual(parse_steam_app_id("730"), 730)

    def test_invalid_input(self):
        with self.assertRaises(SteamArtworkError):
            parse_steam_app_id("https://steamdb.info/instantsearch/")


class SteamMediaTests(unittest.TestCase):
    DETAILS = {
        "movies": [
            {
                "name": "Launch Trailer",
                "thumbnail": "https://cdn.example/thumb.jpg",
                "webm": {"480": "https://cdn.example/480.webm", "max": "https://cdn.example/max.webm"},
                "mp4": {"480": "https://cdn.example/480.mp4", "max": "https://cdn.example/max.mp4"},
            },
            {
                "name": "Gameplay",
                "thumbnail": "https://cdn.example/thumb2.jpg",
                "webm": {"480": "https://cdn.example/480b.webm"},
                "mp4": {},
            },
            {"name": "Broken", "webm": {}, "mp4": {}},
        ],
        "screenshots": [
            {"id": 0, "path_thumbnail": "https://cdn.example/t0.jpg", "path_full": "https://cdn.example/f0.jpg"},
            {"id": 1, "path_thumbnail": "https://cdn.example/t1.jpg"},
        ],
    }

    def test_trailers_prefer_max_quality(self):
        trailers = collect_steam_trailers(self.DETAILS)
        self.assertEqual(len(trailers), 2)
        self.assertEqual(trailers[0]["mp4"], "https://cdn.example/max.mp4")
        self.assertEqual(trailers[0]["webm"], "https://cdn.example/max.webm")
        self.assertEqual(trailers[0]["name"], "Launch Trailer")

    def test_trailers_fall_back_to_480_and_skip_empty(self):
        trailers = collect_steam_trailers(self.DETAILS)
        self.assertEqual(trailers[1]["webm"], "https://cdn.example/480b.webm")
        self.assertEqual(trailers[1]["mp4"], "")
        self.assertNotIn("Broken", [t["name"] for t in trailers])

    def test_trailer_limit(self):
        self.assertEqual(len(collect_steam_trailers(self.DETAILS, limit=1)), 1)

    def test_screenshots_prefer_full_then_thumbnail(self):
        urls = collect_steam_screenshot_urls(self.DETAILS)
        self.assertEqual(urls, ["https://cdn.example/f0.jpg", "https://cdn.example/t1.jpg"])

    def test_missing_media_keys_are_safe(self):
        self.assertEqual(collect_steam_trailers({}), [])
        self.assertEqual(collect_steam_screenshot_urls({}), [])


if __name__ == "__main__":
    unittest.main()
