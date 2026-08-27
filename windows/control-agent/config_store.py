import base64
import ctypes
import json
import os
import socket
import sys
from ctypes import wintypes
from pathlib import Path

APP_DIR = Path(os.getenv("APPDATA") or Path.home()) / "DrownedControl"
CONFIG_PATH = APP_DIR / "agent-config.json"
RUN_VALUE = "Drowned Control Agent"


class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _protect_text(value: str) -> str:
    raw = value.encode("utf-8")
    if os.name != "nt":
        return "plain:" + base64.b64encode(raw).decode("ascii")
    buffer = ctypes.create_string_buffer(raw)
    in_blob = DATA_BLOB(len(raw), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
    out_blob = DATA_BLOB()
    ok = ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(in_blob), "Drowned Control Agent", None, None, None, 0,
        ctypes.byref(out_blob),
    )
    if not ok:
        raise ctypes.WinError()
    try:
        protected = ctypes.string_at(out_blob.pbData, out_blob.cbData)
        return "dpapi:" + base64.b64encode(protected).decode("ascii")
    finally:
        ctypes.windll.kernel32.LocalFree(out_blob.pbData)


def _unprotect_text(value: str) -> str:
    if value.startswith("plain:"):
        return base64.b64decode(value[6:]).decode("utf-8")
    if not value.startswith("dpapi:"):
        return ""
    protected = base64.b64decode(value[6:])
    if os.name != "nt":
        return ""
    buffer = ctypes.create_string_buffer(protected)
    in_blob = DATA_BLOB(len(protected), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
    out_blob = DATA_BLOB()
    ok = ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(in_blob), None, None, None, None, 0,
        ctypes.byref(out_blob),
    )
    if not ok:
        raise ctypes.WinError()
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData).decode("utf-8")
    finally:
        ctypes.windll.kernel32.LocalFree(out_blob.pbData)


def _default_device_id() -> str:
    return socket.gethostname().lower().replace(" ", "-")


def load_saved_config() -> dict | None:
    try:
        payload = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        token = _unprotect_text(payload.get("token", ""))
        relay_url = str(payload.get("relay_url", "")).strip().rstrip("/")
        device_id = str(payload.get("device_id", "")).strip().lower()
        if relay_url and device_id and token:
            return {
                "relay_url": relay_url,
                "device_id": device_id,
                "token": token,
                "start_with_windows": bool(payload.get("start_with_windows", False)),
            }
    except Exception:
        return None
    return None


def save_config(config: dict) -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "relay_url": config["relay_url"].strip().rstrip("/"),
        "device_id": config["device_id"].strip().lower(),
        "token": _protect_text(config["token"].strip()),
        "start_with_windows": bool(config.get("start_with_windows", False)),
    }
    CONFIG_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _set_windows_startup(payload["start_with_windows"])


def _startup_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{Path(sys.executable).resolve()}"'
    script = Path(sys.argv[0]).resolve()
    return f'"{Path(sys.executable).resolve()}" "{script}"'


def _set_windows_startup(enabled: bool) -> None:
    if os.name != "nt":
        return
    import winreg

    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, RUN_VALUE, 0, winreg.REG_SZ, _startup_command())
        else:
            try:
                winreg.DeleteValue(key, RUN_VALUE)
            except FileNotFoundError:
                pass


def show_config_dialog(existing: dict | None = None) -> dict | None:
    import tkinter as tk
    from tkinter import messagebox

    current = existing or {}
    result = {}
    root = tk.Tk()
    root.title("Drowned Control Agent Kurulumu")
    root.geometry("560x330")
    root.resizable(False, False)

    frame = tk.Frame(root, padx=18, pady=18)
    frame.pack(fill="both", expand=True)

    tk.Label(frame, text="Drowned Control Agent", font=("Segoe UI", 16, "bold")).pack(anchor="w")
    tk.Label(
        frame,
        text="Bu bilgisayarın telefondaki Drowned Control uygulamasına bağlanması için ayarları gir.",
        wraplength=510,
        justify="left",
    ).pack(anchor="w", pady=(4, 14))

    tk.Label(frame, text="Relay WSS adresi").pack(anchor="w")
    relay_var = tk.StringVar(value=current.get("relay_url", ""))
    relay = tk.Entry(frame, textvariable=relay_var, width=72)
    relay.pack(fill="x", pady=(2, 9))

    tk.Label(frame, text="Cihaz ID").pack(anchor="w")
    device_var = tk.StringVar(value=current.get("device_id", _default_device_id()))
    tk.Entry(frame, textvariable=device_var, width=72).pack(fill="x", pady=(2, 9))

    tk.Label(frame, text="Gizli erişim token'ı").pack(anchor="w")
    token_var = tk.StringVar(value=current.get("token", ""))
    tk.Entry(frame, textvariable=token_var, show="•", width=72).pack(fill="x", pady=(2, 9))

    startup_var = tk.BooleanVar(value=bool(current.get("start_with_windows", True)))
    tk.Checkbutton(frame, text="Windows açıldığında Agent'ı otomatik başlat", variable=startup_var).pack(anchor="w", pady=(3, 12))

    def submit():
        relay_value = relay_var.get().strip().rstrip("/")
        device_value = device_var.get().strip().lower()
        token_value = token_var.get().strip()
        if not relay_value.startswith(("wss://", "ws://")):
            messagebox.showerror("Geçersiz adres", "Relay adresi wss:// veya yerel test için ws:// ile başlamalı.")
            return
        if not device_value or not token_value:
            messagebox.showerror("Eksik bilgi", "Cihaz ID ve token boş bırakılamaz.")
            return
        result.update({
            "relay_url": relay_value,
            "device_id": device_value,
            "token": token_value,
            "start_with_windows": startup_var.get(),
        })
        root.destroy()

    buttons = tk.Frame(frame)
    buttons.pack(fill="x")
    tk.Button(buttons, text="Kaydet ve Başlat", command=submit, width=18).pack(side="right")
    if existing:
        tk.Button(buttons, text="İptal", command=root.destroy, width=10).pack(side="right", padx=(0, 8))

    root.protocol("WM_DELETE_WINDOW", root.destroy)
    relay.focus_set()
    root.mainloop()
    return result or None


def get_runtime_config(force_configure: bool = False) -> dict:
    env_relay = os.getenv("DROWNED_RELAY_URL", "").strip().rstrip("/")
    env_device = os.getenv("DROWNED_DEVICE_ID", "").strip().lower()
    env_token = os.getenv("DROWNED_REMOTE_TOKEN", "").strip()
    if env_relay and env_device and env_token and not force_configure:
        return {
            "relay_url": env_relay,
            "device_id": env_device,
            "token": env_token,
            "start_with_windows": False,
        }

    saved = load_saved_config()
    if saved and not force_configure:
        return saved

    configured = show_config_dialog(saved)
    if not configured:
        raise SystemExit("Agent yapılandırılmadı.")
    save_config(configured)
    return configured
