import logging
from pathlib import Path
from typing import Optional

import mutagen
import mutagen.id3
import mutagen.mp3
import requests

logger = logging.getLogger(__name__)

_TAG_MAP = {
    "title": "TIT2",
    "artist": "TPE1",
    "album": "TALB",
    "album_artist": "TPE2",
    "track_number": "TRCK",
    "year": "TDRC",
    "genre": "TCON",
}


def _ensure_id3(music_file: mutagen.FileType) -> mutagen.id3.ID3:
    if isinstance(music_file, mutagen.mp3.MP3):
        if music_file.tags is None:
            music_file.add_tags()
        return music_file.tags
    if isinstance(music_file, mutagen.FileType):
        try:
            return mutagen.id3.ID3(music_file.filename)
        except mutagen.id3.ID3NoHeaderError:
            return mutagen.id3.ID3(music_file.filename)
    raise ValueError(f"Unsupported format: {type(music_file)}")


def write_tags(
    file_path: Path,
    title: str,
    artist: str,
    album: str,
    track_number: Optional[int] = None,
    year: Optional[int] = None,
    genre: Optional[str] = None,
    album_artist: Optional[str] = None,
    artwork_url: Optional[str] = None,
) -> None:
    if not file_path.exists():
        logger.warning("File not found, skipping tags: %s", file_path)
        return

    try:
        audio = mutagen.File(file_path, easy=False)
        if audio is None:
            logger.warning("mutagen could not read %s, skipping tags", file_path)
            return
    except Exception as e:
        logger.warning("mutagen error reading %s: %s", file_path, e)
        return

    tags = _ensure_id3(audio)

    frame_map = {
        "TIT2": mutagen.id3.TIT2(encoding=3, text=title),
        "TPE1": mutagen.id3.TPE1(encoding=3, text=artist),
        "TALB": mutagen.id3.TALB(encoding=3, text=album),
        "TPE2": mutagen.id3.TPE2(encoding=3, text=album_artist or artist),
    }
    if track_number is not None:
        frame_map["TRCK"] = mutagen.id3.TRCK(encoding=3, text=str(track_number))
    if year is not None:
        frame_map["TDRC"] = mutagen.id3.TDRC(encoding=3, text=str(year))
    if genre:
        frame_map["TCON"] = mutagen.id3.TCON(encoding=3, text=genre)

    for tag, frame in frame_map.items():
        try:
            tags[tag] = frame
        except Exception as e:
            logger.debug("Failed to set %s: %s", tag, e)

    if artwork_url:
        try:
            resp = requests.get(artwork_url, timeout=10)
            if resp.status_code == 200:
                mime = resp.headers.get("Content-Type", "image/jpeg")
                tags["APIC"] = mutagen.id3.APIC(
                    encoding=3,
                    mime=mime,
                    type=3,
                    desc="Cover",
                    data=resp.content,
                )
        except Exception as e:
            logger.debug("Failed to download artwork: %s", e)

    try:
        tags.save(file_path)
        logger.info("Tags written: %s", file_path)
    except Exception as e:
        logger.warning("Failed to save tags to %s: %s", file_path, e)
