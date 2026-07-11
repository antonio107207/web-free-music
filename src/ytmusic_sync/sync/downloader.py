from __future__ import annotations

import re
import shutil
import tempfile
from pathlib import Path
from typing import Callable

import yt_dlp
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3NoHeaderError
from mutagen.mp3 import MP3

from ytmusic_sync.sync.tasks import DownloadTask

_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
ProgressHook = Callable[[dict], None]


def sanitize_filename(name: str) -> str:
    cleaned = _INVALID_CHARS.sub("_", name).strip().strip(".")
    return cleaned or "Untitled"


def compute_track_path(library_root: Path, playlist_title: str, artist: str | None, title: str) -> Path:
    playlist_dir = sanitize_filename(playlist_title)
    filename = sanitize_filename(f"{artist or 'Unknown Artist'} - {title}") + ".mp3"
    return library_root / playlist_dir / filename


def build_ydl_opts(out_template: str, quality_kbps: str, progress_hook: ProgressHook) -> dict:
    return {
        "format": "bestaudio/best",
        "outtmpl": out_template,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "progress_hooks": [progress_hook],
        "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": quality_kbps},
            {"key": "FFmpegMetadata", "add_metadata": True},
            {"key": "EmbedThumbnail"},
        ],
        "writethumbnail": True,
    }


def tag_mp3(path: Path, task: DownloadTask) -> None:
    audio = MP3(str(path))
    try:
        tags = EasyID3(str(path))
    except ID3NoHeaderError:
        audio.add_tags()
        audio.save()
        tags = EasyID3(str(path))
    tags["title"] = task.title
    if task.artist:
        tags["artist"] = task.artist
    if task.album:
        tags["album"] = task.album
    tags.save()


def download_track(
    task: DownloadTask,
    library_root: Path,
    quality_kbps: str,
    progress_hook: ProgressHook,
) -> Path:
    with tempfile.TemporaryDirectory(prefix="ytmusic_sync_") as tmp_dir_str:
        tmp_dir = Path(tmp_dir_str)
        opts = build_ydl_opts(str(tmp_dir / "%(id)s.%(ext)s"), quality_kbps, progress_hook)
        url = f"https://music.youtube.com/watch?v={task.video_id}"
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])

        mp3_candidates = list(tmp_dir.glob(f"{task.video_id}*.mp3"))
        if not mp3_candidates:
            raise FileNotFoundError(
                f"yt-dlp did not produce an mp3 file for video {task.video_id}"
            )
        mp3_path = mp3_candidates[0]
        tag_mp3(mp3_path, task)

        final_path = compute_track_path(library_root, task.playlist_title, task.artist, task.title)
        final_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(mp3_path), str(final_path))

    return final_path


def link_into_playlist(final_path: Path, link_path: Path) -> None:
    link_path.parent.mkdir(parents=True, exist_ok=True)
    if link_path.exists():
        if link_path.samefile(final_path):
            return
        link_path.unlink()
    try:
        link_path.hardlink_to(final_path)
    except OSError:
        shutil.copy2(final_path, link_path)
