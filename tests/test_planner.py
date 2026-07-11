from pathlib import Path

import pytest

from ytmusic_sync.remote.models import RemotePlaylist, RemoteTrack
from ytmusic_sync.storage.repository import LibraryRepository
from ytmusic_sync.sync.planner import build_sync_plan, refresh_playlist_folder_links


class FakeYTMusicClient:
    def __init__(self, playlists, tracks_by_playlist):
        self._playlists = playlists
        self._tracks_by_playlist = tracks_by_playlist
        self.list_playlist_tracks_calls = []

    def list_playlists(self):
        return self._playlists

    def list_playlist_tracks(self, playlist_id):
        self.list_playlist_tracks_calls.append(playlist_id)
        return self._tracks_by_playlist[playlist_id]


@pytest.fixture
def repo(tmp_path: Path) -> LibraryRepository:
    r = LibraryRepository(tmp_path / "test.sqlite3")
    yield r
    r.close()


def test_build_sync_plan_returns_pending_tasks_and_persists_snapshot(repo: LibraryRepository) -> None:
    playlists = [RemotePlaylist("PL1", "My Mix", 2)]
    tracks = {
        "PL1": [
            RemoteTrack("v1", "Song One", "Artist A", "Album A", 200, None, True),
            RemoteTrack("v2", "Unavailable", "Artist B", None, 100, None, False),
        ]
    }
    client = FakeYTMusicClient(playlists, tracks)

    tasks = build_sync_plan(repo, client, ["PL1"])

    assert [t.video_id for t in tasks] == ["v1"]
    assert client.list_playlist_tracks_calls == ["PL1"]
    # snapshot persisted: playlist row exists
    assert repo.get_pending_tracks(["PL1"])[0].video_id == "v1"


def test_build_sync_plan_skips_unknown_playlist_id(repo: LibraryRepository) -> None:
    client = FakeYTMusicClient([], {})
    tasks = build_sync_plan(repo, client, ["does-not-exist"])
    assert tasks == []
    assert client.list_playlist_tracks_calls == []


def test_build_sync_plan_reuses_passed_in_remote_playlists(repo: LibraryRepository) -> None:
    playlists = [RemotePlaylist("PL1", "My Mix", 1)]
    tracks = {"PL1": [RemoteTrack("v1", "Song", "Artist", None, 100, None, True)]}
    client = FakeYTMusicClient(playlists, tracks)

    calls = {"list_playlists": 0}
    original = client.list_playlists

    def counting_list_playlists():
        calls["list_playlists"] += 1
        return original()

    client.list_playlists = counting_list_playlists

    build_sync_plan(repo, client, ["PL1"], remote_playlists=playlists)
    assert calls["list_playlists"] == 0


def test_refresh_playlist_folder_links_creates_hardlinks(repo: LibraryRepository, tmp_path: Path) -> None:
    playlist = RemotePlaylist("PL1", "My Mix", 1)
    track = RemoteTrack("v1", "Song One", "Artist A", "Album A", 200, None, True)
    repo.upsert_remote_snapshot(playlist, [track])

    canonical = tmp_path / "Tracks" / "Artist A" / "Album A" / "Song One.mp3"
    canonical.parent.mkdir(parents=True)
    canonical.write_bytes(b"data")
    repo.mark_downloaded("v1", canonical)

    library_root = tmp_path
    refresh_playlist_folder_links(repo, library_root)

    expected_link = library_root / "Playlists" / "My Mix" / "Artist A - Song One.mp3"
    assert expected_link.exists()
    assert expected_link.samefile(canonical)
