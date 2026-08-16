from __future__ import annotations
import json
from datetime import datetime, timezone
from .constants import CATALOG_NAME
from .metadata import load_catalog, manifest_repo_path, repo_path_from_raw_url


def _find_game(catalog:dict, game_id:str, platform:str)->dict:
    for game in catalog.get("games",[]):
        if game.get("id")==game_id and game.get("platform")==platform:
            return game
    raise KeyError(f"game not found: {platform}/{game_id}")


def _delete_release_for_channel(client, data:dict, log):
    tag=data.get("tag")
    if not tag: raise ValueError("catalog channel has no release tag")
    release_deleted=False; tag_deleted=False
    release=client.release_by_tag(tag)
    if release is None:
        log(f"Release already absent: {tag}")
    else:
        log(f"Deleting GitHub Release and all attached chunk assets: {tag}")
        client.delete_release(int(release["id"])); release_deleted=True
        log(f"Deleted release: {tag}")
    if client.delete_tag_ref(tag):
        tag_deleted=True; log(f"Deleted Git tag: {tag}")
    else:
        log(f"Git tag already absent: {tag}")
    return release_deleted,tag_deleted


def _delete_manifest(client, game:dict, channel:str, data:dict, log):
    path=data.get("manifest_path") or manifest_repo_path(game["platform"],game["id"],channel,data.get("version","unknown"))
    if client.delete_repo_file(path,f"Delete {game['title']} {channel} manifest"):
        log(f"Deleted raw manifest: {path}")
        return True
    log(f"Manifest already absent: {path}")
    return False


def _delete_artwork(client, game:dict, log):
    deleted=[]
    for kind,url in list((game.get("artwork") or {}).items()):
        path=repo_path_from_raw_url(client,url)
        if not path:
            log(f"Skipping non-repository artwork URL ({kind})")
            continue
        if client.delete_repo_file(path,f"Delete {game['title']} {kind} artwork"):
            deleted.append(path); log(f"Deleted artwork: {path}")
        else:
            log(f"Artwork already absent: {path}")
    return deleted


def _commit_catalog(client,catalog:dict,message:str):
    catalog["updated_at"]=datetime.now(timezone.utc).isoformat()
    client.upsert_text(CATALOG_NAME,json.dumps(catalog,ensure_ascii=False,indent=2),message)


def delete_channel(client, game_id:str, platform:str, channel:str, log=print)->dict:
    """Delete one published channel/version and then remove its catalog entry.

    Remote deletion is deliberately performed before the catalog mutation. The
    operation is idempotent: a retry treats already-missing releases, tags and
    manifests as successfully deleted and can finish the catalog cleanup.
    """
    catalog=load_catalog(client); game=_find_game(catalog,game_id,platform)
    channels=game.get("channels") or {}
    if channel not in channels: raise KeyError(f"channel not found: {channel}")
    data=dict(channels[channel]); releases=0; tags=0; manifests=0; artwork=[]
    rd,td=_delete_release_for_channel(client,data,log); releases+=int(rd); tags+=int(td)
    if _delete_manifest(client,game,channel,data,log): manifests+=1
    del channels[channel]
    removed_game=False
    if not channels:
        artwork=_delete_artwork(client,game,log)
        catalog["games"].remove(game); removed_game=True
    else:
        game["channels"]=channels
    _commit_catalog(client,catalog,f"Delete {game['title']} {channel}")
    log("Catalog updated after remote files were removed")
    return {"game_removed":removed_game,"channels_removed":[channel],"releases_deleted":releases,"tags_deleted":tags,"manifests_deleted":manifests,"artwork_deleted":artwork}


def delete_game(client, game_id:str, platform:str, log=print)->dict:
    """Delete all releases/tags/manifests/artwork and finally the game catalog row.

    If a network/API failure occurs mid-operation, the catalog is intentionally
    left untouched. Re-running is safe because missing remote resources are
    treated as already deleted, allowing the final catalog commit to complete.
    """
    catalog=load_catalog(client); game=_find_game(catalog,game_id,platform)
    channels=dict(game.get("channels") or {}); releases=0; tags=0; manifests=0
    for channel,data in channels.items():
        rd,td=_delete_release_for_channel(client,data,log); releases+=int(rd); tags+=int(td)
        if _delete_manifest(client,game,channel,data,log): manifests+=1
    artwork=_delete_artwork(client,game,log)
    catalog["games"].remove(game)
    _commit_catalog(client,catalog,f"Delete {game['title']} completely")
    log("Game removed from catalog after all remote files were removed")
    return {"game_removed":True,"channels_removed":list(channels),"releases_deleted":releases,"tags_deleted":tags,"manifests_deleted":manifests,"artwork_deleted":artwork}
