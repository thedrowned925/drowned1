from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RELEASE_DIR = ROOT / "windows" / "release-manager"
APP = RELEASE_DIR / "app_v18.py"
HANDOFF = RELEASE_DIR / "fdm_submit_v4.py"
WORKFLOW = ROOT / ".github" / "workflows" / "build-windows.yml"


class ReleaseManagerV18Tests(unittest.TestCase):
    def test_v18_installs_only_direct_fdm_handoff(self):
        source = APP.read_text(encoding="utf-8")
        self.assertIn('APP_VERSION = "0.19.0"', source)
        self.assertIn("import app_v17 as previous", source)
        self.assertIn("fdm_submit_v4.install()", source)

    def test_url_is_given_directly_to_fdm_process(self):
        source = HANDOFF.read_text(encoding="utf-8")
        self.assertIn("subprocess.Popen", source)
        self.assertIn("[str(executable), url]", source)
        self.assertIn("_job_exists(url)", source)
        self.assertIn("FDM download job'ı kendi veritabanında doğrulandı", source)
        self.assertNotIn("_find_add_button", source)
        self.assertNotIn("ADD_BUTTON_TEXTS", source)
        self.assertNotIn('send_keys("^v")', source)
        self.assertNotIn("capture_as_image", source)

    def test_modal_is_only_a_post_handoff_fallback(self):
        source = HANDOFF.read_text(encoding="utf-8")
        self.assertIn("def _confirm_add_dialog", source)
        self.assertIn("FIRST_CONFIRM_TEXTS", source)
        self.assertIn("_configure_second_dialog", source)
        self.assertIn("confirm.click_input()", source)

    def test_windows_build_packages_v18_handoff(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("dir: windows/release-manager\n            entry: app_v20.py", workflow)
        self.assertIn("python -m py_compile windows/release-manager/fdm_submit_v4.py", workflow)
        self.assertIn('Pattern "fdm_submit_v4"', workflow)


if __name__ == "__main__":
    unittest.main()
