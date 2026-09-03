from __future__ import annotations

import queue
import threading
import time
from datetime import datetime, timezone
from typing import Any

import requests
from PySide6.QtCore import QObject, Signal

SUPABASE_URL = "https://hfigrspqyxhscbkmporz.supabase.co"
SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImhmaWdyc3BxeXhoc2Nia21wb3J6Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODgzOTY0NjIsImV4cCI6MjEwMzk3MjQ2Mn0.7esPHfTAIS19KKniUi6Klo1Fgoze2-y6jOOlhHlZaGg"
REGISTER_URL = f"{SUPABASE_URL}/functions/v1/release-remote-register"
COMMANDS_URL = f"{SUPABASE_URL}/rest/v1/remote_commands"
POLL_SECONDS = 1.5


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class RemoteControlAgent(QObject):
    """Small paired command bridge for the Windows Release Manager.

    Commands are inserted through a token-verifying Edge Function. The PC reads
    only its own rows through PostgREST; RLS checks the private pairing token in
    the x-machine-token request header. Large game data never passes Supabase.
    """

    command_received = Signal(object)
    status_changed = Signal(str)

    def __init__(
        self,
        github_token: str,
        remote_token: str,
        machine_id: str = "primary",
        display_name: str = "Drowned Release Manager",
    ):
        super().__init__()
        self.github_token = str(github_token or "").strip()
        self.remote_token = str(remote_token or "").strip()
        self.machine_id = str(machine_id or "primary").strip() or "primary"
        self.display_name = str(display_name or "Drowned Release Manager")
        self._stop = threading.Event()
        self._outbox: queue.Queue[tuple[str, str, dict[str, Any] | None, str | None]] = queue.Queue()
        self._thread: threading.Thread | None = None

    @property
    def enabled(self) -> bool:
        return bool(self.github_token and len(self.remote_token) >= 24)

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        if not self.enabled:
            self.status_changed.emit("GitHub token veya eşleştirme kodu eksik")
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="drowned-remote-control", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def complete(self, command_id: str, result: dict[str, Any] | None = None) -> None:
        self._outbox.put((str(command_id), "done", result or {}, None))

    def fail(self, command_id: str, message: str) -> None:
        self._outbox.put((str(command_id), "error", None, str(message)))

    def _headers(self) -> dict[str, str]:
        return {
            "apikey": SUPABASE_ANON_KEY,
            "authorization": f"Bearer {SUPABASE_ANON_KEY}",
            "x-machine-token": self.remote_token,
            "content-type": "application/json",
            "accept": "application/json",
            "user-agent": "Drowned-Release-Manager-Remote/1.0",
        }

    def _register(self, session: requests.Session) -> None:
        response = session.post(
            REGISTER_URL,
            headers={
                "x-github-token": self.github_token,
                "content-type": "application/json",
                "user-agent": "Drowned-Release-Manager-Remote/1.0",
            },
            json={
                "machine_id": self.machine_id,
                "remote_token": self.remote_token,
                "display_name": self.display_name,
            },
            timeout=(4, 8),
        )
        if response.status_code not in range(200, 300):
            raise RuntimeError(f"Eşleştirme kaydı HTTP {response.status_code}: {response.text[:180]}")

    def _patch(self, session: requests.Session, command_id: str, status: str, result, error) -> None:
        body: dict[str, Any] = {"status": status}
        if status == "running":
            body["started_at"] = _utc_now()
        elif status in {"done", "error", "cancelled"}:
            body["completed_at"] = _utc_now()
            body["result"] = result
            body["error"] = error
        response = session.patch(
            f"{COMMANDS_URL}?id=eq.{command_id}&machine_id=eq.{self.machine_id}",
            headers={**self._headers(), "prefer": "return=minimal"},
            json=body,
            timeout=(3, 6),
        )
        if response.status_code not in range(200, 300):
            raise RuntimeError(f"Komut güncelleme HTTP {response.status_code}")

    def _poll(self, session: requests.Session) -> list[dict[str, Any]]:
        response = session.get(
            COMMANDS_URL,
            headers=self._headers(),
            params={
                "machine_id": f"eq.{self.machine_id}",
                "status": "eq.pending",
                "expires_at": f"gt.{_utc_now()}",
                "select": "id,command_type,payload,created_at",
                "order": "created_at.asc",
                "limit": "6",
            },
            timeout=(3, 6),
        )
        if response.status_code not in range(200, 300):
            raise RuntimeError(f"Komut sorgusu HTTP {response.status_code}: {response.text[:160]}")
        data = response.json()
        return data if isinstance(data, list) else []

    def _flush_outbox(self, session: requests.Session) -> None:
        while True:
            try:
                command_id, status, result, error = self._outbox.get_nowait()
            except queue.Empty:
                return
            try:
                self._patch(session, command_id, status, result, error)
            except Exception:
                # Put it back once; the next poll cycle will retry.
                self._outbox.put((command_id, status, result, error))
                return

    def _run(self) -> None:
        session = requests.Session()
        registered = False
        last_error = ""
        while not self._stop.is_set():
            try:
                if not registered:
                    self.status_changed.emit("Supabase eşleştirmesi doğrulanıyor…")
                    self._register(session)
                    registered = True
                    self.status_changed.emit("✓ Android uzaktan kontrol hazır")
                self._flush_outbox(session)
                for command in self._poll(session):
                    command_id = str(command.get("id") or "")
                    if not command_id:
                        continue
                    self._patch(session, command_id, "running", None, None)
                    self.command_received.emit(command)
                last_error = ""
                self._stop.wait(POLL_SECONDS)
            except Exception as exc:
                message = str(exc)
                if message != last_error:
                    self.status_changed.emit("Uzaktan kontrol bağlantısı: " + message)
                    last_error = message
                registered = False
                self._stop.wait(5.0)
