from __future__ import annotations

import os
import time
from pathlib import Path

import fdm_bridge as base
import fdm_ui_v2 as previous_ui


def _clipboard_get_text() -> str:
    try:
        import win32clipboard
        win32clipboard.OpenClipboard()
        try:
            if win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_UNICODETEXT):
                return str(win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT) or "")
        finally:
            win32clipboard.CloseClipboard()
    except Exception:
        pass
    return ""


def _clipboard_set_text(value: str) -> None:
    try:
        import win32clipboard
        deadline = time.monotonic() + 3.0
        while True:
            try:
                win32clipboard.OpenClipboard()
                break
            except Exception:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.05)
        try:
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardData(win32clipboard.CF_UNICODETEXT, str(value))
        finally:
            win32clipboard.CloseClipboard()
    except Exception as exc:
        raise RuntimeError(f"Windows panosuna FDM URL'si yazılamadı: {exc}") from exc


def _find_main_window(pids: list[int]):
    from pywinauto import Desktop
    desktop = Desktop(backend="uia")
    deadline = time.monotonic() + 12.0
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
                key=lambda w: max(1, w.rectangle().width()) * max(1, w.rectangle().height()),
            )
        time.sleep(0.2)
    raise RuntimeError("FDM ana penceresi bulunamadı.")


def _focus_download_canvas(main):
    """Focus the neutral download-list area, never the search edit.

    FDM 6.34's redesigned Qt toolbar is not reliably exposed through Windows UIA.
    The central download-list canvas is stable, so clicking it before Ctrl+V
    prevents the URL from being pasted into 'İndirmelerde ara...'.
    """
    try:
        rect = main.rectangle()
        x = max(20, int(rect.width() * 0.52))
        y = max(100, int(rect.height() * 0.58))
        main.click_input(coords=(x, y))
        time.sleep(0.15)
    except Exception:
        try:
            main.set_focus()
        except Exception:
            pass


def _open_add_download_with_clipboard(main, url: str, log):
    try:
        from pywinauto.keyboard import send_keys
    except ImportError as exc:
        raise RuntimeError("FDM klavye köprüsü için pywinauto bulunamadı.") from exc

    old_clipboard = _clipboard_get_text()
    _clipboard_set_text(url)
    try:
        main.restore()
    except Exception:
        pass
    try:
        main.set_focus()
    except Exception:
        pass
    try:
        send_keys("{ESC}")
    except Exception:
        pass
    _focus_download_canvas(main)
    send_keys("^v")
    log("FDM: URL panoya yazıldı; indirme listesinde Ctrl+V ile Add Download açıldı.")
    return old_clipboard


def submit_to_fdm(url: str, target_dir: Path, log=base._noop):
    if os.name != "nt":
        raise RuntimeError("FDM otomatik entegrasyonu şu anda Windows build'inde destekleniyor.")
    executable = base.find_fdm_executable()
    if not executable:
        raise RuntimeError("Free Download Manager bulunamadı. FDM yolu alanından fdm.exe seçilmeli.")

    target_dir = Path(target_dir).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    pids = base._ensure_fdm_running(executable)
    main = _find_main_window(pids)

    old_clipboard = _open_add_download_with_clipboard(main, url, log)
    try:
        from pywinauto import Desktop
        desktop = Desktop(backend="uia")
        pids = list(dict.fromkeys(pids + base._fdm_pids()))

        # FDM's own documented Ctrl+V shortcut opens Add Download with the
        # clipboard URL already filled. We never query/click the inaccessible
        # top-right toolbar button anymore.
        modal_root, confirm = previous_ui._wait_for_button(
            desktop, pids, previous_ui.FIRST_CONFIRM_TEXTS, 10.0
        )
        if modal_root is None or confirm is None:
            raise RuntimeError(
                "FDM Ctrl+V ile 'İndirme ekle' penceresini açmadı. "
                "FDM ana penceresini öne getirip tekrar dene."
            )

        url_edit = previous_ui._pick_url_edit(modal_root, confirm)
        if url_edit is not None:
            current = previous_ui._text(url_edit).strip()
            if url.lower() not in current.lower():
                previous_ui._set_value(url_edit, url)

        confirm.click_input()
        log("FDM: 'İndirme ekle' penceresinde TAMAM'a basıldı.")

        # Some FDM builds immediately use their configured default folder;
        # others expose a second Save-to/Download confirmation. Handle it when
        # present and force the Release Manager target directory there.
        previous_ui._configure_second_dialog(desktop, pids, target_dir, url, log)
        log(f"FDM indirme isteği gönderildi: {executable}")
    finally:
        if old_clipboard:
            try:
                _clipboard_set_text(old_clipboard)
            except Exception:
                pass


def install():
    previous_ui.install()
    base.submit_to_fdm = submit_to_fdm
