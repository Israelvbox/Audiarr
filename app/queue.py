import asyncio
import logging
import time
from pathlib import Path
from typing import Optional

from app.config import settings
from app.database import db
from app.database.models import QueueItem
from app.services.downloader import manager as download_manager

logger = logging.getLogger(__name__)


class DownloadQueue:
    def __init__(self):
        self._queue: asyncio.Queue[QueueItem] = asyncio.Queue()
        self._worker_task: asyncio.Task | None = None
        self._status: dict[str, dict] = {}

    async def start(self):
        settings.temp_dir.mkdir(parents=True, exist_ok=True)
        settings.download_dir.mkdir(parents=True, exist_ok=True)
        self._worker_task = asyncio.create_task(self._worker_loop())
        logger.info("Download queue worker started")

    async def stop(self):
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

    def _set_status(self, track_id: str, status: str, item: Optional[QueueItem] = None, **kwargs):
        entry = self._status.get(track_id, {})
        entry["status"] = status
        entry["updated_at"] = time.time()
        if item:
            entry["track_title"] = item.track_title
            entry["artist_name"] = item.artist_name
            entry["album_title"] = item.album_title
        entry.update(kwargs)
        self._status[track_id] = entry

    async def enqueue(self, item: QueueItem):
        self._set_status(item.track_id, "queued", item=item)
        await self._queue.put(item)
        logger.info("Enqueued: %s - %s", item.artist_name, item.track_title)

    async def _worker_loop(self):
        while True:
            item = await self._queue.get()
            self._set_status(item.track_id, "downloading", item=item)
            try:
                await self._process(item)
            except Exception as e:
                logger.exception("Failed to process %s: %s", item.track_id, e)
                self._set_status(item.track_id, "failed", item=item, error=str(e))
            finally:
                self._queue.task_done()

    async def _process(self, item: QueueItem):
        if item.isrc:
            existing = db.track_downloaded_by_isrc(item.isrc)
            if existing:
                logger.info("ISRC %s ya descargado, vinculando track %s al álbum %s", item.isrc, existing, item.album_id)
                db.link_track_to_album(existing, item.album_id)
                self._set_status(item.track_id, "completed", item=item, linked=True)
                return

        result = await download_manager.download_track(item)
        if result:
            db.mark_track_downloaded(item.track_id, str(result))
            logger.info("Downloaded: %s", result)
            self._set_status(item.track_id, "completed", item=item, file_path=str(result))
        else:
            logger.error("All engines failed for %s - %s", item.artist_name, item.track_title)
            self._set_status(item.track_id, "failed", item=item, error="All engines failed")

    def pending_count(self) -> int:
        return self._queue.qsize()

    def get_status_list(self) -> list[dict]:
        results = []
        for tid, info in self._status.items():
            results.append({
                "track_id": tid,
                "status": info.get("status", "unknown"),
                "track_title": info.get("track_title", ""),
                "artist_name": info.get("artist_name", ""),
                "album_title": info.get("album_title", ""),
                "file_path": info.get("file_path"),
                "error": info.get("error"),
                "updated_at": info.get("updated_at", 0),
            })
        results.sort(key=lambda x: x["updated_at"], reverse=True)
        return results

    def clear_completed(self, max_age: float = 60):
        now = time.time()
        to_del = [tid for tid, info in self._status.items()
                  if info.get("status") in ("completed", "failed")
                  and now - info.get("updated_at", 0) > max_age]
        for tid in to_del:
            del self._status[tid]


queue = DownloadQueue()
