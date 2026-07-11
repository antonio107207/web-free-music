from __future__ import annotations

from PySide6.QtWidgets import QHeaderView, QProgressBar, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from ytmusic_sync.sync.tasks import DownloadTask

_COL_TITLE = 0
_COL_ARTIST = 1
_COL_STATUS = 2
_COL_PROGRESS = 3


class ProgressPanel(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._row_by_video_id: dict[str, int] = {}
        self._total = 0
        self._finished = 0

        layout = QVBoxLayout(self)

        self._overall_bar = QProgressBar()
        self._overall_bar.setFormat("%v / %m tracks")
        layout.addWidget(self._overall_bar)

        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["Title", "Artist", "Status", "Progress"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._table.verticalHeader().setVisible(False)
        layout.addWidget(self._table, stretch=1)

    def set_tasks(self, tasks: list[DownloadTask]) -> None:
        self._row_by_video_id.clear()
        self._total = len(tasks)
        self._finished = 0
        self._table.setRowCount(len(tasks))
        self._overall_bar.setRange(0, max(self._total, 1))
        self._overall_bar.setValue(0)

        for row, task in enumerate(tasks):
            self._row_by_video_id[task.video_id] = row
            self._table.setItem(row, _COL_TITLE, QTableWidgetItem(task.title))
            self._table.setItem(row, _COL_ARTIST, QTableWidgetItem(task.artist or ""))
            self._table.setItem(row, _COL_STATUS, QTableWidgetItem("Queued"))
            progress_bar = QProgressBar()
            progress_bar.setRange(0, 100)
            progress_bar.setValue(0)
            self._table.setCellWidget(row, _COL_PROGRESS, progress_bar)

    def mark_started(self, video_id: str) -> None:
        row = self._row_by_video_id.get(video_id)
        if row is None:
            return
        self._table.item(row, _COL_STATUS).setText("Downloading")

    def update_progress(self, video_id: str, fraction: float) -> None:
        row = self._row_by_video_id.get(video_id)
        if row is None:
            return
        bar = self._table.cellWidget(row, _COL_PROGRESS)
        if isinstance(bar, QProgressBar):
            bar.setValue(int(fraction * 100))

    def mark_finished(self, video_id: str, success: bool, message: str) -> None:
        row = self._row_by_video_id.get(video_id)
        if row is not None:
            self._table.item(row, _COL_STATUS).setText("Done" if success else f"Failed: {message}")
            bar = self._table.cellWidget(row, _COL_PROGRESS)
            if isinstance(bar, QProgressBar):
                bar.setValue(100 if success else bar.value())

        self._finished += 1
        self._overall_bar.setValue(self._finished)

    def is_all_finished(self) -> bool:
        return self._total > 0 and self._finished >= self._total
