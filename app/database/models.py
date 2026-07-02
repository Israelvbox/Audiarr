from dataclasses import dataclass
from typing import Optional


@dataclass
class Artist:
    id: str
    name: str
    normalized: str
    image_url: Optional[str] = None


@dataclass
class Album:
    id: str
    artist_id: str
    title: str
    year: Optional[int] = None
    image_url: Optional[str] = None


@dataclass
class Track:
    id: str
    album_id: str
    title: str
    track_number: Optional[int] = None
    duration_ms: Optional[int] = None
    isrc: Optional[str] = None
    preview_url: Optional[str] = None
    file_path: Optional[str] = None
    downloaded: bool = False


@dataclass
class QueueItem:
    track_id: str
    album_id: str
    artist_name: str
    album_title: str
    album_year: Optional[int]
    track_title: str
    track_number: Optional[int]
    isrc: Optional[str]
    artwork_url: Optional[str] = None
