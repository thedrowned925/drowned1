from __future__ import annotations

import html
import re
from pathlib import Path
from urllib.parse import urlparse

import requests


class SteamArtworkError(RuntimeError):
    pass


STEAM_UA = "Drowned-Release-Manager/0.4"
APP_ID_PATTERNS = (
    re.compile(r"steamdb\.info/app/(\d+)", re.IGNORECASE),
    re.compile(r"store\.steampowered\.com/app/(\d+)", re.IGNORECASE),
    re.compile(r"steam://store/(\d+)", re.IGNORECASE),
)


def parse_steam_app_id(value: str) -> int:
    text = str(value or "").strip()
    if text.isdigit():
        app_id = int(text)
        if app_id > 0:
            return app_id
    for pattern in APP_ID_PATTERNS:
        match = pattern.search(text)
        if match:
            app_id = int(match.group(1))
            if app_id > 0:
                return app_id
    raise SteamArtworkError(
        "Geçerli bir SteamDB bağlantısı veya Steam AppID bulunamadı. "
        "Örnek: https://steamdb.info/app/620/"
    )


def _clean_description(value: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", str(value or ""), flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    return re.sub(r"[ \t]+", " ", text).strip()


def _image_extension(url: str, content_type: str) -> str:
    content_type = (content_type or "").lower()
    if "png" in content_type:
        return ".png"
    if "webp" in content_type:
        return ".webp"
    suffix = Path(urlparse(url).path).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp"}:
        return ".jpg" if suffix == ".jpeg" else suffix
    return ".jpg"


def _download_image(session: requests.Session, url: str, timeout=(12, 60)) -> tuple[bytes, str] | None:
    try:
        response = session.get(url, timeout=timeout, allow_redirects=True)
        if response.status_code != 200 or not response.content:
            return None
        content_type = str(response.headers.get("Content-Type") or "")
        if content_type and not content_type.lower().startswith("image/"):
            return None
        return response.content, _image_extension(str(response.url or url), content_type)
    except requests.RequestException:
        return None


def _first_image(session: requests.Session, candidates: list[str]) -> tuple[bytes, str, str] | None:
    seen: set[str] = set()
    for url in candidates:
        if not url or url in seen:
            continue
        seen.add(url)
        result = _download_image(session, url)
        if result:
            payload, extension = result
            return payload, extension, url
    return None


def fetch_steam_store_details(app_id: int, session: requests.Session | None = None) -> dict:
    own_session = session is None
    session = session or requests.Session()
    session.headers.update({"User-Agent": STEAM_UA, "Accept": "application/json,text/plain,*/*"})
    try:
        response = session.get(
            "https://store.steampowered.com/api/appdetails",
            params={"appids": str(int(app_id)), "l": "english", "cc": "us"},
            timeout=(12, 45),
        )
        response.raise_for_status()
        payload = response.json()
        record = payload.get(str(int(app_id))) or {}
        if not record.get("success") or not isinstance(record.get("data"), dict):
            raise SteamArtworkError(f"Steam AppID {app_id} için mağaza bilgisi bulunamadı.")
        return record["data"]
    except (requests.RequestException, ValueError) as exc:
        raise SteamArtworkError(f"Steam mağaza bilgisi alınamadı: {exc}") from exc
    finally:
        if own_session:
            session.close()


def download_steam_artwork(
    steamdb_url_or_appid: str,
    target_dir: Path | str,
    session: requests.Session | None = None,
) -> dict:
    """Resolve a SteamDB URL/AppID and download the best available Steam artwork.

    SteamDB is used only as the convenient AppID input. Artwork is fetched from
    Steam's own store/CDN endpoints, avoiding SteamDB scraping and bot protection.
    """
    app_id = parse_steam_app_id(steamdb_url_or_appid)
    target = Path(target_dir)
    target.mkdir(parents=True, exist_ok=True)

    own_session = session is None
    session = session or requests.Session()
    session.headers.update({"User-Agent": STEAM_UA, "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8"})

    try:
        details = fetch_steam_store_details(app_id, session=session)
        base = f"https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{app_id}"
        legacy = f"https://cdn.cloudflare.steamstatic.com/steam/apps/{app_id}"

        hero_candidates = [
            f"{base}/library_hero_2x.jpg",
            f"{base}/library_hero.jpg",
            str(details.get("background_raw") or ""),
            str(details.get("background") or ""),
            f"{legacy}/library_hero.jpg",
            str(details.get("header_image") or ""),
        ]
        cover_candidates = [
            f"{base}/library_600x900_2x.jpg",
            f"{base}/library_600x900.jpg",
            f"{legacy}/library_600x900.jpg",
            # Header is only a last-resort fallback; the Launcher will crop it.
            str(details.get("header_image") or ""),
        ]
        logo_candidates = [
            f"{base}/logo_2x.png",
            f"{base}/logo.png",
            f"{base}/library_logo.png",
            f"{legacy}/logo.png",
        ]

        paths: dict[str, str] = {}
        sources: dict[str, str] = {}
        for kind, candidates in (
            ("hero", hero_candidates),
            ("cover", cover_candidates),
            ("logo", logo_candidates),
        ):
            found = _first_image(session, candidates)
            if not found:
                continue
            payload, extension, source_url = found
            out = target / f"{kind}{extension}"
            out.write_bytes(payload)
            paths[kind] = str(out)
            sources[kind] = source_url

        if not paths:
            raise SteamArtworkError(
                f"Steam AppID {app_id} için kullanılabilir artwork bulunamadı."
            )

        return {
            "app_id": app_id,
            "name": str(details.get("name") or ""),
            "description": _clean_description(str(details.get("short_description") or "")),
            "paths": paths,
            "sources": sources,
        }
    finally:
        if own_session:
            session.close()
