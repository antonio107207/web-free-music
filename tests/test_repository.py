from pathlib import Path

import pytest

from ytmusic_sync.remote.models import RemotePlaylist, RemoteTrack
from ytmusic_sync.storage.repository import LibraryRepository, STATUS_DOWNLOADED, STATUS_UNAVAILABLE


@pytest.fixture
def repo(tmp_path: Path) -> LibraryRepository:
    r = LibraryRepository(tmp_path / "test.sqlite3")
    yield r
    r.close()


def _playlist_and_tracks():
    playlist = RemotePlaylist(playlist_id="PL1", title="My Mix", track_count=2)
    tracks = [
        RemoteTrack("v1", "Song One", "Artist A", "Album A", 200, None, True),
        RemoteTrack("v2", "Song Two", "Artist B", None, 180, None, True),
        RemoteTrack("v3", "Unavailable Song", "Artist C", None, 100, None, False),
    ]
    return playlist, tracks


def test_unavailable_tracks_excluded_from_pending(repo: LibraryRepository) -> None:
    playlist, tracks = _playlist_and_tracks()
    repo.upsert_remote_snapshot(playlist, tracks)

    pending = repo.get_pending_tracks(["PL1"])
    assert {t.video_id for t in pending} == {"v1", "v2"}


def test_downloaded_track_not_resurfaced_on_resync(repo: LibraryRepository) -> None:
    playlist, tracks = _playlist_and_tracks()
    repo.upsert_remote_snapshot(playlist, tracks)
    repo.mark_downloaded("v1", Path("/tmp/does-not-exist/v1.mp3"))

    repo.upsert_remote_snapshot(playlist, tracks)
    pending = repo.get_pending_tracks(["PL1"])
    assert "v1" not in {t.video_id for t in pending}


def test_failed_track_remains_pending_eligible(repo: LibraryRepository) -> None:
    playlist, tracks = _playlist_and_tracks()
    repo.upsert_remote_snapshot(playlist, tracks)
    repo.mark_failed("v1", "boom")

    pending = repo.get_pending_tracks(["PL1"])
    assert "v1" in {t.video_id for t in pending}


def test_reconcile_missing_files_resets_status(repo: LibraryRepository, tmp_path: Path) -> None:
    playlist, tracks = _playlist_and_tracks()
    repo.upsert_remote_snapshot(playlist, tracks)

    real_file = tmp_path / "v1.mp3"
    real_file.write_bytes(b"data")
    repo.mark_downloaded("v1", real_file)

    reset_count = repo.reconcile_missing_files()
    assert reset_count == 0  # file exists, nothing to reset
    assert "v1" not in {t.video_id for t in repo.get_pending_tracks(["PL1"])}

    real_file.unlink()
    reset_count = repo.reconcile_missing_files()
    assert reset_count == 1
    assert "v1" in {t.video_id for t in repo.get_pending_tracks(["PL1"])}


def test_track_shared_across_playlists_downloads_once(repo: LibraryRepository) -> None:
    shared_track = RemoteTrack("shared", "Shared Song", "Artist", None, 100, None, True)
    repo.upsert_remote_snapshot(RemotePlaylist("PL1", "Playlist One", 1), [shared_track])
    repo.upsert_remote_snapshot(RemotePlaylist("PL2", "Playlist Two", 1), [shared_track])

    assert len(repo.get_pending_tracks(["PL1"])) == 1
    assert len(repo.get_pending_tracks(["PL2"])) == 1

    repo.mark_downloaded("shared", Path("/tmp/shared.mp3"))
    assert repo.get_pending_tracks(["PL1", "PL2"]) == []


def test_duplicate_track_within_same_playlist_does_not_crash(repo: LibraryRepository) -> None:
    # Real playlists can contain the same track more than once (added twice by
    # the user). This used to raise "UNIQUE constraint failed: playlist_tracks
    # .playlist_id, playlist_tracks.video_id".
    playlist = RemotePlaylist("PL1", "My Mix", 3)
    tracks = [
        RemoteTrack("v1", "Song One", "Artist A", "Album A", 200, None, True),
        RemoteTrack("v1", "Song One", "Artist A", "Album A", 200, None, True),
        RemoteTrack("v2", "Song Two", "Artist B", None, 180, None, True),
    ]
    repo.upsert_remote_snapshot(playlist, tracks)

    pending = repo.get_pending_tracks(["PL1"])
    assert sorted(t.video_id for t in pending) == ["v1", "v2"]


def test_unavailable_track_becomes_pending_if_it_reappears_available(
    repo: LibraryRepository,
) -> None:
    playlist = RemotePlaylist("PL1", "My Mix", 1)
    unavailable = RemoteTrack("v1", "Song", "Artist", None, 100, None, False)
    repo.upsert_remote_snapshot(playlist, [unavailable])
    assert repo.get_pending_tracks(["PL1"]) == []

    available = RemoteTrack("v1", "Song", "Artist", None, 100, None, True)
    repo.upsert_remote_snapshot(playlist, [available])
    assert {t.video_id for t in repo.get_pending_tracks(["PL1"])} == {"v1"}
