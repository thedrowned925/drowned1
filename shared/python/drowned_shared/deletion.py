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


def _other_channel_refs(catalog:dict, target_game:dict, removed_channels:set[str])->tuple[set[str],set[str]]:
    tags=set(); manifests=set()
    for game in catalog.get("games",[]):
        for channel,data in (game.get("channels") or {}).items():
            if game is target_game and channel in removed_channels:
                continue
            tag=data.get("tag")
            if tag: tags.add(tag)
            path=data.get("manifest_path")
            if path: manifests.add(path)
    return tags,manifests


def _other_artwork_urls(catalog:dict,target_game:dict)->set[str]:
    urls=set()
    for game in catalog.get("games",[]):
        if game is target_game: continue
        for url in (game.get("artwork") or {}).values():
            if url: urls.add(url)
    return urls


def _delete_release_for_channel(client, data:dict, log, protected_tags:set[str]):
    tag=data.get("tag")
    if not tag: raise ValueError("catalog channel has no release tag")
    if tag in protected_tags:
        log(f"Shared Release/tag retained because another catalog entry still references it: {tag}")
        return False,False
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


def _delete_manifest(client, game:dict, channel:str, data:dict, log, protected_paths:set[str]):
    path=data.get("manifest_path") or manifest_repo_path(game["platform"],game["id"],channel,data.get("version","unknown"))
    if path in protected_paths:
        log(f"Shared raw manifest retained because another catalog entry still references it: {path}")
        return False
    if client.delete_repo_file(path,f"Delete {game['title']} {channel} manifest"):
        log(f"Deleted raw manifest: {path}")
        return True
    log(f"Manifest already absent: {path}")
    return False


def _delete_artwork(client, catalog:dict, game:dict, log):
    deleted=[]; protected_urls=_other_artwork_urls(catalog,game)
    for kind,url in list((game.get("artwork") or {}).items()):
        if url in protected_urls:
            log(f"Shared artwork retained because another catalog entry still references it ({kind})")
            continue
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
    Resources still referenced by another catalog entry are retained.
    """
    catalog=load_catalog(client); game=_find_game(catalog,game_id,platform)
    channels=game.get("channels") or {}
    if channel not in channels: raise KeyError(f"channel not found: {channel}")
    protected_tags,protected_paths=_other_channel_refs(catalog,game,{channel})
    data=dict(channels[channel]); releases=0; tags=0; manifests=0; artwork=[]
    rd,td=_delete_release_for_channel(client,data,log,protected_tags); releases+=int(rd); tags+=int(td)
    if _delete_manifest(client,game,channel,data,log,protected_paths): manifests+=1
    del channels[channel]
    removed_game=False
    if not channels:
        artwork=_delete_artwork(client,catalog,game,log)
        catalog["games"].remove(game); removed_game=True
    else:
        game["channels"]=channels
    _commit_catalog(client,catalog,f"Delete {game['title']} {channel}")
    log("Catalog updated after remote cleanup completed")
    return {"game_removed":removed_game,"channels_removed":[channel],"releases_deleted":releases,"tags_deleted":tags,"manifests_deleted":manifests,"artwork_deleted":artwork}


def delete_game(client, game_id:str, platform:str, log=print)->dict:
    """Delete all unshared releases/tags/manifests/artwork and finally the game row.

    If a network/API failure occurs mid-operation, the catalog is intentionally
    left untouched. Re-running is safe because missing remote resources are
    treated as already deleted. Resources referenced by other catalog entries
    are retained instead of breaking those entries.
    """
    catalog=load_catalog(client); game=_find_game(catalog,game_id,platform)
    channels=dict(game.get("channels") or {})
    protected_tags,protected_paths=_other_channel_refs(catalog,game,set(channels))
    releases=0; tags=0; manifests=0
    for channel,data in channels.items():
        rd,td=_delete_release_for_channel(client,data,log,protected_tags); releases+=int(rd); tags+=int(td)
        if _delete_manifest(client,game,channel,data,log,protected_paths): manifests+=1
    artwork=_delete_artwork(client,catalog,game,log)
    catalog["games"].remove(game)
    _commit_catalog(client,catalog,f"Delete {game['title']} completely")
    log("Game removed from catalog after remote cleanup completed")
    return {"game_removed":True,"channels_removed":list(channels),"releases_deleted":releases,"tags_deleted":tags,"manifests_deleted":manifests,"artwork_deleted":artwork}
