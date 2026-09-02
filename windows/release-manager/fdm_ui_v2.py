from __future__ import annotations

import os
import re
import sqlite3
import time
from pathlib import Path

import fdm_bridge as base


ADD_BUTTON_TEXTS = {"indirme ekle", "add download"}
FIRST_CONFIRM_TEXTS = {"tamam", "ok", "add"}
START_BUTTON_TEXTS = {"indir", "download", "başlat", "baslat", "start"}
URL_LABEL_TOKENS = ("url girin", "enter url", "torrent dosyas", "torrent file")
FOLDER_LABEL_TOKENS = ("kaydet", "save to", "save in", "klasör", "klasor", "folder", "konum", "location")


def _norm(value: str) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _text(control) -> str:
    try:
        return str(control.window_text() or "")
    except Exception:
        return ""


def _rect(control):
    try:
        return control.rectangle()
    except Exception:
        return None


def _center(control) -> tuple[float, float]:
    rect = _rect(control)
    if rect is None:
        return 0.0, 0.0
    return (float(rect.left + rect.right) / 2.0, float(rect.top + rect.bottom) / 2.0)


def _visible(control) -> bool:
    try:
        return bool(control.is_visible()) and bool(control.is_enabled())
    except Exception:
        return True


def _descendants(root, control_type: str | None = None):
    try:
        if control_type:
            return list(root.descendants(control_type=control_type))
        return list(root.descendants())
    except Exception:
        return []


def _roots(desktop, pids: list[int]):
    roots = []
    seen = set()
    for pid in pids:
        try:
            windows = desktop.windows(process=pid, visible_only=True)
        except Exception:
            continue
        for window in windows:
            try:
                handle = int(window.handle)
            except Exception:
                handle = id(window)
            if handle not in seen:
                seen.add(handle)
                roots.append(window)
    return roots


def _largest_root(desktop, pids: list[int]):
    roots = _roots(desktop, pids)
    if not roots:
        return None
    def area(window):
        rect = _rect(window)
        return max(1, rect.width()) * max(1, rect.height()) if rect else 1
    return max(roots, key=area)


def _find_exact_button(root, texts: set[str]):
    wanted = {_norm(value) for value in texts}
    candidates = []
    for button in _descendants(root, "Button"):
        if not _visible(button):
            continue
        value = _norm(_text(button))
        if value in wanted:
            candidates.append(button)
    if not candidates:
        return None
    # Prefer the left-most/top-most match. For the main window this selects the
    # real "İndirme ekle" button and never the search field.
    return min(candidates, key=lambda item: (_center(item)[1], _center(item)[0]))


def _label_rects(root, tokens: tuple[str, ...]):
    found = []
    for control in _descendants(root):
        if not _visible(control):
            continue
        value = _norm(_text(control))
        if value and any(token in value for token in tokens):
            rect = _rect(control)
            if rect is not None:
                found.append(rect)
    return found


def _pick_url_edit(root, confirm_button):
    edits = [control for control in _descendants(root, "Edit") if _visible(control)]
    if not edits:
        return None
    confirm_x, confirm_y = _center(confirm_button)
    root_rect = _rect(root)
    labels = _label_rects(root, URL_LABEL_TOKENS)

    scored = []
    for edit in edits:
        rect = _rect(edit)
        if rect is None:
            continue
        x, y = _center(edit)
        score = 0.0
        # The real URL input is directly above the TAMAM/OK button inside the
        # add-download modal. The main FDM search box sits at the very top and
        # receives a strong penalty.
        dy = confirm_y - y
        if 10 <= dy <= 220:
            score += 260.0 - dy
        else:
            score -= 250.0
        score -= abs(confirm_x - x) * 0.08
        if rect.width() >= 260:
            score += 25.0
        if root_rect is not None and rect.top < root_rect.top + 70:
            score -= 600.0
        current = _norm(_text(edit))
        if current.startswith("http://") or current.startswith("https://"):
            score += 20.0
        for label in labels:
            # Screenshot/UI contract: URL field is immediately below the
            # "URL girin veya torrent dosyasını seçin" label.
            if rect.top >= label.bottom and rect.top - label.bottom <= 90:
                score += 500.0
                break
        scored.append((score, edit))
    return max(scored, default=(float("-inf"), None), key=lambda item: item[0])[1]


def _set_value(control, value: str):
    errors = []
    for method in ("set_edit_text", "set_value"):
        try:
            getattr(control, method)(value)
            return
        except Exception as exc:
            errors.append(str(exc))
    try:
        control.click_input()
        control.type_keys("^a", set_foreground=True)
        control.type_keys(value, with_spaces=True, set_foreground=True)
        return
    except Exception as exc:
        errors.append(str(exc))
    raise RuntimeError("FDM alanına değer yazılamadı: " + " | ".join(errors[-2:]))


def _pick_destination_control(root, action_button, target_dir: Path):
    action_x, action_y = _center(action_button)
    labels = _label_rects(root, FOLDER_LABEL_TOKENS)
    controls = []
    for kind in ("Edit", "ComboBox"):
        controls.extend(control for control in _descendants(root, kind) if _visible(control))
    scored = []
    for control in controls:
        rect = _rect(control)
        if rect is None:
            continue
        x, y = _center(control)
        value = _text(control).strip()
        score = 0.0
        if re.search(r"[a-zA-Z]:\\", value) or value.startswith("\\\\"):
            score += 450.0
        if str(target_dir).lower() in value.lower():
            score += 700.0
        if y < action_y and action_y - y <= 300:
            score += 100.0
        score -= abs(action_x - x) * 0.03
        for label in labels:
            if rect.top >= label.bottom and rect.top - label.bottom <= 110:
                score += 500.0
                break
        if _norm(value).startswith("http"):
            score -= 800.0
        scored.append((score, control))
    best_score, best = max(scored, default=(float("-inf"), None), key=lambda item: item[0])
    return best if best_score >= 250 else None


