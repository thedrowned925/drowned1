from __future__ import annotations
import json
from urllib.parse import unquote
from .constants import CATALOG_NAME
from .util import slugify


def manifest_repo_path(platform:str, game_id:str, channel:str, version:str)->str:
    return f"manifests/{slugify(platform)}/{slugify(game_id)}/{slugify(channel)}/{slugify(version)}.json"


def load_catalog(client)->dict:
    raw=client.raw_content(CATALOG_NAME)
    if raw is None: return {"schema_version":1,"updated_at":None,"games":[]}
    data=json.loads(raw.decode("utf-8"))
    if data.get("schema_version") != 1 or not isinstance(data.get("games"),list):
        raise ValueError("Unsupported or invalid catalog schema")
    return data


def repo_path_from_raw_url(client,url:str)->str|None:
    prefix=f"https://raw.githubusercontent.com/{client.owner}/{client.repo}/{client.branch}/"
    if not isinstance(url,str) or not url.startswith(prefix): return None
    path=unquote(url[len(prefix):]).strip("/")
    return path or None
