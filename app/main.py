import logging
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Form, Body, Depends
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

from app.config import settings
from app.database import db
from app.database.models import QueueItem
from app.queue import queue
from app.services import normalizer, spotify
from app.auth import (
    hash_password, verify_password, create_access_token,
    get_current_user, require_admin, verify_admin_api_key,
)

logger = logging.getLogger(__name__)


def seed_default_user():
    if db.get_setting("system_admin_created", "") == "":
        existing = [a for a in db.list_admins() if a["is_system"]]
        if existing:
            db.set_setting("system_admin_created", "true")
        elif db.has_content() or db.count_users() > 1:
            db.set_setting("system_admin_created", "true")
    if db.get_setting("system_admin_created", "false") != "true":
        password = secrets.token_urlsafe(12)
        db.create_user("admin", hash_password(password), role="admin", is_system=1)
        db.set_setting("system_admin_created", "true")
        logger.warning("═" * 50)
        logger.warning("NO ADMIN USERS FOUND. AUTO-GENERATED ADMIN:")
        logger.warning("  Username: admin")
        logger.warning("  Password: %s", password)
        logger.warning("Log in, create another admin user, then delete this one (recommended).")
        logger.warning("═" * 50)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    # Cargar download_dir desde DB (si existe)
    dd = db.get_setting("download_dir", "")
    if dd:
        settings.download_dir = Path(dd)
    elif not getattr(settings, "download_dir", None) or str(settings.download_dir) == ".":
        settings.download_dir = Path("")
    seed_default_user()
    db.clean_orphan_artists()
    await queue.start()
    yield
    await queue.stop()


app = FastAPI(title="Audiarr", lifespan=lifespan)

static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/", response_class=HTMLResponse)
def index():
    return (static_dir / "index.html").read_text(encoding="utf-8")


@app.get("/login", response_class=HTMLResponse)
def login_page():
    return (static_dir / "login.html").read_text(encoding="utf-8")


# ── Auth ─────────────────────────────────────────────────

@app.post("/api/auth/register")
def register(username: str = Body(...), password: str = Body(...), role: str = Body("user"),
             _: bool = Depends(verify_admin_api_key)):
    if not username or not password:
        raise HTTPException(400, "Username and password required")
    if role not in ("admin", "user"):
        raise HTTPException(400, "Role must be 'admin' or 'user'")
    if db.user_exists(username):
        raise HTTPException(409, "Username already exists")
    user = db.create_user(username, hash_password(password), role)
    return {"id": user["id"], "username": user["username"], "role": user["role"]}


@app.post("/api/auth/login")
def login(username: str = Body(...), password: str = Body(...)):
    user = db.get_user_by_username(username)
    if not user or not verify_password(password, user["password"]):
        raise HTTPException(401, "Invalid credentials")
    token = create_access_token({"sub": user["username"], "role": user["role"]})
    return {"access_token": token, "token_type": "bearer", "username": user["username"], "role": user["role"]}


@app.get("/api/auth/me")
def me(user: dict = Depends(get_current_user)):
    return {"id": user["id"], "username": user["username"], "role": user["role"]}


# ── Admin ─────────────────────────────────────────────────

@app.get("/api/admin/users")
def admin_list_users(_=Depends(require_admin)):
    return db.list_users()


@app.post("/api/admin/users")
def admin_create_user(username: str = Body(...), password: str = Body(...), role: str = Body("user"), _=Depends(require_admin)):
    if not username or not password:
        raise HTTPException(400, "Username and password required")
    if role not in ("admin", "user"):
        raise HTTPException(400, "Role must be 'admin' or 'user'")
    if db.user_exists(username):
        raise HTTPException(409, "Username already exists")
    user = db.create_user(username, hash_password(password), role)
    return {"id": user["id"], "username": user["username"], "role": user["role"], "is_system": user["is_system"]}


@app.put("/api/admin/users/{user_id}/role")
def admin_update_role(user_id: int, body: dict = Body(...), current_user: dict = Depends(require_admin)):
    role = body.get("role", "")
    if role not in ("admin", "user"):
        raise HTTPException(400, "Role must be 'admin' or 'user'")
    if user_id == current_user["id"]:
        raise HTTPException(400, "Cannot change your own role")
    target = db.get_user_by_id(user_id)
    if not target:
        raise HTTPException(404, "User not found")
    if target["role"] == "admin" and role == "user" and db.count_admins() <= 1:
        raise HTTPException(400, "Cannot demote the last admin")
    user = db.update_user_role(user_id, role)
    return user


