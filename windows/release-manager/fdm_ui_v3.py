from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
import time
from collections import deque
from pathlib import Path

import fdm_bridge as base
import fdm_ui_v2 as previous_ui


# FDM 6.29+ uses a Qt/QML desktop UI. In that UI the visible controls are not
# guaranteed to be exposed as native UIA Button/Edit controls. v3 therefore
# uses the top-level FDM window only and locates the actual blue controls from
# the rendered pixels. This avoids confusing the search box with Add Download.


def _set_clipboard_text(text: str) -> None:
    """Put Unicode text on the Windows clipboard using 64-bit-safe Win32 types."""
    if os.name != "nt":
        raise RuntimeError("FDM görsel otomasyonu yalnız Windows'ta kullanılabilir.")

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    GMEM_MOVEABLE = 0x0002
    CF_UNICODETEXT = 13

    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalUnlock.restype = wintypes.BOOL
    kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalFree.restype = wintypes.HGLOBAL

    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.EmptyClipboard.argtypes = []
    user32.EmptyClipboard.restype = wintypes.BOOL
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.SetClipboardData.restype = wintypes.HANDLE
    user32.CloseClipboard.argtypes = []
    user32.CloseClipboard.restype = wintypes.BOOL

    data = (text + "\0").encode("utf-16-le")
    handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
    if not handle:
        raise RuntimeError("Windows clipboard belleği ayrılamadı.")

    pointer = kernel32.GlobalLock(handle)
    if not pointer:
        kernel32.GlobalFree(handle)
        raise RuntimeError("Windows clipboard belleği kilitlenemedi.")
    try:
        ctypes.memmove(pointer, data, len(data))
    finally:
        kernel32.GlobalUnlock(handle)

    opened = False
    for _ in range(20):
        if user32.OpenClipboard(None):
            opened = True
            break
        time.sleep(0.025)
    if not opened:
        kernel32.GlobalFree(handle)
        raise RuntimeError("Windows clipboard açılamadı.")

    transferred = False
    try:
        if not user32.EmptyClipboard():
            raise RuntimeError("Windows clipboard temizlenemedi.")
        result = user32.SetClipboardData(CF_UNICODETEXT, handle)
        if not result:
            raise RuntimeError("URL clipboard'a yazılamadı.")
        transferred = True
    finally:
        user32.CloseClipboard()
        if not transferred:
            kernel32.GlobalFree(handle)


def _is_fdm_blue(rgb: tuple[int, int, int]) -> bool:
    r, g, b = rgb
    return (
        b >= 135
        and b - r >= 42
        and b - g >= 12
        and r <= 175
        and g <= 205
    )


