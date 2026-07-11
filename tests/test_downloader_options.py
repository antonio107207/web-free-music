import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3

from ytmusic_sync.sync.downloader import build_ydl_opts, download_track, tag_mp3
from ytmusic_sync.sync.tasks import DownloadTask


def test_build_ydl_opts_uses_bestaudio_and_mp3_postprocessor() -> None:
    opts = build_ydl_opts("out/%(id)s.%(ext)s", "192", progress_hook=lambda d: None)

    assert opts["format"] == "bestaudio/best"
    assert opts["noplaylist"] is True
    pp_keys = [pp["key"] for pp in opts["postprocessors"]]
    assert "FFmpegExtractAudio" in pp_keys
    extract = next(pp for pp in opts["postprocessors"] if pp["key"] == "FFmpegExtractAudio")
    assert extract["preferredcodec"] == "mp3"
    assert extract["preferredquality"] == "192"


class FakeYoutubeDL:
    """Stands in for yt_dlp.YoutubeDL: writes a fake mp3 into the outtmpl's directory
    instead of hitting the network, so download_track's file-moving/tagging logic
    can be tested without a real download."""

    def __init__(self, opts: dict) -> None:
        self._opts = opts

    def __enter__(self) -> "FakeYoutubeDL":
        return self

    def __exit__(self, *exc) -> None:
        return None

    def download(self, urls: list[str]) -> None:
        out_template = self._opts["outtmpl"]
        out_dir = Path(out_template).parent
        video_id = urls[0].rsplit("=", 1)[-1]
        fake_mp3 = out_dir / f"{video_id}.mp3"
        fake_mp3.write_bytes(b"fake mp3 bytes")  # tag_mp3 is mocked out below, no real parsing needed


def test_download_track_moves_file_to_canonical_path_and_tags(tmp_path: Path) -> None:
    task = DownloadTask(
        video_id="abc123",
        title="My Song",
        artist="My Artist",
        album="My Album",
        duration_seconds=120,
        thumbnail_url=None,
        playlist_title="My Mix",
    )
    library_root = tmp_path / "library"

    with patch("ytmusic_sync.sync.downloader.yt_dlp.YoutubeDL", FakeYoutubeDL), patch(
        "ytmusic_sync.sync.downloader.tag_mp3"
    ) as mock_tag:
        final_path = download_track(task, library_root, "192", progress_hook=lambda d: None)

    assert final_path == library_root / "My Mix" / "My Artist - My Song.mp3"
    assert final_path.exists()
    mock_tag.assert_called_once()
    called_path, called_task = mock_tag.call_args[0]
    assert called_task is task


@pytest.fixture
def real_mp3(tmp_path: Path) -> Path:
    """A tiny but real mp3 file, since tag_mp3 needs actual ID3-writable audio
    (ffmpeg is already a hard runtime dependency of this app, checked on
    startup, so relying on it in tests is consistent with that)."""
    path = tmp_path / "sample.mp3"
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
            "-codec:a", "libmp3lame", "-qscale:a", "9", str(path), "-loglevel", "error",
        ],
        check=True,
    )
    return path


def _tag_task(thumbnail_url: str | None = None) -> DownloadTask:
    return DownloadTask(
        video_id="abc123",
        title="My Song",
        artist="My Artist",
        album="My Album",
        duration_seconds=120,
        thumbnail_url=thumbnail_url,
        playlist_title="My Mix",
    )


def test_tag_mp3_sets_text_tags(real_mp3: Path) -> None:
    tag_mp3(real_mp3, _tag_task())
    tags = EasyID3(str(real_mp3))
    assert tags["title"] == ["My Song"]
    assert tags["artist"] == ["My Artist"]
    assert tags["album"] == ["My Album"]


def test_tag_mp3_embeds_cover_art_from_thumbnail_url(real_mp3: Path) -> None:
    fake_response = MagicMock()
    fake_response.content = b"FAKE_JPEG_BYTES"
    fake_response.raise_for_status = lambda: None

    with patch("ytmusic_sync.sync.downloader.requests.get", return_value=fake_response) as mock_get:
        tag_mp3(real_mp3, _tag_task(thumbnail_url="https://example.com/cover.jpg"))

    mock_get.assert_called_once_with("https://example.com/cover.jpg", timeout=10)
    apics = ID3(str(real_mp3)).getall("APIC")
    assert len(apics) == 1
    assert apics[0].data == b"FAKE_JPEG_BYTES"
    assert apics[0].mime == "image/jpeg"


def test_tag_mp3_detects_png_cover_art_mime_type(real_mp3: Path) -> None:
    fake_response = MagicMock()
    fake_response.content = b"FAKE_PNG_BYTES"
    fake_response.raise_for_status = lambda: None

    with patch("ytmusic_sync.sync.downloader.requests.get", return_value=fake_response):
        tag_mp3(real_mp3, _tag_task(thumbnail_url="https://example.com/cover.png?rs=1"))

    apics = ID3(str(real_mp3)).getall("APIC")
    assert apics[0].mime == "image/png"


def test_tag_mp3_skips_cover_art_when_no_thumbnail_url(real_mp3: Path) -> None:
    with patch("ytmusic_sync.sync.downloader.requests.get") as mock_get:
        tag_mp3(real_mp3, _tag_task(thumbnail_url=None))

    mock_get.assert_not_called()
    assert ID3(str(real_mp3)).getall("APIC") == []


def test_tag_mp3_does_not_fail_when_cover_art_download_fails(real_mp3: Path) -> None:
    with patch(
        "ytmusic_sync.sync.downloader.requests.get", side_effect=requests.RequestException("boom")
    ):
        tag_mp3(real_mp3, _tag_task(thumbnail_url="https://example.com/broken.jpg"))  # must not raise

    assert ID3(str(real_mp3)).getall("APIC") == []
    # text tags still got set despite the cover art failure
    assert EasyID3(str(real_mp3))["title"] == ["My Song"]
