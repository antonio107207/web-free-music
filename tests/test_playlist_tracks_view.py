from ytmusic_sync.gui.playlist_tracks_view import PlaylistTracksView
from ytmusic_sync.remote.models import RemoteTrack


def test_show_loading_clears_table_and_sets_label(qtbot) -> None:
    view = PlaylistTracksView()
    qtbot.addWidget(view)

    view.show_loading("My Mix")
    assert "My Mix" in view._title_label.text()
    assert view._table.rowCount() == 0


def test_show_tracks_populates_rows_with_status(qtbot) -> None:
    view = PlaylistTracksView()
    qtbot.addWidget(view)

    tracks = [
        RemoteTrack("v1", "Song One", "Artist A", "Album A", 125, None, True),
        RemoteTrack("v2", "Song Two", "Artist B", None, 60, None, True),
        RemoteTrack("v3", "Unavailable Song", "Artist C", None, 10, None, False),
    ]
    statuses = {"v1": "downloaded"}

    view.show_tracks("My Mix", tracks, statuses)

    assert view._table.rowCount() == 3
    assert view._table.item(0, 0).text() == "Song One"
    assert view._table.item(0, 3).text() == "2:05"
    assert view._table.item(0, 4).text() == "Downloaded"
    # v2 has no stored status yet -> defaults to "pending" -> "Not downloaded"
    assert view._table.item(1, 4).text() == "Not downloaded"
    # v3 is unavailable and has no stored status -> falls back to "unavailable"
    assert view._table.item(2, 4).text() == "Unavailable"


def test_show_error_clears_table_and_shows_message(qtbot) -> None:
    view = PlaylistTracksView()
    qtbot.addWidget(view)

    view.show_tracks("My Mix", [RemoteTrack("v1", "Song", "Artist", None, 100, None, True)], {})
    assert view._table.rowCount() == 1

    view.show_error("My Mix", "network broke")
    assert view._table.rowCount() == 0
    assert "network broke" in view._title_label.text()
