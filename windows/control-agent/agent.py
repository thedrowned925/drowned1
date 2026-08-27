import asyncio
import base64
import ctypes
import io
import os
import platform
import secrets
import socket
import subprocess
import time
import uuid
from contextlib import asynccontextmanager
from ctypes import wintypes
from pathlib import Path

import mss
import psutil
import uvicorn
from fastapi import FastAPI, Header, HTTPException, Query, Request
from PIL import Image

from download_watcher import DownloadWatcher

AGENT_HOST = os.getenv("DROWNED_AGENT_HOST", "0.0.0.0").strip() or "0.0.0.0"
AGENT_PORT = int(os.getenv("DROWNED_AGENT_PORT", "47821"))
DEVICE_ID = os.getenv("DROWNED_DEVICE_ID", socket.gethostname().lower().replace(" ", "-"))
TOKEN = os.getenv("DROWNED_REMOTE_TOKEN", "").strip()
CAPTURE_FPS = max(0.5, min(float(os.getenv("DROWNED_CAPTURE_FPS", "3")), 6.0))
CLIENT_TTL_SECONDS = 120.0


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class Agent:
    def __init__(self):
        self.selected_exe = None
        self.process = None
        self.session_id = None
        self.capture_task = None
        self.tracked_pids = set()
        self.download_watcher = DownloadWatcher()
        self.download_task = None
        self.clients = {}
        self.client_seen = {}

        @asynccontextmanager
        async def lifespan(_app):
            telemetry_task = asyncio.create_task(self.telemetry())
            try:
                yield
            finally:
                telemetry_task.cancel()
                await asyncio.gather(telemetry_task, return_exceptions=True)
                if self.download_task and not self.download_task.done():
                    self.download_task.cancel()
                    await asyncio.gather(self.download_task, return_exceptions=True)

        self.app = FastAPI(
            title="Drowned PC Agent",
            version="0.1.0",
            docs_url=None,
            redoc_url=None,
            lifespan=lifespan,
        )
        self.configure_routes()

    def require_auth(self, authorization):
        if not TOKEN:
            raise HTTPException(status_code=503, detail="Agent token is not configured")
        prefix = "Bearer "
        if not authorization or not authorization.startswith(prefix):
            raise HTTPException(status_code=401, detail="Missing bearer token")
        candidate = authorization[len(prefix):].strip()
        if not secrets.compare_digest(candidate, TOKEN):
            raise HTTPException(status_code=401, detail="Invalid bearer token")

    def configure_routes(self):
        @self.app.get("/api/status")
        async def api_status(authorization: str | None = Header(default=None)):
            self.require_auth(authorization)
            return self.status_payload()

        @self.app.get("/api/drives")
        async def api_drives(authorization: str | None = Header(default=None)):
            self.require_auth(authorization)
            return {"drives": self.list_drives(), "timestamp": time.time()}

        @self.app.get("/api/files")
        async def api_files(
            path: str = Query(..., min_length=1),
            authorization: str | None = Header(default=None),
        ):
            self.require_auth(authorization)
            try:
                return self.list_directory(path)
            except FileNotFoundError:
                raise HTTPException(status_code=404, detail="Folder not found")
            except PermissionError:
                raise HTTPException(status_code=403, detail="Folder access denied")
            except OSError as exc:
                raise HTTPException(status_code=400, detail=str(exc))

        @self.app.get("/api/events/next")
        async def api_events_next(
            client_id: str = Query(..., min_length=8, max_length=128),
            authorization: str | None = Header(default=None),
        ):
            self.require_auth(authorization)
            queue = self.client_queue(client_id)
            try:
                return await asyncio.wait_for(queue.get(), timeout=25.0)
            except asyncio.TimeoutError:
                self.client_seen[client_id] = time.monotonic()
                return {
                    "type": "heartbeat",
                    "agent_online": True,
                    "device_id": DEVICE_ID,
                    "timestamp": time.time(),
                }

        @self.app.post("/api/command")
        async def api_command(
            request: Request,
            authorization: str | None = Header(default=None),
        ):
            self.require_auth(authorization)
            try:
                message = await request.json()
            except Exception:
                raise HTTPException(status_code=400, detail="Invalid JSON body")
            if not isinstance(message, dict):
                raise HTTPException(status_code=400, detail="JSON body must be an object")
            await self.handle(message)
            return {
                "accepted": True,
                "request_id": message.get("request_id"),
                "timestamp": time.time(),
            }

    def prune_clients(self):
        now = time.monotonic()
        stale = [
            client_id for client_id, seen in self.client_seen.items()
            if now - seen > CLIENT_TTL_SECONDS
        ]
        for client_id in stale:
            self.clients.pop(client_id, None)
            self.client_seen.pop(client_id, None)

    def client_queue(self, client_id):
        self.prune_clients()
        queue = self.clients.get(client_id)
        if queue is None:
            queue = asyncio.Queue(maxsize=64)
            self.clients[client_id] = queue
        self.client_seen[client_id] = time.monotonic()
        return queue

    async def send(self, payload):
        self.prune_clients()
        for queue in list(self.clients.values()):
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                pass

    async def event(self, text, level="info"):
        await self.send({"type": "event", "level": level, "message": text, "timestamp": time.time()})

    def live_test_pids(self):
        found = set()
        queue = list(self.tracked_pids)
        while queue:
            pid = queue.pop()
            if pid in found or not psutil.pid_exists(pid):
                continue
            found.add(pid)
            try:
                children = psutil.Process(pid).children(recursive=False)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
            for child in children:
                if child.pid not in found:
                    queue.append(child.pid)
        self.tracked_pids.update(found)
        return found

    def status_payload(self):
        memory = psutil.virtual_memory()
        disks = []
        for part in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(part.mountpoint)
            except OSError:
                continue
            disks.append({
                "path": part.mountpoint,
                "free": usage.free,
                "total": usage.total,
            })
        pids = sorted(self.live_test_pids()) if self.session_id else []
        return {
            "type": "agent_status",
            "device_id": DEVICE_ID,
            "hostname": socket.gethostname(),
            "os": platform.platform(),
            "cpu": psutil.cpu_percent(),
            "memory_percent": memory.percent,
            "disks": disks,
            "selected_exe": self.selected_exe,
            "test_active": bool(pids),
            "pid": self.process.pid if self.process else None,
            "tracked_pids": pids,
            "session_id": self.session_id,
            "fdm_running": self.download_watcher.fdm_running(),
            "download_folder": self.download_watcher.folder,
            "download_watch_active": bool(self.download_watcher.started_at),
            "capabilities": [
                "telemetry",
                "remote_folder_browser",
                "pc_folder_picker",
                "pc_exe_picker",
                "process_tree_test",
                "screen_preview",
                "fdm_folder_watch",
            ],
            "timestamp": time.time(),
        }

    async def status(self):
        await self.send(self.status_payload())

    async def telemetry(self):
        while True:
            if self.clients:
                await self.status()
            await asyncio.sleep(5)

    @staticmethod
    def list_drives():
        drives = []
        seen = set()
        for part in psutil.disk_partitions(all=False):
            mount = part.mountpoint
            key = mount.lower() if os.name == "nt" else mount
            if key in seen:
                continue
            seen.add(key)
            try:
                usage = psutil.disk_usage(mount)
            except OSError:
                continue
            label = Path(mount).drive or mount
            drives.append({
                "name": label,
                "path": mount,
                "free": usage.free,
                "total": usage.total,
            })
        if not drives and os.name != "nt":
            try:
                usage = psutil.disk_usage("/")
                drives.append({"name": "/", "path": "/", "free": usage.free, "total": usage.total})
            except OSError:
                pass
        return drives

    @staticmethod
    def list_directory(raw_path):
        folder = Path(raw_path).expanduser()
        if not folder.exists():
            raise FileNotFoundError(raw_path)
        if not folder.is_dir():
            raise NotADirectoryError(raw_path)
        folder = folder.resolve()

        directories = []
        try:
            entries = list(folder.iterdir())
        except PermissionError:
            raise

        for entry in entries:
            try:
                if entry.is_dir():
                    directories.append({"name": entry.name, "path": str(entry)})
            except OSError:
                continue
        directories.sort(key=lambda item: item["name"].lower())
        parent = None if folder.parent == folder else str(folder.parent)
        return {
            "path": str(folder),
            "parent": parent,
            "directories": directories,
            "timestamp": time.time(),
        }

    async def choose_download_folder(self, request_id):
        folder = await asyncio.to_thread(self.download_watcher.choose_folder_dialog)
        if folder:
            await self.set_download_folder(request_id, folder)
        else:
            await self.send({"type": "download_folder_selection_cancelled", "request_id": request_id})

    async def set_download_folder(self, request_id, folder):
        if self.download_watcher.started_at is not None:
            raise RuntimeError("İndirme izlemesi aktifken klasör değiştirilemez.")
        path = Path(folder).expanduser()
        if not path.exists() or not path.is_dir():
            raise RuntimeError("İndirme klasörü bulunamadı.")
        resolved = str(path.resolve())
        self.download_watcher.folder = resolved
        await self.send({
            "type": "download_folder_selected",
            "request_id": request_id,
            "folder": resolved,
            "fdm_running": self.download_watcher.fdm_running(),
            "timestamp": time.time(),
        })
        await self.event(f"İndirme klasörü seçildi: {resolved}")

    async def start_download_watch(self, request_id):
        if not self.download_watcher.folder:
            raise RuntimeError("Önce indirme klasörünü seç.")
        if self.download_task and not self.download_task.done():
            self.download_task.cancel()
            await asyncio.gather(self.download_task, return_exceptions=True)
        snapshot = await asyncio.to_thread(self.download_watcher.start, self.download_watcher.folder)
        await self.send({
            "type": "download_watch_started",
            "request_id": request_id,
            **snapshot,
            "timestamp": time.time(),
        })
        self.download_task = asyncio.create_task(self.download_loop())
        await self.event("İndirme klasörü izleniyor.")

    async def stop_download_watch(self, request_id):
        if self.download_task and not self.download_task.done():
            self.download_task.cancel()
            await asyncio.gather(self.download_task, return_exceptions=True)
        self.download_task = None
        snapshot = await asyncio.to_thread(self.download_watcher.stop)
        await self.send({
            "type": "download_watch_stopped",
            "request_id": request_id,
            **snapshot,
            "timestamp": time.time(),
        })
        await self.event("İndirme klasörü izlemesi durduruldu.")

    async def download_loop(self):
        while self.download_watcher.started_at is not None:
            snapshot = await asyncio.to_thread(self.download_watcher.poll)
            await self.send({"type": "download_progress", **snapshot, "timestamp": time.time()})
            await asyncio.sleep(1)

    async def choose_exe(self, request_id):
        if self.session_id and self.live_test_pids():
            raise RuntimeError("Aktif test varken EXE değiştirilemez.")
        path = await asyncio.to_thread(self._dialog)
        if path:
            self.selected_exe = path
            await self.send({"type": "exe_selected", "request_id": request_id, "path": path})
            await self.event(f"EXE seçildi: {path}")
        else:
            await self.send({"type": "exe_selection_cancelled", "request_id": request_id})

    @staticmethod
    def _dialog():
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        value = filedialog.askopenfilename(
            title="Drowned Agent - Test edilecek EXE'yi seç",
            filetypes=[("Windows uygulaması", "*.exe")],
        )
        root.destroy()
        return value or None

    async def start_test(self, request_id):
        if self.session_id and self.live_test_pids():
            raise RuntimeError("Zaten aktif test var.")
        if not self.selected_exe:
            raise RuntimeError("Önce PC'de EXE seç.")
        exe = Path(self.selected_exe)
        if not exe.exists():
            raise RuntimeError("Seçilen EXE bulunamadı.")
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        self.process = subprocess.Popen([str(exe)], cwd=str(exe.parent), creationflags=flags)
        self.tracked_pids = {self.process.pid}
        self.session_id = str(uuid.uuid4())
        self.capture_task = asyncio.create_task(self.capture_loop(self.session_id))
        await self.send({
            "type": "test_started",
            "request_id": request_id,
            "session_id": self.session_id,
            "pid": self.process.pid,
            "exe_path": str(exe),
            "timestamp": time.time(),
        })
        await self.event(f"Test başladı. Başlangıç PID {self.process.pid}")

    async def capture_loop(self, session_id):
        frame = 0
        delay = 1.0 / CAPTURE_FPS
        while self.session_id == session_id:
            pids = self.live_test_pids()
            if not pids:
                break
            started = time.monotonic()
            jpg, width, height, source = await asyncio.to_thread(self.capture_for_pids, pids)
            frame += 1
            await self.send({
                "type": "screen_frame",
                "session_id": session_id,
                "frame": frame,
                "mime": "image/jpeg",
                "width": width,
                "height": height,
                "source": source,
                "data": jpg,
                "timestamp": time.time(),
            })
            await asyncio.sleep(max(0.01, delay - (time.monotonic() - started)))
        if self.session_id == session_id:
            await self.send({
                "type": "test_process_exited",
                "session_id": session_id,
                "tracked_pids": sorted(self.tracked_pids),
                "timestamp": time.time(),
            })

    @staticmethod
    def find_game_window(pids):
        if os.name != "nt":
            return None
        user32 = ctypes.windll.user32
        candidates = []
        enum_proc_type = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

        @enum_proc_type
        def callback(hwnd, _):
            if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
                return True
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value not in pids:
                return True
            rect = RECT()
            if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                return True
            width = rect.right - rect.left
            height = rect.bottom - rect.top
            area = max(0, width) * max(0, height)
            if area >= 20000:
                candidates.append((area, rect.left, rect.top, rect.right, rect.bottom))
            return True

        user32.EnumWindows(callback, 0)
        if not candidates:
            return None
        _, left, top, right, bottom = max(candidates, key=lambda item: item[0])
        return left, top, right, bottom

    @classmethod
    def capture_for_pids(cls, pids):
        rect = cls.find_game_window(pids)
        source = "game_window"
        with mss.mss() as sct:
            if rect:
                left, top, right, bottom = rect
                monitor = {
                    "left": left,
                    "top": top,
                    "width": max(1, right - left),
                    "height": max(1, bottom - top),
                }
                try:
                    shot = sct.grab(monitor)
                except Exception:
                    source = "primary_monitor_fallback"
                    shot = sct.grab(sct.monitors[1])
            else:
                source = "primary_monitor_fallback"
                shot = sct.grab(sct.monitors[1])
            image = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
        if image.width > 1280:
            ratio = 1280 / image.width
            image = image.resize((1280, max(1, int(image.height * ratio))), Image.Resampling.LANCZOS)
        output = io.BytesIO()
        image.save(output, "JPEG", quality=65, optimize=True)
        return base64.b64encode(output.getvalue()).decode("ascii"), image.width, image.height, source

    async def finish_test(self, request_id, approved):
        if not self.session_id:
            raise RuntimeError("Aktif test yok.")
        old_session = self.session_id
        if self.capture_task:
            self.capture_task.cancel()
            await asyncio.gather(self.capture_task, return_exceptions=True)
        await asyncio.to_thread(self.kill_tracked)
        self.process = None
        self.session_id = None
        self.capture_task = None
        self.tracked_pids.clear()
        await self.send({
            "type": "test_approved" if approved else "test_failed",
            "request_id": request_id,
            "session_id": old_session,
            "screenshots_deleted": True,
            "next_stage": "upload_ready" if approved else "test_required",
            "timestamp": time.time(),
        })
        await self.event(
            "Test onaylandı; process ağacı kapatıldı ve geçici görüntü akışı temizlendi."
            if approved else "Test başarısız olarak kapatıldı."
        )

    def kill_tracked(self):
        pids = self.live_test_pids()
        procs = []
        for pid in pids:
            try:
                procs.append(psutil.Process(pid))
            except psutil.NoSuchProcess:
                pass
        for proc in sorted(procs, key=lambda p: p.pid, reverse=True):
            try:
                proc.terminate()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        _, alive = psutil.wait_procs(procs, timeout=4)
        for proc in alive:
            try:
                proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

    async def handle(self, msg):
        if msg.get("type") != "command":
            return
        command = msg.get("command")
        request_id = msg.get("request_id") or str(uuid.uuid4())
        try:
            if command == "request_status":
                await self.status()
            elif command == "choose_download_folder":
                await self.choose_download_folder(request_id)
            elif command == "set_download_folder":
                folder = str(msg.get("path") or "").strip()
                if not folder:
                    raise RuntimeError("Klasör yolu gerekli.")
                await self.set_download_folder(request_id, folder)
            elif command == "start_download_watch":
                await self.start_download_watch(request_id)
            elif command == "stop_download_watch":
                await self.stop_download_watch(request_id)
            elif command == "choose_executable":
                await self.choose_exe(request_id)
            elif command == "start_test":
                await self.start_test(request_id)
            elif command == "approve_test":
                await self.finish_test(request_id, True)
            elif command in ("reject_test", "stop_test"):
                await self.finish_test(request_id, False)
            else:
                await self.send({
                    "type": "error",
                    "request_id": request_id,
                    "message": f"Bilinmeyen komut: {command}",
                    "timestamp": time.time(),
                })
        except Exception as exc:
            await self.send({
                "type": "error",
                "request_id": request_id,
                "message": str(exc),
                "timestamp": time.time(),
            })

    async def run(self):
        if not TOKEN:
            raise SystemExit("DROWNED_REMOTE_TOKEN ayarlanmalı.")
        config = uvicorn.Config(
            self.app,
            host=AGENT_HOST,
            port=AGENT_PORT,
            log_level="info",
            access_log=False,
        )
        server = uvicorn.Server(config)
        await server.serve()


if __name__ == "__main__":
    try:
        asyncio.run(Agent().run())
    except KeyboardInterrupt:
        pass
