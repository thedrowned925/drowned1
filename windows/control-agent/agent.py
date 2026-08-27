import asyncio
import base64
import ctypes
import io
import json
import os
import platform
import socket
import subprocess
import time
import uuid
from ctypes import wintypes
from pathlib import Path

import mss
import psutil
import websockets
from PIL import Image

RELAY_BASE = os.getenv("DROWNED_RELAY_URL", "wss://YOUR-RELAY-HOST/ws").rstrip("/")
DEVICE_ID = os.getenv("DROWNED_DEVICE_ID", socket.gethostname().lower().replace(" ", "-"))
TOKEN = os.getenv("DROWNED_REMOTE_TOKEN", "").strip()
CAPTURE_FPS = max(0.5, min(float(os.getenv("DROWNED_CAPTURE_FPS", "3")), 6.0))


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class Agent:
    def __init__(self):
        self.ws = None
        self.send_lock = asyncio.Lock()
        self.selected_exe = None
        self.process = None
        self.session_id = None
        self.capture_task = None
        self.tracked_pids = set()

    async def send(self, payload):
        if not self.ws:
            return
        async with self.send_lock:
            await self.ws.send(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))

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

    async def status(self):
        memory = psutil.virtual_memory()
        disks = []
        for part in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(part.mountpoint)
            except OSError:
                continue
            disks.append({"path": part.mountpoint, "free": usage.free, "total": usage.total})
        pids = sorted(self.live_test_pids()) if self.session_id else []
        await self.send({
            "type": "agent_status",
            "device_id": DEVICE_ID,
            "hostname": socket.gethostname(),
            "cpu": psutil.cpu_percent(),
            "memory_percent": memory.percent,
            "disks": disks,
            "selected_exe": self.selected_exe,
            "test_active": bool(pids),
            "pid": self.process.pid if self.process else None,
            "tracked_pids": pids,
            "session_id": self.session_id,
            "timestamp": time.time(),
        })

    async def telemetry(self):
        while True:
            await self.status()
            await asyncio.sleep(5)

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
            "type": "test_started", "request_id": request_id,
            "session_id": self.session_id, "pid": self.process.pid,
            "exe_path": str(exe), "timestamp": time.time(),
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
                "type": "screen_frame", "session_id": session_id, "frame": frame,
                "mime": "image/jpeg", "width": width, "height": height,
                "source": source, "data": jpg, "timestamp": time.time(),
            })
            await asyncio.sleep(max(0.01, delay - (time.monotonic() - started)))
        if self.session_id == session_id:
            await self.send({
                "type": "test_process_exited", "session_id": session_id,
                "tracked_pids": sorted(self.tracked_pids), "timestamp": time.time(),
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
            "request_id": request_id, "session_id": old_session,
            "screenshots_deleted": True,
            "next_stage": "upload_ready" if approved else "test_required",
            "timestamp": time.time(),
        })
        await self.event("Test onaylandı; process ağacı kapatıldı ve geçici görüntü akışı temizlendi." if approved else "Test başarısız olarak kapatıldı.")

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

    async def handle(self, raw):
        msg = json.loads(raw)
        if msg.get("type") != "command":
            return
        command = msg.get("command")
        request_id = msg.get("request_id") or str(uuid.uuid4())
        try:
            if command == "request_status":
                await self.status()
            elif command == "choose_executable":
                await self.choose_exe(request_id)
            elif command == "start_test":
                await self.start_test(request_id)
            elif command == "approve_test":
                await self.finish_test(request_id, True)
            elif command in ("reject_test", "stop_test"):
                await self.finish_test(request_id, False)
            else:
                await self.send({"type": "error", "request_id": request_id, "message": f"Bilinmeyen komut: {command}"})
        except Exception as exc:
            await self.send({"type": "error", "request_id": request_id, "message": str(exc), "timestamp": time.time()})

    async def run(self):
        if not TOKEN:
            raise SystemExit("DROWNED_REMOTE_TOKEN ayarlanmalı.")
        url = f"{RELAY_BASE}/agent/{DEVICE_ID}"
        wait = 2
        while True:
            try:
                async with websockets.connect(
                    url, extra_headers={"Authorization": f"Bearer {TOKEN}"},
                    ping_interval=20, ping_timeout=20, max_size=8 * 1024 * 1024,
                ) as ws:
                    self.ws = ws
                    wait = 2
                    await self.send({
                        "type": "agent_hello", "device_id": DEVICE_ID,
                        "hostname": socket.gethostname(), "os": platform.platform(),
                        "capabilities": ["telemetry", "pc_exe_picker", "process_tree_test", "screen_preview"],
                        "timestamp": time.time(),
                    })
                    task = asyncio.create_task(self.telemetry())
                    try:
                        async for raw in ws:
                            await self.handle(raw)
                    finally:
                        task.cancel()
                        await asyncio.gather(task, return_exceptions=True)
            except Exception as exc:
                print(f"Relay bağlantısı koptu: {exc}")
            finally:
                self.ws = None
            await asyncio.sleep(wait)
            wait = min(wait * 2, 30)


if __name__ == "__main__":
    try:
        asyncio.run(Agent().run())
    except KeyboardInterrupt:
        pass
