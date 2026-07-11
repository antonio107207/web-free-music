from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ytmusic_sync.gui.status_labels import STATUS_LABELS
from ytmusic_sync.remote.models import RemoteTrack

_COL_TITLE = 0
_COL_ARTIST = 1
_COL_ALBUM = 2
_COL_DURATION = 3
_COL_STATUS = 4
_VIDEO_ID_ROLE = Qt.ItemDataRole.UserRole


def _format_duration(seconds: int | None) -> str:
    if not seconds:
        return ""
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes}:{secs:02d}"


class PlaylistTracksView(QWidget):
    download_selected_requested = Signal(list)  # list[RemoteTrack]

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._tracks: list[RemoteTrack] = []
        self._updating_checks = False

        layout = QVBoxLayout(self)

        self._title_label = QLabel("Select a playlist to see its tracks.")
        layout.addWidget(self._title_label)

        toolbar = QHBoxLayout()
        self._select_all_checkbox = QCheckBox("Select all")
        self._select_all_checkbox.stateChanged.connect(self._on_select_all_toggled)
        toolbar.addWidget(self._select_all_checkbox)
        toolbar.addStretch(1)
        self._download_button = QPushButton("Download Selected")
        self._download_button.clicked.connect(self._on_download_clicked)
        toolbar.addWidget(self._download_button)
        layout.addLayout(toolbar)

        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(["Title", "Artist", "Album", "Duration", "Status"])
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(_COL_TITLE, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(_COL_ARTIST, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(_COL_ALBUM, QHeaderView.ResizeMode.Stretch)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self._table, stretch=1)

    def show_loading(self, playlist_title: str) -> None:
        self._tracks = []
        self._title_label.setText(f"{playlist_title} — loading tracks...")
        self._table.setRowCount(0)
        self._select_all_checkbox.setChecked(False)

    def show_error(self, playlist_title: str, message: str) -> None:
        self._tracks = []
        self._title_label.setText(f"{playlist_title} — failed to load tracks: {message}")
        self._table.setRowCount(0)

    def show_tracks(
        self, playlist_title: str, tracks: list[RemoteTrack], statuses: dict[str, str]
    ) -> None:
        self._tracks = list(tracks)
        self._title_label.setText(f"{playlist_title} ({len(tracks)} tracks)")

        self._updating_checks = True
        self._table.setRowCount(len(tracks))
        for row, track in enumerate(tracks):
            status_key = statuses.get(track.video_id, "pending" if track.is_available else "unavailable")
            status_text = STATUS_LABELS.get(status_key, status_key)

            title_item = QTableWidgetItem(track.title)
            title_item.setFlags(title_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            title_item.setCheckState(Qt.CheckState.Unchecked)
            title_item.setData(_VIDEO_ID_ROLE, track.video_id)
            self._table.setItem(row, _COL_TITLE, title_item)
            self._table.setItem(row, _COL_ARTIST, QTableWidgetItem(track.artist or ""))
            self._table.setItem(row, _COL_ALBUM, QTableWidgetItem(track.album or ""))
            self._table.setItem(row, _COL_DURATION, QTableWidgetItem(_format_duration(track.duration_seconds)))
            self._table.setItem(row, _COL_STATUS, QTableWidgetItem(status_text))
        self._updating_checks = False
        self._select_all_checkbox.setChecked(False)

    def selected_tracks(self) -> list[RemoteTrack]:
        selected_ids = set()
        for row in range(self._table.rowCount()):
            item = self._table.item(row, _COL_TITLE)
            if item is not None and item.checkState() == Qt.CheckState.Checked:
                selected_ids.add(item.data(_VIDEO_ID_ROLE))
        return [t for t in self._tracks if t.video_id in selected_ids]

    def set_downloading_enabled(self, enabled: bool) -> None:
        self._download_button.setEnabled(enabled)

    def _on_select_all_toggled(self, state: int) -> None:
        if self._updating_checks:
            return
        check_state = (
            Qt.CheckState.Checked if Qt.CheckState(state) == Qt.CheckState.Checked else Qt.CheckState.Unchecked
        )
        self._updating_checks = True
        for row in range(self._table.rowCount()):
            item = self._table.item(row, _COL_TITLE)
            if item is not None:
                item.setCheckState(check_state)
        self._updating_checks = False

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._updating_checks or item.column() != _COL_TITLE:
            return
        # keep the "Select all" checkbox in sync when the user unchecks a single row
        all_checked = all(
            self._table.item(row, _COL_TITLE).checkState() == Qt.CheckState.Checked
            for row in range(self._table.rowCount())
        )
        self._updating_checks = True
        self._select_all_checkbox.setChecked(all_checked)
        self._updating_checks = False

    def _on_download_clicked(self) -> None:
        tracks = self.selected_tracks()
        if tracks:
            self.download_selected_requested.emit(tracks)
