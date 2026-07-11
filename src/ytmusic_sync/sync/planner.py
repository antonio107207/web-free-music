from __future__ import annotations

from pathlib import Path

from ytmusic_sync.remote.client import YTMusicClient
from ytmusic_sync.remote.models import RemotePlaylist
from ytmusic_sync.storage.repository import LibraryRepository, TrackRow
from ytmusic_sync.sync.downloader import compute_playlist_link_path, link_into_playlist
from ytmusic_sync.sync.tasks import DownloadTask


def _to_download_task(row: TrackRow) -> DownloadTask:
    return DownloadTask(
        video_id=row.video_id,
        title=row.title,
        artist=row.artist,
        album=row.album,
        duration_seconds=row.duration_seconds,
        thumbnail_url=row.thumbnail_url,
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
    return [_to_download_task(row) for row in pending_rows]


def refresh_playlist_folder_links(repo: LibraryRepository, library_root: Path) -> None:
    downloaded = repo.get_downloaded_tracks_with_playlists()
    for track_row, playlist_titles in downloaded.values():
        final_path = Path(track_row.file_path)
        if not final_path.exists():
            continue
        task = _to_download_task(track_row)
        for playlist_title in playlist_titles:
            link_path = compute_playlist_link_path(library_root, playlist_title, task)
            link_into_playlist(final_path, link_path)
