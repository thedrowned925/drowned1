from __future__ import annotations

import sys
import time

from PySide6.QtWidgets import QApplication

# Compatibility shim for the FDM submission layers. fdm_bridge historically
# kept its no-op callback on game_prepare as `base._noop`, while the newer FDM
# modules import it as `fdm_bridge._noop`. Install the alias before importing
# app_v17/fdm_ui_v3 so frozen and normal imports behave identically.
import fdm_bridge

if not hasattr(fdm_bridge, "_noop"):
    fdm_bridge._noop = fdm_bridge.base._noop

import app_v17 as previous
import fdm_submit_v4
from drowned_shared.realtime_status import LiveStatusPublisher


APP_VERSION = "0.19.0"

# FDM direct URL handoff remains unchanged. v0.19 adds a best-effort Supabase
# Realtime telemetry mirror for preparation/test/verification. Upload telemetry
# is mirrored by drowned_shared.upload_status.UploadStatusBroadcaster.
fdm_submit_v4.install()


class Manager(previous.Manager):
    def __init__(self):
        self._prep_live: LiveStatusPublisher | None = None
        super().__init__()
        self.setWindowTitle(
            f"Drowned Release Manager {APP_VERSION} • FDM + Supabase Realtime"
        )

    def _new_live_publisher(self, kind: str = "prepare") -> LiveStatusPublisher | None:
        try:
            params = self._params()
            token = str(params.get("token") or "").strip()
        except Exception:
            token = ""
        if not token:
            return None
        title = ""
        try:
            title = self.prep_title.text().strip() or self.game_title.text().strip()
        except Exception:
            pass
        publisher = LiveStatusPublisher(token, kind=kind, title=title)
        return publisher if publisher.enabled else None

    def _live_snapshot(self, snapshot: dict):
        if self._prep_live is None:
            return
        try:
            title = self.prepared_game.title if self.prepared_game else self.prep_title.text().strip()
            self._prep_live.set_context(title=title)
            self._prep_live.update(dict(snapshot), active=True)
        except Exception:
            pass

    def start_preparation(self):
        already_running = self.prep_worker is not None
        super().start_preparation()
        if already_running or self.prep_worker is None:
            return
        if self._prep_live is not None:
            self._prep_live.close()
        self._prep_live = self._new_live_publisher("prepare")
        if self._prep_live is not None:
            self.prep_worker.telemetry.connect(self._live_snapshot)
            self._prep_live.update(
                {
                    "phase": "download",
                    "done": 0,
                    "total": 0,
                    "progress": 0.0,
                    "detail": "FDM indirme işi başlatılıyor",
                },
                force=True,
                active=True,
            )

    def _preparation_done(self, prepared):
        super()._preparation_done(prepared)
        if self._prep_live is not None:
            self._prep_live.set_context(title=prepared.title)
            self._prep_live.update(
                {
                    "phase": "test",
                    "done": 0,
                    "total": 30,
                    "progress": 0.0,
                    "eta": 30,
                    "detail": f"EXE bulundu: {prepared.executable.name}",
                },
                force=True,
                active=True,
            )

    def _preparation_error(self, message: str):
        if self._prep_live is not None:
            self._prep_live.fail(message)
        super()._preparation_error(message)

    def _poll_game_test(self):
        super()._poll_game_test()
        if self._prep_live is None or not self.prepared_game or not self.prepared_game.test_pid:
            return
        elapsed = max(0.0, time.monotonic() - self.test_started_at)
        self._prep_live.update(
            {
                "phase": "test",
                "done": int(min(elapsed, 30.0)),
                "total": 30,
                "progress": min(1.0, elapsed / 30.0),
                "eta": max(0.0, 30.0 - elapsed),
                "detail": self.test_state.text(),
                "current_item": str(self.prepared_game.executable),
            },
            active=True,
        )

    def confirm_game_success(self):
        super().confirm_game_success()
        if self._prep_live is not None and self.prepared_game and self.prepared_game.user_confirmed:
            self._prep_live.update(
                {
                    "phase": "ready",
                    "done": 1,
                    "total": 1,
                    "progress": 1.0,
                    "eta": 0,
                    "detail": "Oyun kullanıcı tarafından başarılı doğrulandı; yayın klasörü bekleniyor",
                },
                force=True,
                active=True,
            )

    def confirm_game_failure(self):
        super().confirm_game_failure()
        if self._prep_live is not None:
            self._prep_live.fail("Oyun testi kullanıcı tarafından başarısız işaretlendi")

    def _start_remote_verification(self, tag: str):
        if self._prep_live is None:
            self._prep_live = self._new_live_publisher("verify")
        if self._prep_live is not None:
            try:
                params = dict(self._last_publish_params or {})
                self._prep_live.set_context(
                    kind="verify",
                    title=str(params.get("title") or ""),
                    platform=str(params.get("platform") or ""),
                    channel=str(params.get("channel") or ""),
                    version=str(params.get("version") or ""),
                )
                self._prep_live.update(
                    {
                        "phase": "remote_verify",
                        "done": 0,
                        "total": 1000,
                        "progress": 0.0,
                        "detail": f"GitHub yayını doğrulanıyor: {tag}",
                    },
                    force=True,
                    active=True,
                )
            except Exception:
                pass
        super()._start_remote_verification(tag)
        if self.remote_worker is not None and self._prep_live is not None:
            self.remote_worker.status.connect(self._live_snapshot)

    def _remote_verify_done(self, result: dict):
        super()._remote_verify_done(result)
        if self._prep_live is not None:
            self._prep_live.finish("complete", "Release + manifest + catalog + Game List doğrulandı")

    def _remote_verify_error(self, message: str):
        if self._prep_live is not None:
            self._prep_live.fail(message)
        super()._remote_verify_error(message)

    def reset_for_new_game(self):
        if self._prep_live is not None:
            self._prep_live.update(
                {
                    "phase": "idle",
                    "done": 0,
                    "total": 0,
                    "progress": 0.0,
                    "eta": None,
                    "detail": "Yeni oyun bekleniyor",
                },
                force=True,
                active=False,
            )
            self._prep_live.close()
            self._prep_live = None
        super().reset_for_new_game()


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
