from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class DownloadTask:
    video_id: str
    title: str
    artist: str | None
    album: str | None
    duration_seconds: int | None
    thumbnail_url: str | None
    playlist_title: str


@dataclass
class DownloadResult:
    video_id: str
    success: bool
    file_path: Path | None = None
    error_message: str | None = None


@dataclass
class SyncResult:
    total: int
    succeeded: int
    failed: int
    skipped_unavailable: int
