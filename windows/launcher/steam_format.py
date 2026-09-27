"""Qt-free helpers for the v0.19 launcher UI: sizes, speeds, dates and
launch-target discovery. Kept separate so the CI test job (no Qt) can
exercise them directly."""

from __future__ import annotations

import math
import os
import re
from datetime import datetime, timezone
from pathlib import Path

TR_MONTHS = (
    "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
    "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık",
)


def human_size(value) -> str:
    """Same shape as drowned_shared.util.format_bytes ("7.02 GiB"), kept
    local so the UI modules never import the install backend."""
    try:
        amount = float(value or 0)
    except (TypeError, ValueError):
        return "-"
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if amount < 1024 or unit == "TiB":
            return f"{amount:.2f} {unit}"
        amount /= 1024
    return "-"


_SPEED_UNITS = {
    "B": 1,
    "KB": 1024, "KIB": 1024,
    "MB": 1024 ** 2, "MIB": 1024 ** 2,
    "GB": 1024 ** 3, "GIB": 1024 ** 3,
    "TB": 1024 ** 4, "TIB": 1024 ** 4,
}


def speed_to_bytes(text: str) -> float:
    """Read the downloader's "12.34 MiB/sn" back into bytes per second.

    app_v10.parse_speed_bytes only knows decimal units (MB), but
    drowned_shared.util.format_bytes writes IEC units (MiB), so its peak
    readout never moved. The v0.19 graph and peak use this parser.
    """
    cleaned = str(text or "").replace("/sn", "").strip().replace(",", ".")
    parts = cleaned.split()
    if len(parts) < 2:
        return 0.0
    try:
        amount = float(parts[0])
    except ValueError:
        return 0.0
    return amount * _SPEED_UNITS.get(parts[1].upper(), 0)


def parse_iso(value) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def long_date(value) -> str:
    parsed = value if isinstance(value, datetime) else parse_iso(value)
    if parsed is None:
        return "-"
    local = parsed.astimezone()
    return f"{local.day} {TR_MONTHS[local.month - 1]} {local.year}"


def short_date(value) -> str:
    parsed = value if isinstance(value, datetime) else parse_iso(value)
    if parsed is None:
        return "-"
    local = parsed.astimezone()
    return f"{local.day:02d}.{local.month:02d}.{local.year}"


def time_bucket(value, now: datetime | None = None) -> str:
    """Steam's shelf captions: Today / Yesterday / This week / month name."""
    parsed = value if isinstance(value, datetime) else parse_iso(value)
    if parsed is None:
        return ""
    now = (now or datetime.now(timezone.utc)).astimezone()
    local = parsed.astimezone()
    days = (now.date() - local.date()).days
    if days <= 0:
        return "Bugün"
    if days == 1:
        return "Dün"
    if days < 7:
        return "Bu hafta"
    if days < 14:
        return "Geçen hafta"
    if local.year == now.year and local.month == now.month:
        return "Bu ay"
    if local.year == now.year:
        return TR_MONTHS[local.month - 1]
    return f"{TR_MONTHS[local.month - 1]} {local.year}"


# ---------------------------------------------------------------------------
# launch-target discovery
# ---------------------------------------------------------------------------

_SKIP_DIRS = {
    "_commonredist", "commonredist", "redist", "redists", "redistributable", "redistributables", "directx",
    "dotnet", "vcredist", "__installer", "installer", "installers", "support", "_redist", "prerequisites",
    "prereqs", "engine", ".drowned", "__support", "tools", "crashreportclient",
}
_SKIP_NAME = re.compile(
    r"^(unins|uninstall)|setup|redist|vcredist|dxsetup|dxweb|dotnet|crash|reporter|installer|prereq|"
    r"7za|uplaybrowser|ubisoftconnect|^gdf|firewall|testapp|oalinst|physx|quicksfv|cefprocess|"
    r"easyanticheat_setup|eaanticheat\.installer|touchup|activation|register|update",
    re.IGNORECASE,
)


def _tokens(value: str) -> set[str]:
    return {token for token in re.split(r"[^a-z0-9]+", value.lower()) if len(token) > 1}


def find_launch_candidates(root, title: str = "", game_id: str = "", limit: int = 12) -> list[Path]:
    """Likely game executables inside an install folder, best first.

    Manifests carry no launch metadata, so this only ranks candidates:
    shallow files whose name shares words with the title win, redistributable
    installers, uninstallers and crash reporters are skipped. The user
    confirms the choice once and it is remembered per game.
    """
    root = Path(root)
    if not root.is_dir():
        return []
    wanted = _tokens(title) | _tokens(game_id)
    scored: list[tuple[float, Path]] = []
    root_depth = len(root.parts)
    for current, dirs, files in os.walk(root):
        depth = len(Path(current).parts) - root_depth
        dirs[:] = [d for d in dirs if d.lower() not in _SKIP_DIRS and depth < 3]
        for name in files:
            if not name.lower().endswith(".exe") or _SKIP_NAME.search(name):
                continue
            path = Path(current) / name
            try:
                size = path.stat().st_size
            except OSError:
                continue
            score = 100.0 - depth * 18
            score += len(wanted & _tokens(path.stem)) * 30
            if "shipping" in name.lower():
                score += 12
            if "launcher" in name.lower():
                score -= 4
            score += min(20.0, math.log10(max(size, 1)) * 2.5)
            scored.append((score, path))
    scored.sort(key=lambda pair: (-pair[0], str(pair[1]).lower()))
    return [path for _score, path in scored[:limit]]
