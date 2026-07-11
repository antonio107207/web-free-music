from pathlib import Path

import pytest

from ytmusic_sync.gui.main_window import MainWindow
from ytmusic_sync.remote.models import RemotePlaylist, RemoteTrack


class FakePaths:
    def __init__(self, tmp_path: Path) -> None:
        self.db_file = tmp_path / "library.sqlite3"
        self.settings_file = tmp_path / "settings.json"


class FakeAuthManager:
    """Duck-types YTMAuthManager without touching real ytmusicapi/platformdirs."""

    def has_saved_auth(self) -> bool:
        return True

    def load_client(self):
        return object()  # MainWindow only passes this into YTMusicClient(client)

    def validate_client(self, client) -> None:
        return None


@pytest.fixture
def fake_remote_data():
    playlists = [RemotePlaylist("PL1", "My Mix", 1)]
    tracks = {
        "PL1": [RemoteTrack("v1", "Song One", "Artist A", "Album A", 100, None, True)],
    }
    return playlists, tracks


def test_sync_now_downloads_selected_playlist_and_updates_repo(
    qtbot, tmp_path: Path, monkeypatch, fake_remote_data
) -> None:
    playlists, tracks_by_playlist = fake_remote_data

    monkeypatch.setattr(
        "ytmusic_sync.remote.client.YTMusicClient.list_playlists",
        lambda self: playlists,
    )
    monkeypatch.setattr(
        "ytmusic_sync.remote.client.YTMusicClient.list_playlist_tracks",
        lambda self, playlist_id: tracks_by_playlist[playlist_id],
    )

    downloaded_paths = []

    def fake_download_track(task, library_root, quality_kbps, progress_hook):
        progress_hook({"status": "downloading", "downloaded_bytes": 50, "total_bytes": 100})
        final = library_root / f"{task.video_id}.mp3"
        final.parent.mkdir(parents=True, exist_ok=True)
        final.write_bytes(b"fake")
        downloaded_paths.append(final)
        return final

    monkeypatch.setattr("ytmusic_sync.gui.workers.download_track", fake_download_track)

    paths = FakePaths(tmp_path)
    auth_manager = FakeAuthManager()

    window = MainWindow(auth_manager, paths)
    qtbot.addWidget(window)

    assert window._sidebar.selected_playlist_ids() == []
    # simulate the user checking the playlist checkbox
    window._on_playlist_selection_changed("PL1", True)
    window._sidebar.set_playlists(playlists, {"PL1"})

    window._on_sync_now_clicked()
    assert window._sync_now_button.isEnabled() is False

    qtbot.waitUntil(lambda: len(downloaded_paths) == 1, timeout=5000)
    qtbot.waitUntil(lambda: window._sync_now_button.isEnabled(), timeout=5000)

    assert window.statusBar().currentMessage() == "Sync complete."
    pending = window._repo.get_pending_tracks(["PL1"])
    assert pending == []
    assert downloaded_paths[0].exists()


def test_clicking_playlist_shows_its_track_list(
    qtbot, tmp_path: Path, monkeypatch, fake_remote_data
) -> None:
    playlists, tracks_by_playlist = fake_remote_data

    monkeypatch.setattr(
        "ytmusic_sync.remote.client.YTMusicClient.list_playlists",
        lambda self: playlists,
    )
    monkeypatch.setattr(
        "ytmusic_sync.remote.client.YTMusicClient.list_playlist_tracks",
        lambda self, playlist_id: tracks_by_playlist[playlist_id],
    )

    window = MainWindow(FakeAuthManager(), FakePaths(tmp_path))
    qtbot.addWidget(window)

    window._on_playlist_activated("PL1")

    qtbot.waitUntil(lambda: window._tracks_view._table.rowCount() == 1, timeout=5000)
    assert window._tabs.currentWidget() is window._tracks_view
    assert "My Mix" in window._tracks_view._title_label.text()
    assert window._tracks_view._table.item(0, 0).text() == "Song One"


def test_clicking_different_playlist_before_first_load_finishes_ignores_stale_result(
    qtbot, tmp_path: Path, monkeypatch
) -> None:
    playlists = [RemotePlaylist("PL1", "Slow Playlist", 1), RemotePlaylist("PL2", "Fast Playlist", 1)]
    tracks_by_playlist = {
        "PL1": [RemoteTrack("slow1", "Slow Song", "Artist", None, 100, None, True)],
        "PL2": [RemoteTrack("fast1", "Fast Song", "Artist", None, 100, None, True)],
    }

    monkeypatch.setattr(
        "ytmusic_sync.remote.client.YTMusicClient.list_playlists",
        lambda self: playlists,
    )
    monkeypatch.setattr(
        "ytmusic_sync.remote.client.YTMusicClient.list_playlist_tracks",
        lambda self, playlist_id: tracks_by_playlist[playlist_id],
    )

    window = MainWindow(FakeAuthManager(), FakePaths(tmp_path))
    qtbot.addWidget(window)

    # Simulate a stale result arriving late for a playlist the user already
    # navigated away from -- it must not clobber what's currently displayed.
    window._active_tracks_playlist_id = "PL2"
    window._on_tracks_ready("PL1", tracks_by_playlist["PL1"])
    assert window._tracks_view._table.rowCount() == 0
