import asyncio
import base64
import ctypes
import json
import os
import secrets
import socket
from ctypes import wintypes
from pathlib import Path

APP_DIR = Path(os.getenv("APPDATA", str(Path.home()))) / "DrownedAgent"
CONFIG_PATH = APP_DIR / "config.json"
DEFAULT_PORT = 47821


class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _blob(data: bytes):
    buffer = ctypes.create_string_buffer(data)
    return DATA_BLOB(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte))), buffer


def protect_text(text: str) -> str:
    if os.name != "nt":
        return base64.b64encode(text.encode("utf-8")).decode("ascii")
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    in_blob, keepalive = _blob(text.encode("utf-8"))
    out_blob = DATA_BLOB()
    if not crypt32.CryptProtectData(
        ctypes.byref(in_blob), "DrownedAgent", None, None, None, 0,
        ctypes.byref(out_blob),
    ):
        raise ctypes.WinError()
    try:
        raw = ctypes.string_at(out_blob.pbData, out_blob.cbData)
        return base64.b64encode(raw).decode("ascii")
    finally:
        kernel32.LocalFree(out_blob.pbData)
        _ = keepalive


def unprotect_text(value: str) -> str:
    raw = base64.b64decode(value)
    if os.name != "nt":
        return raw.decode("utf-8")
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    in_blob, keepalive = _blob(raw)
    out_blob = DATA_BLOB()
    if not crypt32.CryptUnprotectData(
        ctypes.byref(in_blob), None, None, None, None, 0,
        ctypes.byref(out_blob),
    ):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData).decode("utf-8")
    finally:
        kernel32.LocalFree(out_blob.pbData)
        _ = keepalive


def lan_ip():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("10.255.255.255", 1))
        value = sock.getsockname()[0]
        if value and not value.startswith("127."):
            return value
    except OSError:
        pass
    finally:
        sock.close()
    try:
        value = socket.gethostbyname(socket.gethostname())
        return value or "127.0.0.1"
    except OSError:
        return "127.0.0.1"


def load_config():
    if not CONFIG_PATH.exists():
        return None
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        port = int(data.get("port", DEFAULT_PORT))
        if not 1024 <= port <= 65535:
            return None
        return {
            "port": port,
            "device_id": str(data.get("device_id") or socket.gethostname()).strip().lower(),
            "token": unprotect_text(str(data["token_protected"])),
        }
    except Exception:
        return None


def setup_dialog(existing=None):
    import tkinter as tk
    from tkinter import messagebox

    result = {}
    root = tk.Tk()
    root.title("Drowned Agent - İlk Kurulum")
    root.resizable(False, False)
    root.attributes("-topmost", True)

    tk.Label(root, text="Drowned Agent", font=("Segoe UI", 16, "bold")).grid(
        row=0, column=0, columnspan=2, padx=18, pady=(16, 4)
    )
    tk.Label(root, text="Telefonu bu bilgisayara aynı ağ üzerinden bağla.").grid(
        row=1, column=0, columnspan=2, padx=18, pady=(0, 14)
    )

    tk.Label(root, text="Port").grid(row=2, column=0, sticky="w", padx=18, pady=5)
    port = tk.Entry(root, width=46)
    port.grid(row=2, column=1, padx=(0, 18), pady=5)

    tk.Label(root, text="Cihaz ID").grid(row=3, column=0, sticky="w", padx=18, pady=5)
    device = tk.Entry(root, width=46)
    device.grid(row=3, column=1, padx=(0, 18), pady=5)

    tk.Label(root, text="Erişim anahtarı").grid(row=4, column=0, sticky="w", padx=18, pady=5)
    token = tk.Entry(root, width=46, show="•")
    token.grid(row=4, column=1, padx=(0, 18), pady=5)

    if existing:
        port.insert(0, str(existing.get("port", DEFAULT_PORT)))
        device.insert(0, existing.get("device_id", ""))
        token.insert(0, existing.get("token", ""))
    else:
        port.insert(0, str(DEFAULT_PORT))
        device.insert(0, socket.gethostname().lower().replace(" ", "-"))
        token.insert(0, secrets.token_urlsafe(32))

    def save():
        try:
            port_value = int(port.get().strip())
        except ValueError:
            messagebox.showerror("Drowned Agent", "Port sayı olmalı.")
            return
        if not 1024 <= port_value <= 65535:
            messagebox.showerror("Drowned Agent", "Port 1024-65535 arasında olmalı.")
            return

        device_value = device.get().strip().lower()
        token_value = token.get().strip()
        if not device_value or len(token_value) < 24:
            messagebox.showerror(
                "Drowned Agent",
                "Cihaz ID boş olamaz ve erişim anahtarı en az 24 karakter olmalı.",
            )
            return

        result.update(port=port_value, device_id=device_value, token=token_value)
        address = f"http://{lan_ip()}:{port_value}"
        messagebox.showinfo(
            "Drowned Agent",
            "Telefonda PC Control ekranına şu bilgileri gir:\n\n"
            f"Agent adresi:\n{address}\n\n"
            f"Erişim anahtarı:\n{token_value}\n\n"
            "Telefon ve PC aynı Wi-Fi/LAN üzerinde olmalı.",
        )
        root.destroy()

    tk.Button(root, text="Kaydet ve Agent'ı Başlat", command=save, width=24).grid(
        row=5, column=0, columnspan=2, pady=18
    )
    root.protocol("WM_DELETE_WINDOW", root.destroy)
    root.mainloop()
    return result or None


def save_config(config):
    APP_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "port": int(config["port"]),
        "device_id": config["device_id"],
        "token_protected": protect_text(config["token"]),
    }
    CONFIG_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main():
    config = load_config()
    if config is None:
        config = setup_dialog()
        if not config:
            return
        save_config(config)

    os.environ["DROWNED_AGENT_HOST"] = "0.0.0.0"
    os.environ["DROWNED_AGENT_PORT"] = str(config["port"])
    os.environ["DROWNED_DEVICE_ID"] = config["device_id"]
    os.environ["DROWNED_REMOTE_TOKEN"] = config["token"]

    address = f"http://{lan_ip()}:{config['port']}"
    print("Drowned Agent hazır.")
    print(f"Telefon bağlantı adresi: {address}")
    print("Bu pencere açık kaldığı sürece Agent çalışır.")

    from agent import Agent

    try:
        asyncio.run(Agent().run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
