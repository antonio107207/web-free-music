from __future__ import annotations

from typing import Any

from ytmusicapi import YTMusic

from ytmusic_sync.remote.models import LIKED_SONGS_PLAYLIST_ID, RemotePlaylist, RemoteTrack

_LIKED_SONGS_TITLE = "Liked Songs"
_PAGE_STEP = 500
_MAX_PAGES = 40  # safety cap: 40 * 500 = 20000 tracks


def _track_from_dict(t: dict[str, Any]) -> RemoteTrack | None:
    video_id = t.get("videoId")
    if not video_id:
        return None
    artists = t.get("artists") or []
    artist = ", ".join(a["name"] for a in artists if a.get("name")) or "Unknown Artist"
    album = t.get("album")
    album_name = album.get("name") if isinstance(album, dict) else None
    thumbnails = t.get("thumbnails") or []
    thumbnail_url = thumbnails[-1]["url"] if thumbnails else None
    return RemoteTrack(
        video_id=video_id,
        title=t.get("title") or "Unknown Title",
        artist=artist,
        album=album_name,
        duration_seconds=t.get("duration_seconds"),
        thumbnail_url=thumbnail_url,
        is_available=t.get("isAvailable", True),
    )


class YTMusicClient:
    def __init__(self, yt: YTMusic) -> None:
        self._yt = yt

    def list_playlists(self) -> list[RemotePlaylist]:
        raw = self._yt.get_library_playlists(limit=None)
        playlists = [RemotePlaylist(playlist_id=LIKED_SONGS_PLAYLIST_ID, title=_LIKED_SONGS_TITLE, track_count=None)]
        for p in raw:
            playlist_id = p.get("playlistId")
            if not playlist_id:
                continue
            playlists.append(
                RemotePlaylist(
                    playlist_id=playlist_id,
                    title=p.get("title") or "Untitled Playlist",
                    track_count=p.get("count"),
                )
            )
        return playlists

    def list_playlist_tracks(self, playlist_id: str) -> list[RemoteTrack]:
        if playlist_id == LIKED_SONGS_PLAYLIST_ID:
            raw_tracks = self._fetch_liked_songs_paginated()
        else:
            data = self._yt.get_playlist(playlist_id, limit=None)
            raw_tracks = data.get("tracks", [])
        tracks = []
        for t in raw_tracks:
            track = _track_from_dict(t)
            if track is not None:
                tracks.append(track)
        return tracks

    def _fetch_liked_songs_paginated(self) -> list[dict[str, Any]]:
        seen_ids: set[str] = set()
        collected: list[dict[str, Any]] = []
        limit = _PAGE_STEP
        for _ in range(_MAX_PAGES):
            data = self._yt.get_liked_songs(limit=limit)
            batch = data.get("tracks", [])
            new_count = 0
            collected = []
            seen_ids.clear()
            for t in batch:
                vid = t.get("videoId")
                if vid and vid not in seen_ids:
                    seen_ids.add(vid)
                    collected.append(t)
                    new_count += 1
            if new_count < limit:
                break
            limit += _PAGE_STEP
        return collected