@app.delete("/api/admin/users/{user_id}")
def admin_delete_user(user_id: int, current_user: dict = Depends(require_admin)):
    if user_id == current_user["id"]:
        raise HTTPException(400, "Cannot delete yourself")
    target = db.get_user_by_id(user_id)
    if not target:
        raise HTTPException(404, "User not found")
    if target["role"] == "admin" and db.count_admins() <= 1:
        raise HTTPException(400, "Cannot delete the last admin")
    db.delete_user(user_id)
    return {"deleted": True}


# ── Search ──────────────────────────────────────────────

@app.get("/api/search/artists")
def search_artists(q: str, limit: int = 10, offset: int = 0, _=Depends(get_current_user)):
    result = spotify.search_artist(q, limit=limit, offset=offset)
    for r in result["items"]:
        r["normalized"] = normalizer.normalize_name(r["name"])
    return result


@app.get("/api/search/tracks")
def search_tracks(q: str, limit: int = 10, offset: int = 0, _=Depends(get_current_user)):
    return spotify.search_tracks(q, limit=limit, offset=offset)


@app.get("/api/search/playlists")
def search_playlists(q: str, limit: int = 10, offset: int = 0, _=Depends(get_current_user)):
    return spotify.search_playlists(q, limit=limit, offset=offset)


# ── Artist ───────────────────────────────────────────────

@app.get("/api/artists/{artist_id}")
def get_artist(artist_id: str, _=Depends(get_current_user)):
    sp_artist = spotify.get_artist(artist_id)
    if not sp_artist:
        raise HTTPException(404, "Artist not found")
    return sp_artist


@app.get("/api/artists/{artist_id}/albums")
def get_artist_albums(artist_id: str, _=Depends(get_current_user)):
    return spotify.get_artist_albums(artist_id)


@app.get("/api/artists/{artist_id}/top-tracks")
def get_artist_top_tracks(artist_id: str, _=Depends(get_current_user)):
    return spotify.get_artist_top_tracks(artist_id)


# ── Album ────────────────────────────────────────────────

@app.get("/api/albums/{album_id}/tracks")
def get_album_tracks(album_id: str, _=Depends(get_current_user)):
    return spotify.get_album_tracks(album_id)


# ── Playlist ─────────────────────────────────────────────

@app.get("/api/playlists/{playlist_id}/tracks")
def get_playlist_tracks(playlist_id: str, _=Depends(get_current_user)):
    return spotify.get_playlist_tracks(playlist_id)


@app.post("/api/playlist/parse")
def parse_playlist(url: str = Form(default=None), url_q: str = Query(default=None, alias="url"), _=Depends(get_current_user)):
    url = url or url_q
    if not url:
        raise HTTPException(400, "url parameter is required")
    pid = spotify.extract_playlist_id(url)
    if not pid:
        raise HTTPException(400, "Invalid Spotify playlist URL or ID")
    tracks = spotify.get_playlist_tracks(pid)
    return {"playlist_id": pid, "tracks": tracks, "total": len(tracks)}


# ── Download ─────────────────────────────────────────────

def _is_track_downloaded(t: dict) -> bool:
    isrc = t.get("isrc") or t.get("track", {}).get("isrc")
    if isrc:
        if db.track_downloaded_by_isrc(isrc):
            return True
    tid = t.get("id") or t.get("track", {}).get("id")
    if tid:
        checked = db.check_downloaded_tracks([tid])
        return checked.get(tid, False)
    return False


async def _enqueue_track(t: dict, artist_name: str, artist_id: str | None, album_title: str, album_year: int | None, album_id: str, artwork_url: str | None = None):
    db.save_track(
        id=t["id"], album_id=album_id, title=t["name"],
        track_number=t.get("track_number"), duration_ms=t.get("duration_ms"),
        isrc=t.get("isrc"), preview_url=t.get("preview_url"),
    )
    item = QueueItem(
        track_id=t["id"], album_id=album_id,
        artist_name=artist_name, album_title=album_title,
        album_year=album_year, track_title=t["name"],
        track_number=t.get("track_number"), isrc=t.get("isrc"),
        artwork_url=artwork_url,
    )
    await queue.enqueue(item)


