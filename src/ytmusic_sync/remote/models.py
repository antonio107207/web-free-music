from __future__ import annotations

from dataclasses import dataclass

LIKED_SONGS_PLAYLIST_ID = "LM"


@dataclass
class RemoteTrack:
    video_id: str
    title: str
    artist: str
    album: str | None
    duration_seconds: int | None
    thumbnail_url: str | None
    is_available: bool


@dataclass
class RemotePlaylist:
    playlist_id: str
    title: str
    track_count: int | None
