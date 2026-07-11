from PySide6.QtCore import Qt

from ytmusic_sync.gui.playlist_tracks_view import PlaylistTracksView
from ytmusic_sync.remote.models import RemoteTrack


def _tracks():
    return [
        RemoteTrack("v1", "Song One", "Artist A", "Album A", 125, None, True),
        RemoteTrack("v2", "Song Two", "Artist B", None, 60, None, True),
        RemoteTrack("v3", "Unavailable Song", "Artist C", None, 10, None, False),
    ]


def test_show_loading_clears_table_and_sets_label(qtbot) -> None:
    view = PlaylistTracksView()
    qtbot.addWidget(view)

    view.show_loading("My Mix")
    assert "My Mix" in view._title_label.text()
    assert view._table.rowCount() == 0


def test_show_tracks_populates_rows_with_status(qtbot) -> None:
    view = PlaylistTracksView()
    qtbot.addWidget(view)

    statuses = {"v1": "downloaded"}
    view.show_tracks("My Mix", _tracks(), statuses)

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


def test_new_tracks_start_unchecked(qtbot) -> None:
    view = PlaylistTracksView()
    qtbot.addWidget(view)
    view.show_tracks("My Mix", _tracks(), {})
    assert view.selected_tracks() == []


def test_checking_individual_rows_selects_them(qtbot) -> None:
    view = PlaylistTracksView()
    qtbot.addWidget(view)
    view.show_tracks("My Mix", _tracks(), {})

    view._table.item(0, 0).setCheckState(Qt.CheckState.Checked)
    view._table.item(2, 0).setCheckState(Qt.CheckState.Checked)

    assert [t.video_id for t in view.selected_tracks()] == ["v1", "v3"]


def test_select_all_checkbox_checks_every_row(qtbot) -> None:
    view = PlaylistTracksView()
    qtbot.addWidget(view)
    view.show_tracks("My Mix", _tracks(), {})

    view._select_all_checkbox.setChecked(True)

    assert [t.video_id for t in view.selected_tracks()] == ["v1", "v2", "v3"]


def test_unchecking_one_row_after_select_all_keeps_others_checked(qtbot) -> None:
    # Regression: the "keep select-all checkbox in sync" logic must not
    # recursively force-uncheck every row when only one row changes.
    view = PlaylistTracksView()
    qtbot.addWidget(view)
    view.show_tracks("My Mix", _tracks(), {})

    view._select_all_checkbox.setChecked(True)
    view._table.item(1, 0).setCheckState(Qt.CheckState.Unchecked)

    assert [t.video_id for t in view.selected_tracks()] == ["v1", "v3"]
    assert view._select_all_checkbox.isChecked() is False


def test_download_button_emits_selected_tracks(qtbot) -> None:
    view = PlaylistTracksView()
    qtbot.addWidget(view)
    view.show_tracks("My Mix", _tracks(), {})
    view._table.item(0, 0).setCheckState(Qt.CheckState.Checked)

    with qtbot.waitSignal(view.download_selected_requested, timeout=1000) as blocker:
        view._download_button.click()

    emitted_tracks = blocker.args[0]
    assert [t.video_id for t in emitted_tracks] == ["v1"]


def test_download_button_does_nothing_when_none_selected(qtbot) -> None:
    view = PlaylistTracksView()
    qtbot.addWidget(view)
    view.show_tracks("My Mix", _tracks(), {})

    received = []
    view.download_selected_requested.connect(lambda tracks: received.append(tracks))
    view._download_button.click()

    assert received == []


def test_set_downloading_enabled_toggles_download_button(qtbot) -> None:
    view = PlaylistTracksView()
    qtbot.addWidget(view)

    view.set_downloading_enabled(False)
    assert view._download_button.isEnabled() is False
    view.set_downloading_enabled(True)
    assert view._download_button.isEnabled() is True
