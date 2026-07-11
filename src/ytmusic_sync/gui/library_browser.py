from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QMenu,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ytmusic_sync.gui.status_labels import STATUS_LABELS
from ytmusic_sync.storage.repository import STATUS_DOWNLOADED, LibraryRepository

_COL_TITLE = 0
_COL_ARTIST = 1
_COL_ALBUM = 2
_COL_PLAYLISTS = 3
_COL_STATUS = 4
_VIDEO_ID_ROLE = Qt.ItemDataRole.UserRole
_ALL_STATUSES = "All statuses"


class LibraryBrowser(QWidget):
    def __init__(self, repo: LibraryRepository, parent=None) -> None:
        super().__init__(parent)
        self._repo = repo
        self._all_rows: list = []

        layout = QVBoxLayout(self)

        filters_row = QHBoxLayout()
        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText("Search by title or artist...")
        self._search_box.textChanged.connect(self._apply_filter)
        filters_row.addWidget(self._search_box, stretch=1)

        self._status_filter = QComboBox()
        self._status_filter.addItem(_ALL_STATUSES, userData=None)
        for status, label in STATUS_LABELS.items():
            self._status_filter.addItem(label, userData=status)
        self._status_filter.currentIndexChanged.connect(lambda _: self._apply_filter(self._search_box.text()))
        filters_row.addWidget(self._status_filter)
        layout.addLayout(filters_row)

        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(["Title", "Artist", "Album", "Playlists", "Status"])
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(_COL_TITLE, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(_COL_ARTIST, QHeaderView.ResizeMode.Stretch)
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSortingEnabled(True)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._show_context_menu)
        layout.addWidget(self._table, stretch=1)

    def refresh(self) -> None:
        self._all_rows = self._repo.list_all_tracks()
        self._apply_filter(self._search_box.text())

    def _apply_filter(self, text: str) -> None:
        query = text.strip().lower()
        status_filter = self._status_filter.currentData()
        rows = [
            r
            for r in self._all_rows
            if (not query or query in (r["title"] or "").lower() or query in (r["artist"] or "").lower())
            and (status_filter is None or r["status"] == status_filter)
        ]

        was_sorting = self._table.isSortingEnabled()
        self._table.setSortingEnabled(False)
        self._table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            title_item = QTableWidgetItem(r["title"])
            title_item.setData(_VIDEO_ID_ROLE, r["video_id"])
            self._table.setItem(i, _COL_TITLE, title_item)
            self._table.setItem(i, _COL_ARTIST, QTableWidgetItem(r["artist"] or ""))
            self._table.setItem(i, _COL_ALBUM, QTableWidgetItem(r["album"] or ""))
            self._table.setItem(i, _COL_PLAYLISTS, QTableWidgetItem(r["playlist_titles"] or ""))
            self._table.setItem(i, _COL_STATUS, QTableWidgetItem(STATUS_LABELS.get(r["status"], r["status"])))
        self._table.setSortingEnabled(was_sorting)

    def _show_context_menu(self, pos) -> None:
        row = self._table.rowAt(pos.y())
        if row < 0:
            return
        title_item = self._table.item(row, _COL_TITLE)
        video_id = title_item.data(_VIDEO_ID_ROLE)
        row_data = next((r for r in self._all_rows if r["video_id"] == video_id), None)
        if row_data is None:
            return

        menu = QMenu(self)
        reveal_action = None
        if row_data["status"] == STATUS_DOWNLOADED and row_data["file_path"]:
            reveal_action = menu.addAction("Reveal in file manager")
        redownload_action = menu.addAction("Re-download")

        chosen = menu.exec(self._table.viewport().mapToGlobal(pos))
        if chosen is None:
            return
        if chosen is reveal_action:
            file_path = Path(row_data["file_path"])
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(file_path.parent)))
        elif chosen is redownload_action:
            self._repo.mark_failed(video_id, "Queued for re-download")
            self.refresh()
            QMessageBox.information(
                self,
                "Queued for re-download",
                "This track will be downloaded again the next time you click 'Sync Now'.",
            )
