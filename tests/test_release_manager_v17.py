from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RELEASE_DIR = ROOT / "windows" / "release-manager"
APP = RELEASE_DIR / "app_v17.py"
UI = RELEASE_DIR / "fdm_ui_v3.py"
WORKFLOW = ROOT / ".github" / "workflows" / "build-windows.yml"

HAS_RUNTIME = importlib.util.find_spec("psutil") is not None and importlib.util.find_spec("PIL") is not None
if HAS_RUNTIME:
    sys.path.insert(0, str(RELEASE_DIR))
    from PIL import Image, ImageDraw  # noqa: E402
    import fdm_ui_v3  # noqa: E402
else:
    fdm_ui_v3 = None


class ReleaseManagerV17Tests(unittest.TestCase):
    def test_v17_only_replaces_fdm_submission_layer(self):
        source = APP.read_text(encoding="utf-8")
        self.assertIn('APP_VERSION = "0.17.0"', source)
        self.assertIn("import app_v16 as previous", source)
        self.assertIn("fdm_ui_v3.install()", source)

    def test_visual_bridge_does_not_depend_on_qml_button_text(self):
        source = UI.read_text(encoding="utf-8")
        self.assertIn("capture_as_image", source)
        self.assertIn("def _find_add_button", source)
        self.assertIn("fallback_x = image.size[0] * 0.735", source)
        self.assertIn("def _find_url_outline", source)
        self.assertIn("def _find_confirm_button", source)
        self.assertIn("_set_clipboard_text(url)", source)
        self.assertIn("_configure_second_dialog", source)
        self.assertNotIn('send_keys("^j")', source)
        self.assertNotIn("ADD_BUTTON_TEXTS", source)

    @unittest.skipUnless(HAS_RUNTIME, "visual bridge runtime dependencies are installed in Release Manager matrix job")
    def test_blue_geometry_detects_realistic_fdm_controls(self):
        assert fdm_ui_v3 is not None
        blue = (65, 140, 230)

        image = Image.new("RGB", (1770, 700), (245, 247, 250))
        draw = ImageDraw.Draw(image)
        # Matches the relative geometry measured from the user's FDM 6.34.4 screenshot.
        draw.rectangle((1232, 56, 1378, 96), fill=blue)
        add = fdm_ui_v3._find_add_button(image)
        self.assertIsNotNone(add)
        assert add is not None
        self.assertGreater(add["x"], 1200)

        modal = Image.new("RGB", (909, 296), (225, 230, 235))
        draw = ImageDraw.Draw(modal)
        # Real screenshot: URL field begins close to x=34 and its top blue border
        # can be observed without the whole outline becoming one component.
        draw.line((34, 105, 543, 105), fill=blue, width=3)
        draw.line((34, 105, 34, 145), fill=blue, width=3)
        draw.line((543, 105, 543, 145), fill=blue, width=3)
        draw.rectangle((600, 168, 678, 209), fill=blue)
        outline = fdm_ui_v3._find_url_outline(modal)
        confirm = fdm_ui_v3._find_confirm_button(modal)
        self.assertIsNotNone(outline)
        self.assertIsNotNone(confirm)
        assert outline is not None and confirm is not None
        self.assertGreater(outline["w"], 450)
        self.assertGreaterEqual(outline["h"], 40)
        self.assertLess(confirm["w"], 180)

    def test_windows_build_packages_v17_visual_bridge(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("dir: windows/release-manager\n            entry: app_v17.py", workflow)
        self.assertIn("python -m py_compile windows/release-manager/fdm_ui_v3.py", workflow)
        self.assertIn('Pattern "fdm_ui_v3"', workflow)


if __name__ == "__main__":
    unittest.main()