def _blue_components(image, *, x0=0.0, y0=0.0, x1=1.0, y1=1.0, step: int = 2):
    """Return connected blue regions in screenshot coordinates."""
    image = image.convert("RGB")
    width, height = image.size
    left = max(0, int(width * x0))
    top = max(0, int(height * y0))
    right = min(width, int(width * x1))
    bottom = min(height, int(height * y1))
    pixels = image.load()
    points: set[tuple[int, int]] = set()
    for y in range(top, bottom, step):
        for x in range(left, right, step):
            if _is_fdm_blue(pixels[x, y]):
                points.add((x // step, y // step))

    components = []
    while points:
        start = points.pop()
        queue = deque([start])
        min_x = max_x = start[0]
        min_y = max_y = start[1]
        count = 0
        while queue:
            x, y = queue.popleft()
            count += 1
            min_x = min(min_x, x)
            max_x = max(max_x, x)
            min_y = min(min_y, y)
            max_y = max(max_y, y)
            for neighbor in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if neighbor in points:
                    points.remove(neighbor)
                    queue.append(neighbor)
        sx = min_x * step
        sy = min_y * step
        sw = (max_x - min_x + 1) * step
        sh = (max_y - min_y + 1) * step
        components.append({"x": sx, "y": sy, "w": sw, "h": sh, "samples": count})
    return components


def _to_screen(main, image, x: float, y: float) -> tuple[int, int]:
    rect = main.rectangle()
    width = max(1, image.size[0])
    height = max(1, image.size[1])
    sx = rect.left + (x / width) * max(1, rect.width())
    sy = rect.top + (y / height) * max(1, rect.height())
    return int(round(sx)), int(round(sy))


def _click_component(main, image, component) -> None:
    from pywinauto import mouse

    x = component["x"] + component["w"] / 2
    y = component["y"] + component["h"] / 2
    mouse.click(button="left", coords=_to_screen(main, image, x, y))


def _find_main_window(pids: list[int]):
    from pywinauto import Desktop

    desktop = Desktop(backend="uia")
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        candidates = []
        for pid in list(dict.fromkeys(pids + base._fdm_pids())):
            try:
                candidates.extend(desktop.windows(process=pid, visible_only=True))
            except Exception:
                pass
        if candidates:
            return max(
                candidates,
                key=lambda window: max(1, window.rectangle().width())
                * max(1, window.rectangle().height()),
            )
        time.sleep(0.2)
    raise RuntimeError("FDM ana penceresi bulunamadı.")


def _find_add_button(image):
    width, height = image.size
    candidates = []
    for item in _blue_components(image, x0=0.48, y0=0.01, x1=0.96, y1=0.22):
        if 65 <= item["w"] <= 260 and 22 <= item["h"] <= 80:
            cx = item["x"] + item["w"] / 2
            cy = item["y"] + item["h"] / 2
            score = item["samples"] + (cx / max(1, width)) * 100
            if cy < height * 0.22:
                candidates.append((score, item))
    if candidates:
        return max(candidates, key=lambda pair: pair[0])[1]
    return None


def _find_url_outline(image):
    candidates = []
    for item in _blue_components(image, x0=0.05, y0=0.08, x1=0.95, y1=0.78):
        if item["w"] >= 220 and 24 <= item["h"] <= 90:
            candidates.append((item["w"], item))
    return max(candidates, default=(0, None), key=lambda pair: pair[0])[1]


def _find_confirm_button(image):
    candidates = []
    for item in _blue_components(image, x0=0.15, y0=0.10, x1=0.90, y1=0.88):
        if 45 <= item["w"] <= 180 and 24 <= item["h"] <= 75:
            density = item["samples"] / max(1.0, (item["w"] * item["h"]) / 4.0)
            if density >= 0.18:
                score = density * 1000 + item["samples"] + item["y"] * 0.02
                candidates.append((score, item))
    return max(candidates, default=(0, None), key=lambda pair: pair[0])[1]


def _open_add_dialog_visually(main, log=base._noop):
    image = main.capture_as_image()
    button = _find_add_button(image)
    if button is not None:
        _click_component(main, image, button)
        log(
            "FDM: görsel Add Download düğmesi bulundu "
            f"({button['x']},{button['y']} {button['w']}x{button['h']})."
        )
        return

    from pywinauto import mouse

    fallback_x = image.size[0] * 0.735
    fallback_y = image.size[1] * 0.072
    mouse.click(button="left", coords=_to_screen(main, image, fallback_x, fallback_y))
    log("FDM: mavi düğme rengi bulunamadı; FDM 6.34 göreli Add Download konumu kullanıldı.")


def _wait_for_url_dialog(main, timeout: float = 6.0):
    deadline = time.monotonic() + timeout
    last_image = None
    while time.monotonic() < deadline:
        image = main.capture_as_image()
        last_image = image
        outline = _find_url_outline(image)
        if outline is not None:
            return image, outline
        time.sleep(0.15)
    return last_image, None


def submit_to_fdm(url: str, target_dir: Path, log=base._noop):
    """Submit one URL to FDM 6.34 without relying on QML child controls."""
    if os.name != "nt":
        raise RuntimeError("FDM otomatik entegrasyonu şu anda Windows build'inde destekleniyor.")
    executable = base.find_fdm_executable()
    if not executable:
        raise RuntimeError(
            "Free Download Manager bulunamadı. FDM yolu alanından fdm.exe seçilmeli."
        )
    target_dir = Path(target_dir).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    pids = base._ensure_fdm_running(executable)

    try:
        from pywinauto import Desktop
        from pywinauto.keyboard import send_keys
    except ImportError as exc:
        raise RuntimeError("FDM otomasyonu için pywinauto paketi bulunamadı.") from exc

    main = _find_main_window(pids)
    try:
        main.restore()
    except Exception:
        pass
    try:
        main.set_focus()
    except Exception:
        pass

    _open_add_dialog_visually(main, log)
    image, outline = _wait_for_url_dialog(main)
    if image is None or outline is None:
        raise RuntimeError(
            "FDM 'İndirme ekle' penceresi görsel olarak açılamadı. "
            "FDM 6.34 arayüzü beklenen URL alanını göstermedi."
        )

    _click_component(main, image, outline)
    _set_clipboard_text(url)
    time.sleep(0.05)
    send_keys("^a")
    send_keys("^v")
    time.sleep(0.12)

    confirm_image = main.capture_as_image()
    confirm = _find_confirm_button(confirm_image)
    if confirm is not None:
        _click_component(main, confirm_image, confirm)
        log("FDM: URL modalındaki mavi TAMAM/Add düğmesine basıldı.")
    else:
        send_keys("{ENTER}")
        log("FDM: TAMAM düğmesi rengi bulunamadı; URL alanında Enter kullanıldı.")

    # Some FDM builds show a second Save-to/Download dialog after the URL is
    # resolved. Reuse the v2 destination scorer for that dialog so the folder
    # chosen in Release Manager remains authoritative.
    try:
        desktop = Desktop(backend="uia")
        pids = list(dict.fromkeys(pids + base._fdm_pids()))
        previous_ui._configure_second_dialog(desktop, pids, target_dir, url, log)
    except Exception as exc:
        # Do not silently redirect/copy a huge game later: FdmDownloader still
        # verifies the completed FDM path equals target_dir and fails safely if
        # FDM ignored the selected folder.
        log(f"FDM hedef klasör ek ekranı otomatik ayarlanamadı: {exc}")

    log(f"FDM indirme isteği gönderildi: {executable}")


def install():
    previous_ui.install()
    base.submit_to_fdm = submit_to_fdm