def _require_download_dir():
    if not settings.download_dir or not str(settings.download_dir).strip():
        raise HTTPException(400, "No download directory configured. Admin must set it in Settings.")
    return settings.download_dir


@app.post("/api/download/album")
async def download_album(album_id: str, artist_id: str, _=Depends(get_current_user), __=Depends(_require_download_dir)):
    sp_artist = spotify.get_artist(artist_id)
    if not sp_artist:
        raise HTTPException(404, "Artist not found")
    sp_albums = spotify.get_artist_albums(artist_id)
    album = next((a for a in sp_albums if a["id"] == album_id), None)
    if not album:
        raise HTTPException(404, "Album not found")
    tracks = spotify.get_album_tracks(album_id)
    artist_norm = normalizer.normalize_name(sp_artist["name"])
    db.save_artist(sp_artist["id"], sp_artist["name"], artist_norm, sp_artist.get("image_url"))
    sp_album_full = spotify.get_album(album_id)
    album_year = (sp_album_full or album).get("year")
    album_artwork = (sp_album_full or album).get("image_url")
    db.save_album(album_id, artist_id, album["name"], album_year, album_artwork)
    enqueued = 0
    for t in tracks:
        if _is_track_downloaded(t):
            continue
        await _enqueue_track(t, sp_artist["name"], artist_id, album["name"], album_year, album_id, album_artwork)
        enqueued += 1
    return {"enqueued": enqueued, "total": len(tracks), "skipped": len(tracks) - enqueued}


@app.post("/api/download/track")
async def download_track(track_id: str, _=Depends(get_current_user), __=Depends(_require_download_dir)):
    sp_track = spotify.get_track(track_id)
    if not sp_track:
        raise HTTPException(404, "Track not found")
    if _is_track_downloaded(sp_track):
        return {"enqueued": 0, "skipped": 1}
    main_artist = sp_track["artists"][0]
    artist_norm = normalizer.normalize_name(main_artist["name"])
    album_id = sp_track["album_id"]
    album_name = sp_track["album_name"]
    sp_album = spotify.get_album(album_id)
    album_year = sp_album.get("year") if sp_album else None
    album_artwork = sp_album.get("image_url") if sp_album else sp_track.get("album_image")
    db.save_artist(main_artist["id"], main_artist["name"], artist_norm, sp_track.get("album_image"))
    db.save_album(album_id, main_artist["id"], album_name, year=album_year, image_url=album_artwork)
    await _enqueue_track(
        {"id": sp_track["id"], "name": sp_track["name"],
         "track_number": sp_track.get("track_number"), "duration_ms": sp_track.get("duration_ms"),
         "isrc": sp_track.get("isrc"), "preview_url": sp_track.get("preview_url")},
        main_artist["name"], main_artist["id"], album_name, album_year, album_id, album_artwork,
    )
    return {"enqueued": 1}


@app.post("/api/download/playlist")
async def download_playlist(playlist_id: str = Query(...), track_ids: str = Query(""), _=Depends(get_current_user), __=Depends(_require_download_dir)):
    tracks = spotify.get_playlist_tracks(playlist_id)
    if not tracks:
        raise HTTPException(404, "Playlist not found or empty")
    if track_ids:
        selected = {tid for tid in track_ids.split(",") if tid}
        tracks = [t for t in tracks if t["id"] in selected]
        if not tracks:
            raise HTTPException(400, "No valid tracks selected")
    _album_cache: dict[str, dict] = {}
    enqueued = 0
    for t in tracks:
        if _is_track_downloaded(t):
            continue
        main_artist = t["artists"][0]
        artist_norm = normalizer.normalize_name(main_artist["name"])
        album_id = t["album"]["id"]
        if album_id not in _album_cache:
            sp_album = spotify.get_album(album_id)
            _album_cache[album_id] = {
                "year": sp_album.get("year") if sp_album else None,
                "image_url": sp_album.get("image_url") if sp_album else t["album"].get("image_url"),
            }
        album_info = _album_cache[album_id]
        db.save_artist(main_artist["id"], main_artist["name"], artist_norm, t["album"].get("image_url"))
        db.save_album(album_id, main_artist["id"], t["album"]["name"], year=album_info["year"], image_url=album_info["image_url"])
        await _enqueue_track(t, main_artist["name"], main_artist["id"], t["album"]["name"], album_info["year"], album_id, album_info["image_url"])
        enqueued += 1
    return {"enqueued": enqueued, "total": len(tracks), "skipped": len(tracks) - enqueued}


