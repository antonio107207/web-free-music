from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Signal

from ytmusic_sync.remote.client import YTMusicClient
from ytmusic_sync.remote.models import RemotePlaylist
from ytmusic_sync.storage.repository import LibraryRepository
from ytmusic_sync.sync.downloader import download_track
from ytmusic_sync.sync.planner import build_sync_plan
from ytmusic_sync.sync.tasks import DownloadTask

logger = logging.getLogger(__name__)


class DownloadSignals(QObject):
    track_started = Signal(str)
    track_progress = Signal(str, float)
    track_finished = Signal(str, bool, str)  # video_id, success, file_path_or_error


class DownloadWorker(QRunnable):
    def __init__(
        self,
        task: DownloadTask,
        signals: DownloadSignals,
        library_root: Path,
        mp3_quality_kbps: str,
    ) -> None:
        super().__init__()
        self._task = task
        self._signals = signals
        self._library_root = library_root
        self._mp3_quality_kbps = mp3_quality_kbps

    def run(self) -> None:
        self._signals.track_started.emit(self._task.video_id)

        def hook(d: dict) -> None:
            if d.get("status") != "downloading":
                return
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            downloaded = d.get("downloaded_bytes", 0)
            if total:
                pct = max(0.0, min(downloaded / total, 1.0))
                self._signals.track_progress.emit(self._task.video_id, pct)

        try:
            final_path = download_track(
                self._task, self._library_root, self._mp3_quality_kbps, hook
            )
            self._signals.track_finished.emit(self._task.video_id, True, str(final_path))
        except Exception as e:  # noqa: BLE001 - report any failure back to the GUI, don't crash the worker pool
            logger.exception("Download failed for %s (%s)", self._task.video_id, self._task.title)
            self._signals.track_finished.emit(self._task.video_id, False, str(e))


class PlanSignals(QObject):
    plan_ready = Signal(list)
    plan_failed = Signal(str)


class PlanWorker(QRunnable):
    """Runs on a background thread, so it opens its own short-lived LibraryRepository
    connection to the db file rather than sharing the main thread's connection object
    (sqlite3.Connection objects aren't safe to use across threads)."""

    def __init__(
        self,
        db_path: Path,
        client: YTMusicClient,
        selected_playlist_ids: list[str],
        remote_playlists: list[RemotePlaylist],
        signals: PlanSignals,
    ) -> None:
        super().__init__()
        self._db_path = db_path
        self._client = client
        self._selected_playlist_ids = selected_playlist_ids
        self._remote_playlists = remote_playlists
        self._signals = signals

    def run(self) -> None:
        repo = LibraryRepository(self._db_path)
        try:
            tasks = build_sync_plan(
                repo, self._client, self._selected_playlist_ids, self._remote_playlists
            )
            self._signals.plan_ready.emit(tasks)
        except Exception as e:  # noqa: BLE001
            logger.exception("Sync planning failed for playlists %s", self._selected_playlist_ids)
            self._signals.plan_failed.emit(str(e))
        finally:
            repo.close()
