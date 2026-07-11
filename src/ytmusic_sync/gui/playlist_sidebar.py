from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QPushButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from ytmusic_sync.remote.models import RemotePlaylist

_PLAYLIST_ID_ROLE = Qt.ItemDataRole.UserRole


class PlaylistSidebar(QWidget):
    playlist_activated = Signal(str)  # playlist_id, emitted when a row is clicked
    refresh_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)

        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["Playlist"])
        self._tree.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self._tree, stretch=1)

        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self.refresh_requested.emit)
        layout.addWidget(refresh_button)

    def set_playlists(self, playlists: list[RemotePlaylist]) -> None:
        self._tree.clear()
        for playlist in playlists:
            count_text = f" ({playlist.track_count} tracks)" if playlist.track_count else ""
            item = QTreeWidgetItem([f"{playlist.title}{count_text}"])
            item.setData(0, _PLAYLIST_ID_ROLE, playlist.playlist_id)
            self._tree.addTopLevelItem(item)

    def _on_item_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        self.playlist_activated.emit(item.data(0, _PLAYLIST_ID_ROLE))
