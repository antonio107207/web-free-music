from __future__ import annotations

from pathlib import Path

from ytmusic_sync.remote.client import YTMusicClient
from ytmusic_sync.remote.models import RemotePlaylist
from ytmusic_sync.storage.repository import LibraryRepository, TrackRow
from ytmusic_sync.sync.downloader import compute_track_path, link_into_playlist
from ytmusic_sync.sync.tasks import DownloadTask

_UNKNOWN_PLAYLIST = "Unknown Playlist"


def primary_playlist_title(titles: list[str]) -> str:
    """Deterministically picks one playlist title out of several a track
    belongs to (alphabetically first), used only to decide where a brand-new
    download's canonical file initially lands. Which one gets picked doesn't
    matter for correctness afterward: refresh_playlist_folder_links() detects
    the real file by comparing paths, not by recomputing this choice."""
    return min(titles) if titles else _UNKNOWN_PLAYLIST


def _to_download_task(row: TrackRow, playlist_title: str) -> DownloadTask:
    return DownloadTask(
        video_id=row.video_id,
        title=row.title,
        artist=row.artist,
        album=row.album,
        duration_seconds=row.duration_seconds,
        thumbnail_url=row.thumbnail_url,
        playlist_title=playlist_title,
    )


def build_sync_plan(
    repo: LibraryRepository,
    client: YTMusicClient,
    selected_playlist_ids: list[str],
    remote_playlists: list[RemotePlaylist] | None = None,
) -> list[DownloadTask]:
    repo.reconcile_missing_files()

    if remote_playlists is None:
        remote_playlists = client.list_playlists()
    playlists_by_id = {p.playlist_id: p for p in remote_playlists}

    for playlist_id in selected_playlist_ids:
        playlist = playlists_by_id.get(playlist_id)
        if playlist is None:
            continue
        tracks = client.list_playlist_tracks(playlist_id)
        repo.upsert_remote_snapshot(playlist, tracks)

    pending_rows = repo.get_pending_tracks(selected_playlist_ids)
    titles_by_video_id = repo.get_playlist_titles_for_tracks(
        [row.video_id for row in pending_rows], selected_playlist_ids
    )
    return [
        _to_download_task(row, primary_playlist_title(titles_by_video_id.get(row.video_id, [])))
        for row in pending_rows
    ]


def refresh_playlist_folder_links(repo: LibraryRepository, library_root: Path) -> None:
    downloaded = repo.get_downloaded_tracks_with_playlists()
    for track_row, playlist_titles in downloaded.values():
        if not track_row.file_path:
            continue
        final_path = Path(track_row.file_path)
        if not final_path.exists():
            continue
        for playlist_title in playlist_titles:
            link_path = compute_track_path(library_root, playlist_title, track_row.artist, track_row.title)
            if link_path == final_path:
                continue  # this playlist's folder already holds the real file
            link_into_playlist(final_path, link_path)
