from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import fdm_bridge as base
import fdm_ui_v2 as ui


POLL_INTERVAL = 0.15
HANDOFF_TIMEOUT = 12.0


def _all_fdm_pids() -> list[int]:
    return list(dict.fromkeys(base._fdm_pids()))


def _wait_for_fdm_process(timeout: float = 8.0) -> list[int]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        pids = _all_fdm_pids()
        if pids:
            return pids
        time.sleep(POLL_INTERVAL)
    return []


def _job_exists(url: str) -> bool:
    try:
        return bool(ui._database_has_url(url))
    except Exception:
        return False


def _confirm_add_dialog(url: str, target_dir: Path, log) -> bool:
    """Confirm an Add Download modal if FDM's process handoff opens one.

    We deliberately do not find/click the top toolbar button and do not touch the
    main search edit. The URL has already been handed to fdm.exe. UI automation
    is used only after FDM itself presents a modal confirmation.
    """
    try:
        from pywinauto import Desktop
    except ImportError:
        return False

    pids = _all_fdm_pids()
    if not pids:
        return False
    desktop = Desktop(backend="uia")
    modal_root, confirm = ui._wait_for_button(
        desktop,
        pids,
        ui.FIRST_CONFIRM_TEXTS,
        0.35,
    )
    if modal_root is None or confirm is None:
        return False

    url_edit = ui._pick_url_edit(modal_root, confirm)
    if url_edit is not None:
        current = ui._text(url_edit).strip()
        if url.lower() not in current.lower():
            ui._set_value(url_edit, url)

    confirm.click_input()
    log("FDM: process URL handoff sonrası Add Download onaylandı.")

    # Depending on FDM preferences/build, a Save to / Download confirmation can
    # appear next. The existing compatibility bridge prioritizes a visible
    # destination control and writes the Release Manager target there.
    ui._configure_second_dialog(desktop, pids, target_dir, url, log)
    return True


def submit_to_fdm(url: str, target_dir: Path, log=base._noop):
    """Hand a URL directly to FDM 6.x and let FDM create the download job.

    This avoids all interaction with FDM's redesigned top toolbar. In
    particular, we never search for `İndirme ekle`, never click the search box,
    and never paste a URL into the main window. FDM receives the URL as a
    process argument; we then verify the handoff through FDM's own SQLite job
    state. If FDM chooses to show its Add Download modal, only that modal is
    confirmed as a compatibility fallback.
    """
    if os.name != "nt":
        raise RuntimeError("FDM otomatik entegrasyonu şu anda Windows build'inde destekleniyor.")

    executable = base.find_fdm_executable()
    if not executable:
        raise RuntimeError("Free Download Manager bulunamadı. FDM yolu alanından fdm.exe seçilmeli.")

    target_dir = Path(target_dir).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)

    try:
        subprocess.Popen(
            [str(executable), url],
            cwd=str(executable.parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )
    except OSError as exc:
        raise RuntimeError(f"FDM URL handoff başlatılamadı: {exc}") from exc

    log(f"FDM'ye URL doğrudan proses argümanı olarak gönderildi: {executable}")
    _wait_for_fdm_process()

    deadline = time.monotonic() + HANDOFF_TIMEOUT
    modal_checked = False
    while time.monotonic() < deadline:
        # The positional URL normally either creates a job immediately or opens
        # FDM's own Add Download modal with the URL already populated.
        if _confirm_add_dialog(url, target_dir, log):
            modal_checked = True

        if _job_exists(url):
            if not modal_checked:
                # A destination confirmation may coexist briefly with a newly
                # created DB record. Give it one chance before returning.
                try:
                    from pywinauto import Desktop

                    pids = _all_fdm_pids()
                    if pids:
                        ui._configure_second_dialog(Desktop(backend="uia"), pids, target_dir, url, log)
                except Exception:
                    pass
            log("FDM download job'ı kendi veritabanında doğrulandı.")
            return

        time.sleep(POLL_INTERVAL)

    raise RuntimeError(
        "URL fdm.exe'ye gönderildi ancak FDM download job'ı oluşturmadı. "
        "FDM açıkken aynı URL'nin manuel olarak 'İndirme ekle' ile kabul edildiğini kontrol et."
    )


def install():
    # Keep v2's broader DB-location compatibility, but replace only URL
    # submission. Extraction, telemetry, game test, cleanup and publish remain
    # unchanged.
    ui.install()
    base.submit_to_fdm = submit_to_fdm
