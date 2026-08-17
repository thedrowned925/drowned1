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
    if "icon" in content_type:
        return ".ico"
    suffix = Path(urlparse(url).path).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp", ".ico"}:
        return ".jpg" if suffix == ".jpeg" else suffix
    return ".jpg"


def collect_steam_trailers(details: dict, limit: int = 8) -> list[dict]:
    """Turn the store `movies` array into plain trailer link records.

    Trailer files are large and Steam already serves them from its own CDN,
    so these stay as external links instead of being downloaded and
    re-uploaded to the distribution repository.
    """
    trailers: list[dict] = []
    for movie in (details.get("movies") or []):
        if len(trailers) >= limit:
            break
        if not isinstance(movie, dict):
            continue
        webm = movie.get("webm") or {}
        mp4 = movie.get("mp4") or {}
        record = {
            "name": str(movie.get("name") or "").strip(),
            "thumbnail": str(movie.get("thumbnail") or ""),
            "webm": str(webm.get("max") or webm.get("480") or ""),
            "mp4": str(mp4.get("max") or mp4.get("480") or ""),
        }
        if not record["webm"] and not record["mp4"]:
            continue
        trailers.append(record)
    return trailers


def collect_steam_screenshot_urls(details: dict, limit: int = 8) -> list[str]:
    urls: list[str] = []
    for shot in (details.get("screenshots") or []):
        if len(urls) >= limit:
            break
        if not isinstance(shot, dict):
            continue
        url = str(shot.get("path_full") or shot.get("path_thumbnail") or "")
        if url:
            urls.append(url)
    return urls


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
    *,
    max_screenshots: int = 8,
) -> dict:
    """Resolve a SteamDB URL/AppID and download the best available Steam artwork.

    SteamDB is used only as the convenient AppID input. Artwork is fetched from
    Steam's own store/CDN endpoints, avoiding SteamDB scraping and bot protection.

    Returns hero/cover/logo/icon image paths, downloaded screenshot paths, and
    trailer links. Trailers stay as links because Steam already hosts them.

    Note on the icon: Steam does not publish a per-app `.ico` through any
    public REST endpoint (the client icon hash lives in internal app info), so
    the small store capsule is downloaded as the icon source. The Release
    Manager lets the user replace it with a real `.ico` file.
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
        icon_candidates = [
            f"{base}/capsule_231x87_2x.jpg",
            f"{base}/capsule_231x87.jpg",
            f"{legacy}/capsule_231x87.jpg",
            str(details.get("capsule_image") or ""),
            str(details.get("capsule_imagev5") or ""),
        ]

        paths: dict[str, str] = {}
        sources: dict[str, str] = {}
        for kind, candidates in (
            ("hero", hero_candidates),
            ("cover", cover_candidates),
            ("logo", logo_candidates),
            ("icon", icon_candidates),
        ):
            found = _first_image(session, candidates)
            if not found:
                continue
            payload, extension, source_url = found
            out = target / f"{kind}{extension}"
            out.write_bytes(payload)
            paths[kind] = str(out)
            sources[kind] = source_url

        screenshot_paths: list[str] = []
        screenshot_sources = collect_steam_screenshot_urls(details, limit=max_screenshots)
        for index, url in enumerate(screenshot_sources):
            result = _download_image(session, url)
            if not result:
                continue
            payload, extension = result
            out = target / f"screenshot-{index:02d}{extension}"
            out.write_bytes(payload)
            screenshot_paths.append(str(out))

        trailers = collect_steam_trailers(details)

        if not paths and not screenshot_paths:
            raise SteamArtworkError(
                f"Steam AppID {app_id} için kullanılabilir artwork bulunamadı."
            )

        return {
            "app_id": app_id,
            "name": str(details.get("name") or ""),
            "description": _clean_description(str(details.get("short_description") or "")),
            "paths": paths,
            "sources": sources,
            "screenshots": screenshot_paths,
            "trailers": trailers,
        }
    finally:
        if own_session:
            session.close()
