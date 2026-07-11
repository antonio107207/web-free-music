from pathlib import Path

import pytest

from ytmusic_sync.remote.models import RemotePlaylist, RemoteTrack
from ytmusic_sync.storage.repository import LibraryRepository
from ytmusic_sync.sync.planner import build_sync_plan, primary_playlist_title, refresh_playlist_folder_links


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
    assert tasks[0].playlist_title == "My Mix"
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


def test_primary_playlist_title_picks_alphabetically_first() -> None:
    assert primary_playlist_title(["Zeta Mix", "Alpha Mix", "Mid Mix"]) == "Alpha Mix"


def test_primary_playlist_title_empty_list_returns_fallback() -> None:
    assert primary_playlist_title([]) == "Unknown Playlist"


def test_refresh_playlist_folder_links_is_noop_for_single_playlist_track(
    repo: LibraryRepository, tmp_path: Path
) -> None:
    track = RemoteTrack("v1", "Song One", "Artist A", None, 200, None, True)
    repo.upsert_remote_snapshot(RemotePlaylist("PL1", "My Mix", 1), [track])

    real_file = tmp_path / "My Mix" / "Artist A - Song One.mp3"
    real_file.parent.mkdir(parents=True)
    real_file.write_bytes(b"data")
    repo.mark_downloaded("v1", real_file)

    refresh_playlist_folder_links(repo, tmp_path)

    # the track's only playlist already holds the real file -- nothing to link
    assert list(tmp_path.rglob("*.mp3")) == [real_file]


def test_refresh_playlist_folder_links_creates_hardlinks_for_non_primary_playlists(
    repo: LibraryRepository, tmp_path: Path
) -> None:
    track = RemoteTrack("v1", "Song One", "Artist A", "Album A", 200, None, True)
    repo.upsert_remote_snapshot(RemotePlaylist("PL1", "My Mix", 1), [track])
    repo.upsert_remote_snapshot(RemotePlaylist("PL2", "Chill", 1), [track])

    # Simulate the track already having been downloaded directly into "My Mix"
    # (as if that had been the playlist picked at download time).
    real_file = tmp_path / "My Mix" / "Artist A - Song One.mp3"
    real_file.parent.mkdir(parents=True)
    real_file.write_bytes(b"data")
    repo.mark_downloaded("v1", real_file)

    refresh_playlist_folder_links(repo, tmp_path)

    other_link = tmp_path / "Chill" / "Artist A - Song One.mp3"
    assert other_link.exists()
    assert other_link.samefile(real_file)
    # "My Mix" already holds the real file -- must not get a second copy/link
    assert list((tmp_path / "My Mix").iterdir()) == [real_file]
