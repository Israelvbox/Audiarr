import sqlite3
from pathlib import Path
from typing import Optional

from app.config import settings


def get_connection() -> sqlite3.Connection:
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(settings.db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_connection()
    schema = (Path(__file__).parent / "schema.sql").read_text()
    conn.executescript(schema)
    # migration: add is_system column if missing
    cols = [r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
    if "is_system" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN is_system INTEGER NOT NULL DEFAULT 0")
    conn.commit()
    conn.close()


def artist_exists(normalized: str) -> bool:
    conn = get_connection()
    row = conn.execute(
        "SELECT 1 FROM artists WHERE normalized = ?", (normalized,)
    ).fetchone()
    conn.close()
    return row is not None


def save_artist(id: str, name: str, normalized: str, image_url: Optional[str] = None):
    conn = get_connection()
    conn.execute(
        """INSERT INTO artists (id, name, normalized, image_url) VALUES (?, ?, ?, ?)
           ON CONFLICT(id) DO UPDATE SET name=excluded.name, normalized=excluded.normalized, image_url=COALESCE(excluded.image_url, artists.image_url)""",
        (id, name, normalized, image_url),
    )
    conn.commit()
    conn.close()


def save_album(id: str, artist_id: str, title: str, year: Optional[int] = None, image_url: Optional[str] = None):
    conn = get_connection()
    conn.execute(
        "INSERT OR IGNORE INTO albums (id, artist_id, title, year, image_url) VALUES (?, ?, ?, ?, ?)",
        (id, artist_id, title, year, image_url),
    )
    conn.commit()
    conn.close()


def isrc_exists(isrc: str) -> bool:
    if not isrc:
        return False
    conn = get_connection()
    row = conn.execute(
        "SELECT 1 FROM tracks WHERE isrc = ?", (isrc,)
    ).fetchone()
    conn.close()
    return row is not None


def track_exists_by_isrc(isrc: str) -> Optional[str]:
    if not isrc:
        return None
    conn = get_connection()
    row = conn.execute(
        "SELECT id FROM tracks WHERE isrc = ?", (isrc,)
    ).fetchone()
    conn.close()
    return row["id"] if row else None


def track_downloaded_by_isrc(isrc: str) -> Optional[str]:
    if not isrc:
        return None
    conn = get_connection()
    row = conn.execute(
        "SELECT id FROM tracks WHERE isrc = ? AND downloaded = 1", (isrc,)
    ).fetchone()
    conn.close()
    return row["id"] if row else None


def save_track(
    id: str, album_id: str, title: str,
    track_number: Optional[int] = None,
    duration_ms: Optional[int] = None,
    isrc: Optional[str] = None,
    preview_url: Optional[str] = None,
):
    conn = get_connection()
    conn.execute(
        """INSERT OR IGNORE INTO tracks
           (id, album_id, title, track_number, duration_ms, isrc, preview_url)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (id, album_id, title, track_number, duration_ms, isrc, preview_url),
    )
    conn.commit()
    conn.close()


def mark_track_downloaded(track_id: str, file_path: str):
    conn = get_connection()
    conn.execute(
        "UPDATE tracks SET downloaded = 1, file_path = ? WHERE id = ?",
        (file_path, track_id),
    )
    conn.commit()
    conn.close()


def link_track_to_album(track_id: str, album_id: str):
    conn = get_connection()
    conn.execute(
        "UPDATE tracks SET album_id = ? WHERE id = ?",
        (album_id, track_id),
    )
    conn.commit()
    conn.close()


def get_artist(artist_id: str) -> Optional[dict]:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM artists WHERE id = ?", (artist_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_artist_albums(artist_id: str) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM albums WHERE artist_id = ? ORDER BY year", (artist_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_album_tracks(album_id: str) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM tracks WHERE album_id = ? ORDER BY track_number", (album_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def search_artists(query: str) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM artists WHERE normalized LIKE ?", (f"%{query}%",)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def all_artists() -> list[dict]:
    conn = get_connection()
    rows = conn.execute("SELECT * FROM artists ORDER BY name").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def check_downloaded_tracks(track_ids: list[str]) -> dict[str, bool]:
    if not track_ids:
        return {}
    placeholders = ",".join("?" for _ in track_ids)
    conn = get_connection()
    rows = conn.execute(
        f"SELECT id, downloaded FROM tracks WHERE id IN ({placeholders})", track_ids
    ).fetchall()
    conn.close()
    result = {r["id"]: bool(r["downloaded"]) for r in rows}
    for tid in track_ids:
        result.setdefault(tid, False)
    return result


def delete_track(track_id: str) -> Optional[str]:
    conn = get_connection()
    row = conn.execute("SELECT file_path FROM tracks WHERE id = ?", (track_id,)).fetchone()
    file_path = row["file_path"] if row else None
    conn.execute("DELETE FROM tracks WHERE id = ?", (track_id,))
    conn.commit()
    conn.close()
    return file_path


def delete_album(album_id: str) -> list[str]:
    conn = get_connection()
    rows = conn.execute("SELECT file_path FROM tracks WHERE album_id = ?", (album_id,)).fetchall()
    paths = [r["file_path"] for r in rows if r["file_path"]]
    conn.execute("DELETE FROM tracks WHERE album_id = ?", (album_id,))
    conn.execute("DELETE FROM albums WHERE id = ?", (album_id,))
    conn.commit()
    conn.close()
    return paths


def delete_artist(artist_id: str) -> list[str]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT t.file_path FROM tracks t JOIN albums a ON t.album_id = a.id WHERE a.artist_id = ?",
        (artist_id,),
    ).fetchall()
    paths = [r["file_path"] for r in rows if r["file_path"]]
    conn.execute("DELETE FROM tracks WHERE album_id IN (SELECT id FROM albums WHERE artist_id = ?)", (artist_id,))
    conn.execute("DELETE FROM albums WHERE artist_id = ?", (artist_id,))
    conn.execute("DELETE FROM artists WHERE id = ?", (artist_id,))
    conn.commit()
    conn.close()
    return paths


def clean_orphan_artists() -> list[str]:
    conn = get_connection()
    rows = conn.execute(
        """SELECT a.id, a.name FROM artists a
           LEFT JOIN albums al ON al.artist_id = a.id
           WHERE al.id IS NULL"""
    ).fetchall()
    removed = []
    for r in rows:
        conn.execute("DELETE FROM artists WHERE id = ?", (r["id"],))
        removed.append(r["name"])
    conn.commit()
    conn.close()
    return removed


def sync_downloaded_files(download_dir: str) -> dict:
    conn = get_connection()
    rows = conn.execute("SELECT id, file_path FROM tracks WHERE downloaded = 1").fetchall()
    lost = 0
    restored = 0
    for r in rows:
        if r["file_path"] and not Path(r["file_path"]).exists():
            conn.execute("UPDATE tracks SET downloaded = 0, file_path = NULL WHERE id = ?", (r["id"],))
            lost += 1
    conn.commit()

    # Also restore downloaded=1 if file_path exists but downloaded=0
    rows2 = conn.execute("SELECT id, file_path FROM tracks WHERE downloaded = 0 AND file_path IS NOT NULL").fetchall()
    for r in rows2:
        if r["file_path"] and Path(r["file_path"]).exists():
            conn.execute("UPDATE tracks SET downloaded = 1 WHERE id = ?", (r["id"],))
            restored += 1
    conn.commit()
    conn.close()
    return {"lost": lost, "restored": restored}


def get_setting(key: str, default: str = "") -> str:
    conn = get_connection()
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else default


def set_setting(key: str, value: str):
    conn = get_connection()
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    conn.commit()
    conn.close()
    return value


def create_user(username: str, password: str, role: str = "user", is_system: int = 0) -> dict:
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO users (username, password, role, is_system) VALUES (?, ?, ?, ?)",
            (username, password, role, is_system),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        return dict(row) if row else None
    except Exception as e:
        conn.close()
        raise e
    finally:
        conn.close()


def get_user_by_username(username: str) -> Optional[dict]:
    conn = get_connection()
    row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_id(user_id: int) -> Optional[dict]:
    conn = get_connection()
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def user_exists(username: str) -> bool:
    conn = get_connection()
    row = conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone()
    conn.close()
    return row is not None


def list_admins() -> list[dict]:
    conn = get_connection()
    rows = conn.execute("SELECT id, username, role, is_system FROM users WHERE role = 'admin'").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def has_content() -> bool:
    """Check if the DB has been used (has artists/albums/tracks)."""
    conn = get_connection()
    row = conn.execute("SELECT 1 FROM artists LIMIT 1").fetchone()
    conn.close()
    return row is not None


def count_admins() -> int:
    conn = get_connection()
    row = conn.execute("SELECT COUNT(*) AS cnt FROM users WHERE role = 'admin'").fetchone()
    conn.close()
    return row["cnt"] if row else 0


def count_users() -> int:
    conn = get_connection()
    row = conn.execute("SELECT COUNT(*) AS cnt FROM users").fetchone()
    conn.close()
    return row["cnt"] if row else 0


def list_users() -> list[dict]:
    conn = get_connection()
    rows = conn.execute("SELECT id, username, role, is_system, created_at FROM users ORDER BY id").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_user_role(user_id: int, role: str) -> Optional[dict]:
    conn = get_connection()
    conn.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
    conn.commit()
    row = conn.execute("SELECT id, username, role, is_system, created_at FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def delete_user(user_id: int) -> bool:
    conn = get_connection()
    cur = conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    deleted = cur.rowcount > 0
    conn.commit()
    conn.close()
    return deleted
