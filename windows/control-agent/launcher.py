import asyncio
import base64
import ctypes
import json
import os
import secrets
import socket
import sys
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


def maybe_offer_update():
    try:
        from update_manager import (
            UpdateError,
            can_self_replace,
            check_for_windows_update,
            current_build_label,
            download_windows_update,
            schedule_windows_replace,
        )
    except Exception as exc:
        print(f"Drowned Agent updater yüklenemedi: {exc}")
        return False

    if not can_self_replace():
        return False

    try:
        update = check_for_windows_update()
    except UpdateError as exc:
        print(f"Güncelleme kontrolü atlandı: {exc}")
        return False
    except Exception as exc:
        print(f"Güncelleme kontrolü atlandı: {exc}")
        return False

    if not update:
        return False

    import tkinter as tk
    from tkinter import messagebox

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        ok = messagebox.askyesno(
            "Drowned Agent Güncellemesi",
            "GitHub'da yeni Drowned Agent sürümü hazır.\n\n"
            f"Mevcut: {current_build_label()}\n"
            f"Yeni: {update.get('version')} · build {update.get('build_number')}\n\n"
            "Şimdi GitHub'dan indirip güncelleyelim mi?",
            parent=root,
        )
        if not ok:
            return False

        try:
            downloaded = download_windows_update(update)
            schedule_windows_replace(downloaded)
        except Exception as exc:
            messagebox.showerror(
                "Drowned Agent Güncellemesi",
                f"Güncelleme kurulamadı:\n\n{exc}",
                parent=root,
            )
            return False

        messagebox.showinfo(
            "Drowned Agent Güncellemesi",
            "Yeni EXE doğrulandı. Drowned Agent kapanıp güncel sürümle yeniden açılacak.",
            parent=root,
        )
        return True
    finally:
        root.destroy()


