from __future__ import annotations

from PySide6.QtWidgets import QHeaderView, QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from ytmusic_sync.remote.models import RemoteTrack

_COL_TITLE = 0
_COL_ARTIST = 1
_COL_ALBUM = 2
_COL_DURATION = 3
_COL_STATUS = 4

_STATUS_LABELS = {
    "pending": "Not downloaded",
    "downloading": "Downloading...",
    "downloaded": "Downloaded",
    "failed": "Failed",
    "unavailable": "Unavailable",
}


def _format_duration(seconds: int | None) -> str:
    if not seconds:
        return ""
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes}:{secs:02d}"


class PlaylistTracksView(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)

        self._title_label = QLabel("Select a playlist to see its tracks.")
        layout.addWidget(self._title_label)

        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(["Title", "Artist", "Album", "Duration", "Status"])
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(_COL_TITLE, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(_COL_ARTIST, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(_COL_ALBUM, QHeaderView.ResizeMode.Stretch)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self._table, stretch=1)

    def show_loading(self, playlist_title: str) -> None:
        self._title_label.setText(f"{playlist_title} — loading tracks...")
        self._table.setRowCount(0)

    def show_error(self, playlist_title: str, message: str) -> None:
        self._title_label.setText(f"{playlist_title} — failed to load tracks: {message}")
        self._table.setRowCount(0)

    def show_tracks(
        self, playlist_title: str, tracks: list[RemoteTrack], statuses: dict[str, str]
    ) -> None:
        self._title_label.setText(f"{playlist_title} ({len(tracks)} tracks)")
        self._table.setRowCount(len(tracks))
        for row, track in enumerate(tracks):
            status_key = statuses.get(track.video_id, "pending" if track.is_available else "unavailable")
            status_text = _STATUS_LABELS.get(status_key, status_key)
            self._table.setItem(row, _COL_TITLE, QTableWidgetItem(track.title))
            self._table.setItem(row, _COL_ARTIST, QTableWidgetItem(track.artist or ""))
            self._table.setItem(row, _COL_ALBUM, QTableWidgetItem(track.album or ""))
            self._table.setItem(row, _COL_DURATION, QTableWidgetItem(_format_duration(track.duration_seconds)))
            self._table.setItem(row, _COL_STATUS, QTableWidgetItem(status_text))
