import threading
from unittest.mock import patch

from ytmusic_sync.gui.workers import DownloadSignals, DownloadWorker
from ytmusic_sync.sync.tasks import DownloadTask


def _task() -> DownloadTask:
    return DownloadTask(
        video_id="v1",
        title="Song",
        artist="Artist",
        album=None,
        duration_seconds=100,
        thumbnail_url=None,
        playlist_title="My Mix",
    )


def test_worker_skips_download_entirely_if_already_cancelled(tmp_path) -> None:
    signals = DownloadSignals()
    received = []
    signals.track_finished.connect(lambda *args: received.append(args))
    signals.track_started.connect(lambda video_id: received.append(("started", video_id)))

    cancel_event = threading.Event()
    cancel_event.set()  # already cancelled before the worker ever runs
    worker = DownloadWorker(_task(), signals, tmp_path, "192", cancel_event)

    with patch("ytmusic_sync.gui.workers.download_track") as mock_download:
        worker.run()

    mock_download.assert_not_called()
    assert received == [("v1", False, "Cancelled by user")]


def test_worker_raises_download_cancelled_from_hook_once_event_is_set(tmp_path) -> None:
    signals = DownloadSignals()
    finished = []
    signals.track_finished.connect(lambda video_id, success, message: finished.append((video_id, success, message)))

    cancel_event = threading.Event()
    worker = DownloadWorker(_task(), signals, tmp_path, "192", cancel_event)

    def fake_download_track(task, library_root, quality_kbps, progress_hook):
        # first call: not cancelled yet, proceeds
        progress_hook({"status": "downloading", "downloaded_bytes": 1, "total_bytes": 100})
        # simulate Stop being clicked mid-download
        cancel_event.set()
        # next hook call must now raise DownloadCancelled, exactly like the real one
        progress_hook({"status": "downloading", "downloaded_bytes": 2, "total_bytes": 100})
        raise AssertionError("should not reach here -- progress_hook should have raised")

    with patch("ytmusic_sync.gui.workers.download_track", side_effect=fake_download_track):
        worker.run()

    assert finished == [("v1", False, "Cancelled by user")]