def setup_dialog(existing=None):
    import tkinter as tk
    from tkinter import messagebox

    try:
        from update_manager import current_build_label
        build_label = current_build_label()
    except Exception:
        build_label = "dev"

    result = {}
    root = tk.Tk()
    root.title("Drowned Agent - Bağlantı Ayarları" if existing else "Drowned Agent - İlk Kurulum")
    root.resizable(False, False)
    root.attributes("-topmost", True)

    tk.Label(root, text="Drowned Agent", font=("Segoe UI", 16, "bold")).grid(
        row=0, column=0, columnspan=3, padx=18, pady=(16, 4)
    )
    tk.Label(
        root,
        text="Telefon bağlantısını buradan yönetebilirsin. Anahtarı kaybetsen bile tekrar görebilir veya yenileyebilirsin.",
        wraplength=470,
        justify="left",
    ).grid(row=1, column=0, columnspan=3, padx=18, pady=(0, 14), sticky="w")

    tk.Label(root, text="Port").grid(row=2, column=0, sticky="w", padx=18, pady=5)
    port = tk.Entry(root, width=46)
    port.grid(row=2, column=1, columnspan=2, padx=(0, 18), pady=5, sticky="ew")

    tk.Label(root, text="Cihaz ID").grid(row=3, column=0, sticky="w", padx=18, pady=5)
    device = tk.Entry(root, width=46)
    device.grid(row=3, column=1, columnspan=2, padx=(0, 18), pady=5, sticky="ew")

    tk.Label(root, text="Erişim anahtarı").grid(row=4, column=0, sticky="w", padx=18, pady=5)
    token = tk.Entry(root, width=46, show="•")
    token.grid(row=4, column=1, columnspan=2, padx=(0, 18), pady=5, sticky="ew")

    if existing:
        port.insert(0, str(existing.get("port", DEFAULT_PORT)))
        device.insert(0, existing.get("device_id", ""))
        token.insert(0, existing.get("token", ""))
    else:
        port.insert(0, str(DEFAULT_PORT))
        device.insert(0, socket.gethostname().lower().replace(" ", "-"))
        token.insert(0, secrets.token_urlsafe(32))

    show_token = tk.BooleanVar(value=False)

    def toggle_visibility():
        token.configure(show="" if show_token.get() else "•")

    tk.Checkbutton(
        root,
        text="Anahtarı göster",
        variable=show_token,
        command=toggle_visibility,
    ).grid(row=5, column=1, sticky="w", pady=(2, 6))

    def copy_value(value: str, label: str):
        value = value.strip()
        if not value:
            messagebox.showwarning("Drowned Agent", f"{label} boş.")
            return
        root.clipboard_clear()
        root.clipboard_append(value)
        root.update()
        messagebox.showinfo("Drowned Agent", f"{label} panoya kopyalandı.")

    def current_address():
        try:
            port_value = int(port.get().strip())
        except ValueError:
            port_value = DEFAULT_PORT
        return f"http://{lan_ip()}:{port_value}"

    tk.Button(
        root,
        text="Anahtarı Kopyala",
        command=lambda: copy_value(token.get(), "Erişim anahtarı"),
        width=20,
    ).grid(row=6, column=1, padx=(0, 6), pady=4, sticky="ew")

    tk.Button(
        root,
        text="Adresi Kopyala",
        command=lambda: copy_value(current_address(), "Agent adresi"),
        width=20,
    ).grid(row=6, column=2, padx=(0, 18), pady=4, sticky="ew")

    def regenerate_token():
        if existing:
            ok = messagebox.askyesno(
                "Erişim anahtarını yenile",
                "Yeni anahtar oluşturulursa telefondaki eski anahtar artık çalışmayacak.\n\nDevam edilsin mi?",
            )
            if not ok:
                return
        token.delete(0, tk.END)
        token.insert(0, secrets.token_urlsafe(32))
        show_token.set(True)
        toggle_visibility()
        token.focus_set()
        token.selection_range(0, tk.END)
        messagebox.showinfo(
            "Drowned Agent",
            "Yeni erişim anahtarı oluşturuldu. Kaydettiğinde aktif olacak. İstersen şimdi kopyalayabilirsin.",
        )

    tk.Button(
        root,
        text="Yeni Anahtar Oluştur",
        command=regenerate_token,
        width=22,
    ).grid(row=7, column=1, columnspan=2, padx=(0, 18), pady=(4, 8), sticky="w")

    address_text = tk.StringVar(value=f"Bağlantı adresi: {current_address()}")
    tk.Label(root, textvariable=address_text, fg="#475569").grid(
        row=8, column=0, columnspan=3, padx=18, pady=(0, 4), sticky="w"
    )
    tk.Label(root, text=f"Sürüm: {build_label}", fg="#64748b").grid(
        row=9, column=0, columnspan=3, padx=18, pady=(0, 8), sticky="w"
    )

    def refresh_address(_event=None):
        address_text.set(f"Bağlantı adresi: {current_address()}")

    port.bind("<KeyRelease>", refresh_address)

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
            "Ayarlar kaydedildi. Telefonda PC Control ekranında şu bilgileri kullan:\n\n"
            f"Agent adresi:\n{address}\n\n"
            f"Erişim anahtarı:\n{token_value}\n\n"
            "Telefon ve PC aynı Wi-Fi/LAN üzerinde olmalı.",
        )
        root.destroy()

    tk.Button(root, text="Kaydet ve Agent'ı Başlat", command=save, width=26).grid(
        row=10, column=0, columnspan=3, pady=(8, 18)
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
    existing = load_config()
    headless = "--headless" in sys.argv
    no_update = "--no-update" in sys.argv

    if not headless and not no_update and maybe_offer_update():
        return

    if headless:
        if existing is None:
            print("Drowned Agent: --headless kullanmak için önce normal kurulum yapılmalı.")
            return
        config = existing
    else:
        config = setup_dialog(existing)
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
