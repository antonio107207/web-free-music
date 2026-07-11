from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QWidget,
)

from ytmusic_sync.config import Settings

_BITRATE_OPTIONS = ["128", "192", "256", "320"]


class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self._settings = settings

        form = QFormLayout(self)

        library_root_row = QWidget()
        library_root_layout = QHBoxLayout(library_root_row)
        library_root_layout.setContentsMargins(0, 0, 0, 0)
        self._library_root_edit = QLineEdit(str(settings.library_root))
        browse_button = QPushButton("Browse...")
        browse_button.clicked.connect(self._on_browse)
        library_root_layout.addWidget(self._library_root_edit)
        library_root_layout.addWidget(browse_button)
        form.addRow("Library folder:", library_root_row)

        self._bitrate_combo = QComboBox()
        self._bitrate_combo.addItems(_BITRATE_OPTIONS)
        if settings.mp3_quality_kbps in _BITRATE_OPTIONS:
            self._bitrate_combo.setCurrentText(settings.mp3_quality_kbps)
        form.addRow("MP3 bitrate (kbps):", self._bitrate_combo)

        self._concurrency_spin = QSpinBox()
        self._concurrency_spin.setRange(1, 8)
        self._concurrency_spin.setValue(settings.max_concurrent_downloads)
        form.addRow("Max concurrent downloads:", self._concurrency_spin)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _on_browse(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Choose library folder", self._library_root_edit.text())
        if directory:
            self._library_root_edit.setText(directory)

    def result_settings(self) -> Settings:
        return Settings(
            library_root=Path(self._library_root_edit.text()),
            mp3_quality_kbps=self._bitrate_combo.currentText(),
            max_concurrent_downloads=self._concurrency_spin.value(),
        )
