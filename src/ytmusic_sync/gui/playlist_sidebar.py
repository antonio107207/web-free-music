from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QPushButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from ytmusic_sync.remote.models import RemotePlaylist

_PLAYLIST_ID_ROLE = Qt.ItemDataRole.UserRole


class PlaylistSidebar(QWidget):
    selection_changed = Signal(str, bool)  # playlist_id, checked
    refresh_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._updating = False

        layout = QVBoxLayout(self)

        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["Playlist"])
        self._tree.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self._tree, stretch=1)

        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self.refresh_requested.emit)
        layout.addWidget(refresh_button)

    def set_playlists(self, playlists: list[RemotePlaylist], selected_ids: set[str]) -> None:
        self._updating = True
        self._tree.clear()
        for playlist in playlists:
            count_text = f" ({playlist.track_count} tracks)" if playlist.track_count else ""
            item = QTreeWidgetItem([f"{playlist.title}{count_text}"])
            item.setData(0, _PLAYLIST_ID_ROLE, playlist.playlist_id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                0, Qt.CheckState.Checked if playlist.playlist_id in selected_ids else Qt.CheckState.Unchecked
            )
            self._tree.addTopLevelItem(item)
        self._updating = False

    def selected_playlist_ids(self) -> list[str]:
        ids = []
        for i in range(self._tree.topLevelItemCount()):
            item = self._tree.topLevelItem(i)
            if item.checkState(0) == Qt.CheckState.Checked:
                ids.append(item.data(0, _PLAYLIST_ID_ROLE))
        return ids

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if self._updating:
            return
        playlist_id = item.data(0, _PLAYLIST_ID_ROLE)
        checked = item.checkState(0) == Qt.CheckState.Checked
        self.selection_changed.emit(playlist_id, checked)
