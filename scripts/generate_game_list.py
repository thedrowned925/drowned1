from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

CATALOG_PATH = Path("catalog.json")
OUTPUT_PATH = Path("game-list.md")

PLATFORM_ORDER = {
    "pc": 0,
    "windows": 0,
    "ps1": 10,
    "ps2": 11,
    "ps3": 12,
    "ps4": 13,
    "ps5": 14,
    "xbox": 20,
    "xbox-360": 21,
    "xbox-one": 22,
    "xbox-series": 23,
    "switch": 30,
    "android": 40,
    "ios": 41,
}

CHANNEL_ORDER = {
    "stable": 0,
    "beta": 1,
    "dev": 2,
    "nightly": 3,
}


def escape_cell(value: object) -> str:
    return str(value or "-").replace("|", r"\|").replace("\n", " ")


def platform_label(platform: str) -> str:
    value = (platform or "unknown").strip()
    lower = value.lower()
    labels = {
        "pc": "PC",
        "windows": "Windows",
        "ps1": "PS1",
        "ps2": "PS2",
        "ps3": "PS3",
        "ps4": "PS4",
        "ps5": "PS5",
        "xbox": "Xbox",
        "xbox-360": "Xbox 360",
        "xbox-one": "Xbox One",
        "xbox-series": "Xbox Series X|S",
        "switch": "Nintendo Switch",
        "android": "Android",
        "ios": "iOS",
    }
    return labels.get(lower, value.replace("-", " ").title())


def format_gb(size: int) -> str:
    return f"{size / 1_000_000_000:.3f}"


def format_gib(size: int) -> str:
    return f"{size / (1024 ** 3):.3f}"


def format_tb(size: int) -> str:
    return f"{size / 1_000_000_000_000:.3f}"


def format_tib(size: int) -> str:
    return f"{size / (1024 ** 4):.3f}"


def format_updated_at(raw: object) -> str:
    if not raw:
        return "-"
    text = str(raw)
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        dt = dt.astimezone(timezone.utc)
        return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    except ValueError:
        return text


def main() -> None:
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    games = list(catalog.get("games") or [])

    rows_by_platform: dict[str, list[dict]] = defaultdict(list)
    game_ids_by_platform: dict[str, set[str]] = defaultdict(set)

    for game in games:
        platform = str(game.get("platform") or "unknown")
        game_id = str(game.get("id") or game.get("title") or "unknown")
        title = str(game.get("title") or game_id)
        channels = game.get("channels") or {}

        game_ids_by_platform[platform].add(game_id)

        if not channels:
            rows_by_platform[platform].append(
                {
                    "title": title,
                    "channel": "-",
                    "version": "-",
                    "size": 0,
                    "tag": "-",
                }
            )
            continue

        for channel, info in channels.items():
            info = info or {}
            rows_by_platform[platform].append(
                {
                    "title": title,
                    "channel": str(channel),
                    "version": str(info.get("version") or "-"),
                    "size": int(info.get("size") or 0),
                    "tag": str(info.get("tag") or "-"),
                }
            )

    total_size = sum(
        int(row["size"])
        for rows in rows_by_platform.values()
        for row in rows
    )
    total_games = len(games)
    total_releases = sum(len(rows) for rows in rows_by_platform.values())

    lines = [
        "# Game List",
        "",
        "> Bu dosya `catalog.json` verisinden GitHub Actions tarafından otomatik üretilir. Elle düzenlemeyin.",
        "",
        f"- **Toplam oyun:** {total_games}",
        f"- **Toplam aktif sürüm/kanal:** {total_releases}",
        f"- **Toplam aktif boyut:** {format_gb(total_size)} GB ({format_gib(total_size)} GiB) · {format_tb(total_size)} TB ({format_tib(total_size)} TiB)",
        f"- **Katalog güncelleme zamanı:** {format_updated_at(catalog.get('updated_at'))}",
        "",
    ]

    platforms = sorted(
        rows_by_platform,
        key=lambda p: (PLATFORM_ORDER.get(p.lower(), 999), platform_label(p).casefold()),
    )

    for platform in platforms:
        rows = rows_by_platform[platform]
        rows.sort(
            key=lambda row: (
                str(row["title"]).casefold(),
                CHANNEL_ORDER.get(str(row["channel"]).lower(), 999),
                str(row["channel"]).casefold(),
            )
        )

        platform_size = sum(int(row["size"]) for row in rows)
        platform_game_count = len(game_ids_by_platform[platform])

        lines.extend(
            [
                f"## {platform_label(platform)}",
                "",
                (
                    f"**{platform_game_count} oyun · {len(rows)} aktif sürüm/kanal · "
                    f"{format_gb(platform_size)} GB ({format_gib(platform_size)} GiB) · "
                    f"{format_tb(platform_size)} TB ({format_tib(platform_size)} TiB)**"
                ),
                "",
                "| Oyun | Sürüm | Kanal | Boyut (GB) | Boyut (GiB) | Boyut (TB) | Boyut (TiB) | Release etiketi |",
                "|---|---:|---|---:|---:|---:|---:|---|",
            ]
        )

        for row in rows:
            lines.append(
                "| "
                + " | ".join(
                    [
                        escape_cell(row["title"]),
                        escape_cell(row["version"]),
                        escape_cell(row["channel"]),
                        format_gb(int(row["size"])),
                        format_gib(int(row["size"])),
                        format_tb(int(row["size"])),
                        format_tib(int(row["size"])),
                        f"`{escape_cell(row['tag'])}`" if row["tag"] != "-" else "-",
                    ]
                )
                + " |"
            )

        lines.append("")

    lines.extend(
        [
            "---",
            "",
            "_Otomatik üretici: `scripts/generate_game_list.py`_",
            "",
        ]
    )

    OUTPUT_PATH.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
