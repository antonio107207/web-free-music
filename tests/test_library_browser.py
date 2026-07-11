from pathlib import Path

import pytest
from PySide6.QtCore import Qt

from ytmusic_sync.gui.library_browser import LibraryBrowser
from ytmusic_sync.remote.models import RemotePlaylist, RemoteTrack
from ytmusic_sync.storage.repository import LibraryRepository


@pytest.fixture
def repo_with_tracks(tmp_path: Path):
    repo = LibraryRepository(tmp_path / "test.sqlite3")
    playlist = RemotePlaylist("PL1", "My Mix", 2)
    tracks = [
        RemoteTrack("v1", "Alpha Song", "Artist A", "Album A", 100, None, True),
        RemoteTrack("v2", "Beta Song", "Artist B", "Album B", 120, None, True),
    ]
    repo.upsert_remote_snapshot(playlist, tracks)
    downloaded_file = tmp_path / "v1.mp3"
    downloaded_file.write_bytes(b"data")
    repo.mark_downloaded("v1", downloaded_file)
    yield repo
    repo.close()


def test_refresh_populates_table(qtbot, repo_with_tracks: LibraryRepository) -> None:
    browser = LibraryBrowser(repo_with_tracks)
    qtbot.addWidget(browser)
    browser.refresh()
    assert browser._table.rowCount() == 2


def test_search_filters_rows_by_title_and_artist(qtbot, repo_with_tracks: LibraryRepository) -> None:
    browser = LibraryBrowser(repo_with_tracks)
    qtbot.addWidget(browser)
    browser.refresh()

    browser._search_box.setText("alpha")
    assert browser._table.rowCount() == 1
    assert browser._table.item(0, 0).text() == "Alpha Song"

    browser._search_box.setText("Artist B")
    assert browser._table.rowCount() == 1
    assert browser._table.item(0, 0).text() == "Beta Song"

    browser._search_box.setText("")
    assert browser._table.rowCount() == 2


def test_redownload_marks_track_failed_and_pending_eligible(
    qtbot, repo_with_tracks: LibraryRepository
) -> None:
    browser = LibraryBrowser(repo_with_tracks)
    qtbot.addWidget(browser)
    browser.refresh()

    # simulate choosing "Re-download" for v1 without going through the real context menu popup
    row_data = next(r for r in browser._all_rows if r["video_id"] == "v1")
    assert row_data["status"] == "downloaded"

    repo_with_tracks.mark_failed("v1", "Queued for re-download")
    browser.refresh()

    pending = repo_with_tracks.get_pending_tracks(["PL1"])
    assert "v1" in {t.video_id for t in pending}


def test_status_filter_shows_only_matching_status(qtbot, repo_with_tracks: LibraryRepository) -> None:
    browser = LibraryBrowser(repo_with_tracks)
    qtbot.addWidget(browser)
    browser.refresh()

    browser._status_filter.setCurrentIndex(browser._status_filter.findData("downloaded"))
    assert browser._table.rowCount() == 1
    assert browser._table.item(0, 0).text() == "Alpha Song"

    browser._status_filter.setCurrentIndex(browser._status_filter.findData("pending"))
    assert browser._table.rowCount() == 1
    assert browser._table.item(0, 0).text() == "Beta Song"

    browser._status_filter.setCurrentIndex(0)  # "All statuses"
    assert browser._table.rowCount() == 2


def test_status_filter_combines_with_search_text(qtbot, repo_with_tracks: LibraryRepository) -> None:
    browser = LibraryBrowser(repo_with_tracks)
    qtbot.addWidget(browser)
    browser.refresh()

    browser._status_filter.setCurrentIndex(browser._status_filter.findData("downloaded"))
    browser._search_box.setText("Beta")  # Beta Song is pending, not downloaded
    assert browser._table.rowCount() == 0


def test_sorting_is_enabled_and_reorders_rows(qtbot, repo_with_tracks: LibraryRepository) -> None:
    browser = LibraryBrowser(repo_with_tracks)
    qtbot.addWidget(browser)
    browser.refresh()

    assert browser._table.isSortingEnabled() is True

    browser._table.sortItems(0, Qt.SortOrder.DescendingOrder)
    assert browser._table.item(0, 0).text() == "Beta Song"
    assert browser._table.item(1, 0).text() == "Alpha Song"

    browser._table.sortItems(0, Qt.SortOrder.AscendingOrder)
    assert browser._table.item(0, 0).text() == "Alpha Song"
    assert browser._table.item(1, 0).text() == "Beta Song"
