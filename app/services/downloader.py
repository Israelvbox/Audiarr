import asyncio
import logging
import shutil
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from app.config import settings
from app.database.models import QueueItem
from app.services.normalizer import sanitize_path_component
from app.services.tagger import write_tags

logger = logging.getLogger(__name__)


class DownloadError(Exception):
    pass


_VENV_BIN = Path(__file__).parent.parent.parent / ".venv" / "bin"


class DownloadEngine(ABC):
    @abstractmethod
    async def download(self, item: QueueItem, output_dir: Path) -> Optional[Path]:
        ...


class YtDlpEngine(DownloadEngine):
    def _bin(self) -> str:
        return str(_VENV_BIN / "yt-dlp")

    async def download(self, item: QueueItem, output_dir: Path) -> Optional[Path]:
        search_query = f"{item.artist_name} - {item.track_title}"
        output_template = str(output_dir / "%(title)s.%(ext)s")

        cmd = [
            self._bin(),
            "--extract-audio",
            "--audio-format", "mp3",
            "--audio-quality", "320k",
            "--output", output_template,
            "--no-playlist",
            "--no-warnings",
            "--rm-cache-dir",
            f"ytsearch1:{search_query}",
        ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()

            if proc.returncode != 0:
                logger.warning("yt-dlp failed: %s", stderr.decode()[:500])
                return None

            for f in output_dir.iterdir():
                if f.is_file() and f.suffix in (".mp3", ".flac", ".m4a", ".opus"):
                    return f
            return None
        except Exception as e:
            logger.warning("yt-dlp exception: %s", e)
            return None


class SpotDlEngine(DownloadEngine):
    def _bin(self) -> str:
        return str(_VENV_BIN / "spotdl")

    async def download(self, item: QueueItem, output_dir: Path) -> Optional[Path]:
        spotify_url = f"https://open.spotify.com/track/{item.track_id}"
        cmd = [
            self._bin(),
            spotify_url,
            "--output", f"{output_dir}/{{artist}} - {{title}}.{{output_ext}}",
            "--log-level", "ERROR",
        ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()

            if proc.returncode != 0:
                logger.warning("spotdl failed: %s", stderr.decode()[:300])
                return None

            for f in output_dir.iterdir():
                if f.is_file() and f.suffix in (".mp3", ".flac", ".m4a", ".opus"):
                    return f
            return None
        except Exception as e:
            logger.warning("spotdl exception: %s", e)
            return None


class DownloadManager:
    def __init__(self):
        self._engines: list[DownloadEngine] = [SpotDlEngine(), YtDlpEngine()]

    async def download_track(self, item: QueueItem) -> Optional[Path]:
        album_dir = self._build_album_path(item)
        album_dir.mkdir(parents=True, exist_ok=True)
        temp_dir = settings.temp_dir / item.track_id
        temp_dir.mkdir(parents=True, exist_ok=True)
        shutil.rmtree(temp_dir)

        downloaded = None
        for engine in self._engines:
            logger.info("Trying %s for %s - %s", type(engine).__name__, item.artist_name, item.track_title)
            temp_dir.mkdir(parents=True, exist_ok=True)
            try:
                result = await engine.download(item, temp_dir)
                if result and result.exists():
                    downloaded = result
                    break
            except Exception as e:
                logger.exception("Engine %s error: %s", type(engine).__name__, e)

        if downloaded is None:
            shutil.rmtree(temp_dir, ignore_errors=True)
            return None

        dest = album_dir / self._build_filename(item, downloaded.suffix)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(downloaded), str(dest))
        shutil.rmtree(temp_dir, ignore_errors=True)
        logger.info("Saved: %s", dest)

        # Escribir tags ID3 para que Jellyfin reconozca el artista/álbum/pista
        try:
            write_tags(
                file_path=dest,
                title=item.track_title,
                artist=item.artist_name,
                album=item.album_title,
                track_number=item.track_number,
                year=item.album_year,
                artwork_url=item.artwork_url,
            )
        except Exception as e:
            logger.warning("Failed to write tags for %s: %s", dest, e)

        return dest

    def _build_album_path(self, item: QueueItem) -> Path:
        artist_norm = self._slugify(item.artist_name)
        album_label = f"{item.album_year} - {item.album_title}" if item.album_year else item.album_title
        album_norm = self._slugify(album_label)
        return settings.download_dir / artist_norm / album_norm

    def _build_filename(self, item: QueueItem, ext: str) -> str:
        track_num = f"{item.track_number:02d} " if item.track_number else ""
        return f"{track_num}{self._slugify(item.track_title)}{ext}"

    @staticmethod
    def _slugify(text: str) -> str:
        return sanitize_path_component(text)


manager = DownloadManager()