# ── Library ──────────────────────────────────────────────

@app.get("/api/library/artists")
def library_artists(_=Depends(get_current_user)):
    return db.all_artists()


@app.get("/api/library/artists/{artist_id}/albums")
def library_artist_albums(artist_id: str, _=Depends(get_current_user)):
    return db.get_artist_albums(artist_id)


@app.get("/api/library/albums/{album_id}/tracks")
def library_album_tracks(album_id: str, _=Depends(get_current_user)):
    return db.get_album_tracks(album_id)


@app.get("/api/library/check-tracks")
def check_tracks(ids: str = Query(..., description="Comma-separated track IDs"), _=Depends(get_current_user)):
    return db.check_downloaded_tracks([tid for tid in ids.split(",") if tid])


# ── Delete ───────────────────────────────────────────────

@app.delete("/api/library/tracks/{track_id}")
def delete_track(track_id: str, _=Depends(require_admin)):
    path = db.delete_track(track_id)
    if path:
        Path(path).unlink(missing_ok=True)
        _remove_empty_parents(Path(path))
    return {"deleted": True}


@app.delete("/api/library/albums/{album_id}")
def delete_album(album_id: str, _=Depends(require_admin)):
    paths = db.delete_album(album_id)
    dirs = set()
    for p in paths:
        fp = Path(p)
        fp.unlink(missing_ok=True)
        dirs.add(fp.parent)
    for d in dirs:
        if d.exists():
            import shutil
            shutil.rmtree(d, ignore_errors=True)
    db.clean_orphan_artists()
    return {"deleted": len(paths)}


@app.delete("/api/library/artists/{artist_id}")
def delete_artist(artist_id: str, _=Depends(require_admin)):
    paths = db.delete_artist(artist_id)
    dirs = set()
    for p in paths:
        fp = Path(p)
        fp.unlink(missing_ok=True)
        dirs.add(fp.parent.parent)
    for d in dirs:
        if d.exists():
            import shutil
            shutil.rmtree(d, ignore_errors=True)
    return {"deleted": len(paths)}


def _remove_empty_parents(fp: Path):
    parent = fp.parent
    while parent != parent.parent:
        try:
            if any(parent.iterdir()):
                break
            parent.rmdir()
            parent = parent.parent
        except OSError:
            break


# ── Sync ─────────────────────────────────────────────────

@app.post("/api/library/sync")
def sync_library(_=Depends(require_admin)):
    result = db.sync_downloaded_files(str(settings.download_dir))
    orphans = db.clean_orphan_artists()
    result.setdefault("lost", 0)
    result.setdefault("restored", 0)
    result["orphans_removed"] = orphans
    return result


# ── Settings ─────────────────────────────────────────────

@app.get("/api/settings")
def get_settings(_=Depends(require_admin)):
    return {
        "download_dir": db.get_setting("download_dir", ""),
        "monitor_enabled": db.get_setting("monitor_enabled", "true"),
    }


@app.post("/api/settings")
def update_settings(download_dir: str = Form(default=None), monitor_enabled: str = Form(default=None), _=Depends(require_admin)):
    if download_dir is not None:
        if download_dir.strip() == "":
            raise HTTPException(400, "download_dir cannot be empty")
        db.set_setting("download_dir", download_dir)
        settings.download_dir = Path(download_dir)
        settings.download_dir.mkdir(parents=True, exist_ok=True)
    if monitor_enabled is not None:
        db.set_setting("monitor_enabled", monitor_enabled)
    return get_settings()


# ── Queue ────────────────────────────────────────────────

@app.get("/api/queue/status")
def queue_status(_=Depends(get_current_user)):
    queue.clear_completed(max_age=120)
    return {"pending": queue.pending_count(), "items": queue.get_status_list()}


# ── Music serving ────────────────────────────────────────

@app.get("/music/{path:path}")
def serve_music(path: str, _=Depends(get_current_user)):
    file_path = settings.download_dir / path
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(404)
    return FileResponse(str(file_path))
