from pathlib import Path
from unittest.mock import patch

from ytmusic_sync.sync.downloader import build_ydl_opts, download_track
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