def _wait_for_button(desktop, pids: list[int], texts: set[str], timeout: float):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for root in _roots(desktop, pids):
            button = _find_exact_button(root, texts)
            if button is not None:
                return root, button
        time.sleep(0.12)
    return None, None


def _database_has_url(url: str) -> bool:
    database = find_fdm_database_v2()
    if database is None:
        return False
    try:
        uri = database.resolve().as_uri() + "?mode=ro"
        connection = sqlite3.connect(uri, uri=True, timeout=0.5)
        try:
            for (table,) in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
                try:
                    columns = [row[1] for row in connection.execute(f'PRAGMA table_info("{str(table).replace(chr(34), chr(34)*2)}")')]
                    if not columns:
                        continue
                    rows = connection.execute(f'SELECT * FROM "{str(table).replace(chr(34), chr(34)*2)}" ORDER BY rowid DESC LIMIT 120').fetchall()
                except sqlite3.DatabaseError:
                    continue
                needle = url.lower()
                for row in rows:
                    if any(needle in str(value).lower() for value in row if value is not None):
                        return True
        finally:
            connection.close()
    except Exception:
        return False
    return False


def find_fdm_database_v2() -> Path | None:
    existing = base.find_fdm_database()
    if existing:
        return existing
    roots = []
    for env_name in ("LOCALAPPDATA", "APPDATA"):
        value = os.environ.get(env_name)
        if value:
            roots.extend([
                Path(value) / "Free Download Manager",
                Path(value) / "Softdeluxe" / "Free Download Manager",
            ])
    executable = base.find_fdm_executable()
    if executable:
        roots.extend([executable.parent, executable.parent / "data", executable.parent / "Data"])
    candidates = []
    for root in roots:
        if not root.exists():
            continue
        for pattern in ("*.sqlite", "*.db", "*.sqlite3"):
            try:
                candidates.extend(root.glob(pattern))
                candidates.extend(root.glob("*/*" + pattern[1:]))
            except OSError:
                pass
    candidates = [path for path in candidates if path.is_file()]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _configure_second_dialog(desktop, pids: list[int], target_dir: Path, url: str, log):
    """Handle FDM's post-URL "Save to / Download" confirmation when present."""
    deadline = time.monotonic() + 12.0
    while time.monotonic() < deadline:
        # If FDM already created the job, there may be no second confirmation in
        # the user's UI mode. Do not click arbitrary controls after that point.
        if _database_has_url(url):
            return
        for root in _roots(desktop, pids):
            action = _find_exact_button(root, START_BUTTON_TEXTS)
            if action is None:
                continue
            destination = _pick_destination_control(root, action, target_dir)
            if destination is None:
                continue
            _set_value(destination, str(target_dir))
            action.click_input()
            log(f"FDM hedef klasörü ayarlandı: {target_dir}")
            return
        time.sleep(0.15)
    # Some FDM layouts use the configured default folder and immediately create
    # the job after the first TAMAM. The downloader later verifies the actual
    # FDM job path, so we do not guess/click anything here.


def submit_to_fdm_v2(url: str, target_dir: Path, log=base.base._noop):
    if os.name != "nt":
        raise RuntimeError("FDM otomatik entegrasyonu şu anda Windows build'inde destekleniyor.")
    executable = base.find_fdm_executable()
    if not executable:
        raise RuntimeError("Free Download Manager bulunamadı. 'FDM yolu' alanından fdm.exe seç.")
    target_dir = Path(target_dir).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    pids = base._ensure_fdm_running(executable)

    try:
        from pywinauto import Desktop
    except ImportError as exc:
        raise RuntimeError("FDM UI köprüsü için pywinauto paketi bulunamadı.") from exc

    desktop = Desktop(backend="uia")
    main = None
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        pids = list(dict.fromkeys(pids + base._fdm_pids()))
        main = _largest_root(desktop, pids)
        if main is not None:
            add_button = _find_exact_button(main, ADD_BUTTON_TEXTS)
            if add_button is not None:
                break
        time.sleep(0.2)
    else:
        raise RuntimeError("FDM ana penceresinde 'İndirme ekle / Add download' butonu bulunamadı.")

    # Critical v16 fix: click the actual Add Download button. Never use Ctrl+J
    # and never target the main search box.
    main.set_focus()
    add_button.click_input()
    log("FDM: 'İndirme ekle' butonuna basıldı.")

    modal_root, confirm = _wait_for_button(desktop, pids, FIRST_CONFIRM_TEXTS, 10.0)
    if modal_root is None or confirm is None:
        raise RuntimeError("FDM 'İndirme ekle' penceresindeki TAMAM/OK butonu bulunamadı.")
    url_edit = _pick_url_edit(modal_root, confirm)
    if url_edit is None:
        raise RuntimeError("FDM 'İndirme ekle' penceresindeki URL alanı bulunamadı.")
    _set_value(url_edit, url)
    confirm.click_input()
    log("FDM: URL gerçek 'İndirme ekle' penceresine yazıldı ve TAMAM'a basıldı.")

    _configure_second_dialog(desktop, pids, target_dir, url, log)


# Patch helpers used by the existing FdmDownloader without touching extraction,
# EXE detection, game test, cleanup or upload code.
def install():
    base.submit_to_fdm = submit_to_fdm_v2
    base.find_fdm_database = find_fdm_database_v2
