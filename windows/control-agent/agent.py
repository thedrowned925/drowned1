import asyncio
import base64
import io
import json
import os
import platform
import socket
import subprocess
import time
import uuid
from pathlib import Path

import mss
import psutil
import websockets
from PIL import Image

RELAY_BASE = os.getenv("DROWNED_RELAY_URL", "wss://YOUR-RELAY-HOST/ws").rstrip("/")
DEVICE_ID = os.getenv("DROWNED_DEVICE_ID", socket.gethostname().lower().replace(" ", "-"))
TOKEN = os.getenv("DROWNED_REMOTE_TOKEN", "").strip()
CAPTURE_FPS = max(0.5, min(float(os.getenv("DROWNED_CAPTURE_FPS", "3")), 6.0))


class Agent:
    def __init__(self):
        self.ws = None
        self.send_lock = asyncio.Lock()
        self.selected_exe = None
        self.process = None
        self.session_id = None
        self.capture_task = None

    async def send(self, payload):
        if not self.ws:
            return
        async with self.send_lock:
            await self.ws.send(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))

    async def event(self, text, level="info"):
        await self.send({"type": "event", "level": level, "message": text, "timestamp": time.time()})

    async def status(self):
        memory = psutil.virtual_memory()
        disks = []
        for part in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(part.mountpoint)
            except OSError:
                continue
            disks.append({"path": part.mountpoint, "free": usage.free, "total": usage.total})
        await self.send({
            "type": "agent_status",
            "device_id": DEVICE_ID,
            "hostname": socket.gethostname(),
            "cpu": psutil.cpu_percent(),
            "memory_percent": memory.percent,
            "disks": disks,
            "selected_exe": self.selected_exe,
            "test_active": bool(self.process and self.process.poll() is None),
            "pid": self.process.pid if self.process else None,
            "session_id": self.session_id,
            "timestamp": time.time(),
        })

    async def telemetry(self):
        while True:
            await self.status()
            await asyncio.sleep(5)

    async def choose_exe(self, request_id):
        if self.process and self.process.poll() is None:
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
        if self.process and self.process.poll() is None:
            raise RuntimeError("Zaten aktif test var.")
        if not self.selected_exe:
            raise RuntimeError("Önce PC'de EXE seç.")
        exe = Path(self.selected_exe)
        if not exe.exists():
            raise RuntimeError("Seçilen EXE bulunamadı.")
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        self.process = subprocess.Popen([str(exe)], cwd=str(exe.parent), creationflags=flags)
        self.session_id = str(uuid.uuid4())
        self.capture_task = asyncio.create_task(self.capture_loop(self.session_id))
        await self.send({
            "type": "test_started", "request_id": request_id,
            "session_id": self.session_id, "pid": self.process.pid,
            "exe_path": str(exe), "timestamp": time.time(),
        })
        await self.event(f"Test başladı. PID {self.process.pid}")

    async def capture_loop(self, session_id):
        frame = 0
        delay = 1.0 / CAPTURE_FPS
        while self.session_id == session_id and self.process and self.process.poll() is None:
            started = time.monotonic()
            jpg, width, height = await asyncio.to_thread(self.capture_screen)
            frame += 1
            await self.send({
                "type": "screen_frame", "session_id": session_id, "frame": frame,
                "mime": "image/jpeg", "width": width, "height": height,
                "source": "primary_monitor", "data": jpg, "timestamp": time.time(),
            })
            await asyncio.sleep(max(0.01, delay - (time.monotonic() - started)))
        if self.session_id == session_id:
            await self.send({"type": "test_process_exited", "session_id": session_id, "timestamp": time.time()})

    @staticmethod
    def capture_screen():
        with mss.mss() as sct:
            shot = sct.grab(sct.monitors[1])
            image = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
        if image.width > 1280:
            ratio = 1280 / image.width
            image = image.resize((1280, int(image.height * ratio)), Image.Resampling.LANCZOS)
        output = io.BytesIO()
        image.save(output, "JPEG", quality=65, optimize=True)
        return base64.b64encode(output.getvalue()).decode("ascii"), image.width, image.height

    async def finish_test(self, request_id, approved):
        if not self.process:
            raise RuntimeError("Aktif test yok.")
        old_session = self.session_id
        if self.capture_task:
            self.capture_task.cancel()
            await asyncio.gather(self.capture_task, return_exceptions=True)
        await asyncio.to_thread(self.kill_tree, self.process.pid)
        self.process = None
        self.session_id = None
        self.capture_task = None
        await self.send({
            "type": "test_approved" if approved else "test_failed",
            "request_id": request_id, "session_id": old_session,
            "screenshots_deleted": True,
            "next_stage": "upload_ready" if approved else "test_required",
            "timestamp": time.time(),
        })
        await self.event("Test onaylandı; process kapatıldı ve geçici görüntü akışı temizlendi." if approved else "Test başarısız olarak kapatıldı.")

    @staticmethod
    def kill_tree(pid):
        try:
            root = psutil.Process(pid)
        except psutil.NoSuchProcess:
            return
        procs = root.children(recursive=True) + [root]
        for proc in reversed(procs):
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
                        "capabilities": ["telemetry", "pc_exe_picker", "process_test", "screen_preview"],
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
