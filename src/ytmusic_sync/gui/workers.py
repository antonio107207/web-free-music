from __future__ import annotations

import logging
import threading
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Signal
from yt_dlp.utils import DownloadCancelled

from ytmusic_sync.remote.client import YTMusicClient
from ytmusic_sync.sync.downloader import download_track
from ytmusic_sync.sync.tasks import DownloadTask

logger = logging.getLogger(__name__)

_CANCELLED_MESSAGE = "Cancelled by user"


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
        cancel_event: threading.Event,
    ) -> None:
        super().__init__()
        self._task = task
        self._signals = signals
        self._library_root = library_root
        self._mp3_quality_kbps = mp3_quality_kbps
        self._cancel_event = cancel_event

    def run(self) -> None:
        # Checked here (not just inside the progress hook) so a task that was
        # still queued when Stop was clicked never starts a real download at
        # all -- every submitted worker still gets a run() call and emits
        # track_finished either way, which is what keeps the GUI's pending-count
        # bookkeeping correct without needing to touch the thread pool's queue.
        if self._cancel_event.is_set():
            self._signals.track_finished.emit(self._task.video_id, False, _CANCELLED_MESSAGE)
            return

        self._signals.track_started.emit(self._task.video_id)

        def hook(d: dict) -> None:
            if self._cancel_event.is_set():
                raise DownloadCancelled(_CANCELLED_MESSAGE)
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
        except DownloadCancelled:
            self._signals.track_finished.emit(self._task.video_id, False, _CANCELLED_MESSAGE)
        except Exception as e:  # noqa: BLE001 - report any failure back to the GUI, don't crash the worker pool
            logger.exception("Download failed for %s (%s)", self._task.video_id, self._task.title)
            self._signals.track_finished.emit(self._task.video_id, False, str(e))


class TracksFetchSignals(QObject):
    tracks_ready = Signal(str, list)  # playlist_id, list[RemoteTrack]
    tracks_failed = Signal(str, str)  # playlist_id, error message


class TracksFetchWorker(QRunnable):
    def __init__(self, client: YTMusicClient, playlist_id: str, signals: TracksFetchSignals) -> None:
        super().__init__()
        self._client = client
        self._playlist_id = playlist_id
        self._signals = signals

    def run(self) -> None:
        try:
            tracks = self._client.list_playlist_tracks(self._playlist_id)
            self._signals.tracks_ready.emit(self._playlist_id, tracks)
        except Exception as e:  # noqa: BLE001 - report any failure back to the GUI
            logger.exception("Failed to fetch tracks for playlist %s", self._playlist_id)
            self._signals.tracks_failed.emit(self._playlist_id, str(e))
