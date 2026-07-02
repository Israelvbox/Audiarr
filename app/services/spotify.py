from typing import Optional
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

from app.config import settings


_client: Optional[spotipy.Spotify] = None


def get_client() -> spotipy.Spotify:
    global _client
    if _client is None:
        auth = SpotifyClientCredentials(
            client_id=settings.spotify_client_id,
            client_secret=settings.spotify_client_secret,
        )
        _client = spotipy.Spotify(auth_manager=auth)
    return _client


def search_artist(query: str, limit: int = 10, offset: int = 0) -> dict:
    sp = get_client()
    results = sp.search(q=query, type="artist", limit=limit, offset=offset)
    artists = []
    for a in results.get("artists", {}).get("items", []):
        artists.append({
            "id": a["id"],
            "name": a["name"],
            "image_url": a["images"][0]["url"] if a.get("images") else None,
            "genres": a.get("genres", []),
            "followers": a.get("followers", {}).get("total", 0),
        })
    total = results.get("artists", {}).get("total", 0)
    return {"items": artists, "total": total}


def get_artist(artist_id: str) -> Optional[dict]:
    sp = get_client()
    try:
        a = sp.artist(artist_id)
        return {
            "id": a["id"],
            "name": a["name"],
            "image_url": a["images"][0]["url"] if a.get("images") else None,
            "genres": a.get("genres", []),
        }
    except Exception:
        return None


def get_artist_albums(artist_id: str) -> list[dict]:
    sp = get_client()
    results = sp.artist_albums(artist_id, album_type="album,single", limit=50)
    albums = []
    for alb in results.get("items", []):
        if alb.get("id") in {a["id"] for a in albums}:
            continue
        albums.append({
            "id": alb["id"],
            "name": alb["name"],
            "year": alb["release_date"][:4] if alb.get("release_date") else None,
            "image_url": alb["images"][0]["url"] if alb.get("images") else None,
            "total_tracks": alb.get("total_tracks", 0),
        })
    return albums


def get_album_tracks(album_id: str) -> list[dict]:
    sp = get_client()
    results = sp.album_tracks(album_id, limit=50)
    tracks = []
    for t in results.get("items", []):
        isrc = None
        try:
            full = sp.track(t["id"])
            isrc = full.get("external_ids", {}).get("isrc")
        except Exception:
            pass
        tracks.append({
            "id": t["id"],
            "name": t["name"],
            "track_number": t.get("track_number"),
            "duration_ms": t.get("duration_ms"),
            "isrc": isrc,
            "preview_url": t.get("preview_url"),
        })
    return tracks


def search_tracks(query: str, limit: int = 10, offset: int = 0) -> dict:
    sp = get_client()
    results = sp.search(q=query, type="track", limit=limit, offset=offset)
    tracks = []
    for t in results.get("tracks", {}).get("items", []):
        tracks.append({
            "id": t["id"],
            "name": t["name"],
            "artists": [{"id": a["id"], "name": a["name"]} for a in t["artists"]],
            "album": {"id": t["album"]["id"], "name": t["album"]["name"], "image_url": t["album"]["images"][0]["url"] if t["album"].get("images") else None},
            "duration_ms": t.get("duration_ms"),
            "isrc": t.get("external_ids", {}).get("isrc"),
            "preview_url": t.get("preview_url"),
        })
    total = results.get("tracks", {}).get("total", 0)
    return {"items": tracks, "total": total}


def get_album(album_id: str) -> Optional[dict]:
    sp = get_client()
    try:
        alb = sp.album(album_id)
        return {
            "id": alb["id"],
            "name": alb["name"],
            "year": alb["release_date"][:4] if alb.get("release_date") else None,
            "image_url": alb["images"][0]["url"] if alb.get("images") else None,
            "total_tracks": alb.get("total_tracks", 0),
            "artists": [{"id": a["id"], "name": a["name"]} for a in alb["artists"]],
        }
    except Exception:
        return None


def get_artist_top_tracks(artist_id: str) -> list[dict]:
    sp = get_client()
    try:
        results = sp.artist_top_tracks(artist_id)
        tracks = []
        for t in results.get("tracks", []):
            tracks.append({
                "id": t["id"],
                "name": t["name"],
                "album_id": t["album"]["id"],
                "album_name": t["album"]["name"],
                "album_image": t["album"]["images"][0]["url"] if t["album"].get("images") else None,
                "track_number": t.get("track_number"),
                "duration_ms": t.get("duration_ms"),
                "isrc": t.get("external_ids", {}).get("isrc") if "external_ids" in t else None,
                "preview_url": t.get("preview_url"),
            })
        return tracks
    except Exception:
        return []


def search_playlists(query: str, limit: int = 10, offset: int = 0) -> dict:
    sp = get_client()
    results = sp.search(q=query, type="playlist", limit=limit, offset=offset)
    playlists = []
    for p in results.get("playlists", {}).get("items", []):
        if not p:
            continue
        playlists.append({
            "id": p["id"],
            "name": p["name"],
            "description": p.get("description", ""),
            "image_url": p["images"][0]["url"] if p.get("images") else None,
            "owner": p["owner"]["display_name"] if p.get("owner") else None,
            "tracks_total": p.get("tracks", {}).get("total", 0),
        })
    total = results.get("playlists", {}).get("total", 0)
    return {"items": playlists, "total": total}


def extract_playlist_id(url_or_id: str) -> str | None:
    import re
    m = re.search(r'(?:open\.spotify\.com/playlist/|spotify:playlist:)([a-zA-Z0-9]+)', url_or_id)
    if m:
        return m.group(1)
    if re.match(r'^[a-zA-Z0-9]{22}$', url_or_id):
        return url_or_id
    return None


def get_playlist_tracks(playlist_id: str) -> list[dict]:
    sp = get_client()
    try:
        results = sp.playlist_tracks(playlist_id, limit=100, market="US")
        tracks = []
        for item in results.get("items", []):
            t = item.get("track")
            if not t:
                continue
            tracks.append({
                "id": t["id"],
                "name": t["name"],
                "artists": [{"id": a["id"], "name": a["name"]} for a in t["artists"]],
                "album": {"id": t["album"]["id"], "name": t["album"]["name"], "image_url": t["album"]["images"][0]["url"] if t["album"].get("images") else None},
                "duration_ms": t.get("duration_ms"),
                "isrc": t.get("external_ids", {}).get("isrc") if "external_ids" in t else None,
                "preview_url": t.get("preview_url"),
            })
        return tracks
    except Exception:
        return []


def get_track(track_id: str) -> Optional[dict]:
    sp = get_client()
    try:
        t = sp.track(track_id)
        return {
            "id": t["id"],
            "name": t["name"],
            "album_id": t["album"]["id"],
            "album_name": t["album"]["name"],
            "album_image": t["album"]["images"][0]["url"] if t["album"].get("images") else None,
            "artists": [{"id": a["id"], "name": a["name"]} for a in t["artists"]],
            "track_number": t.get("track_number"),
            "duration_ms": t.get("duration_ms"),
            "isrc": t.get("external_ids", {}).get("isrc"),
            "preview_url": t.get("preview_url"),
        }
    except Exception:
        return None
