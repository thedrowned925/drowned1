import asyncio
import base64
import ctypes
import json
import os
import socket
from ctypes import wintypes
from pathlib import Path

APP_DIR = Path(os.getenv("APPDATA", str(Path.home()))) / "DrownedAgent"
CONFIG_PATH = APP_DIR / "config.json"


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


def load_config():
    if not CONFIG_PATH.exists():
        return None
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        return {
            "relay_url": str(data["relay_url"]).strip(),
            "device_id": str(data["device_id"]).strip().lower(),
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

    tk.Label(root, text="Drowned Agent", font=("Segoe UI", 16, "bold")).grid(row=0, column=0, columnspan=2, padx=18, pady=(16, 4))
    tk.Label(root, text="Bu bilgisayarı Drowned Control'a bağla.").grid(row=1, column=0, columnspan=2, padx=18, pady=(0, 14))

    tk.Label(root, text="Relay adresi").grid(row=2, column=0, sticky="w", padx=18, pady=5)
    relay = tk.Entry(root, width=46)
    relay.grid(row=2, column=1, padx=(0, 18), pady=5)

    tk.Label(root, text="Cihaz ID").grid(row=3, column=0, sticky="w", padx=18, pady=5)
    device = tk.Entry(root, width=46)
    device.grid(row=3, column=1, padx=(0, 18), pady=5)

    tk.Label(root, text="Gizli token").grid(row=4, column=0, sticky="w", padx=18, pady=5)
    token = tk.Entry(root, width=46, show="•")
    token.grid(row=4, column=1, padx=(0, 18), pady=5)

    if existing:
        relay.insert(0, existing.get("relay_url", ""))
        device.insert(0, existing.get("device_id", ""))
        token.insert(0, existing.get("token", ""))
    else:
        device.insert(0, socket.gethostname().lower().replace(" ", "-"))

    def save():
        relay_value = relay.get().strip().rstrip("/")
        device_value = device.get().strip().lower()
        token_value = token.get().strip()
        if not relay_value.startswith(("ws://", "wss://")):
            messagebox.showerror("Drowned Agent", "Relay adresi ws:// veya wss:// ile başlamalı.")
            return
        if not device_value or not token_value:
            messagebox.showerror("Drowned Agent", "Cihaz ID ve token boş olamaz.")
            return
        result.update(relay_url=relay_value, device_id=device_value, token=token_value)
        root.destroy()

    tk.Button(root, text="Kaydet ve Bağlan", command=save, width=20).grid(row=5, column=0, columnspan=2, pady=18)
    root.protocol("WM_DELETE_WINDOW", root.destroy)
    root.mainloop()
    return result or None


def save_config(config):
    APP_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "relay_url": config["relay_url"],
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

    os.environ["DROWNED_RELAY_URL"] = config["relay_url"]
    os.environ["DROWNED_DEVICE_ID"] = config["device_id"]
    os.environ["DROWNED_REMOTE_TOKEN"] = config["token"]

    from agent import Agent

    try:
        asyncio.run(Agent().run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
