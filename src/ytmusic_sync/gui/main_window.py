from __future__ import annotations

import threading

from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ytmusic_sync.auth.ytm_auth import AuthError, YTMAuthManager
from ytmusic_sync.config import AppPaths, Settings
from ytmusic_sync.gui.library_browser import LibraryBrowser
from ytmusic_sync.gui.playlist_sidebar import PlaylistSidebar
from ytmusic_sync.gui.playlist_tracks_view import PlaylistTracksView
from ytmusic_sync.gui.progress_panel import ProgressPanel
from ytmusic_sync.gui.settings_dialog import SettingsDialog
from ytmusic_sync.gui.workers import (
    DownloadSignals,
    DownloadWorker,
    PlanSignals,
    PlanWorker,
    TracksFetchSignals,
    TracksFetchWorker,
)
from ytmusic_sync.remote.client import YTMusicClient
from ytmusic_sync.remote.models import RemotePlaylist
from ytmusic_sync.storage.repository import LibraryRepository
from ytmusic_sync.sync.planner import refresh_playlist_folder_links
from ytmusic_sync.sync.tasks import DownloadTask

try:
    from ytmusic_sync.gui.login_web_view_dialog import LoginWebViewDialog as _SetupDialogImpl

    _SETUP_DIALOG_NEEDS_PATHS = True
except ImportError:  # pragma: no cover - only exercised if QtWebEngine is unavailable
    from ytmusic_sync.gui.setup_dialog import SetupDialog as _SetupDialogImpl

    _SETUP_DIALOG_NEEDS_PATHS = False


class MainWindow(QMainWindow):
    def __init__(self, auth_manager: YTMAuthManager, paths: AppPaths) -> None:
        super().__init__()
        self._auth_manager = auth_manager
        self._paths = paths
        self._settings = Settings.load(paths.settings_file)
        self._repo = LibraryRepository(paths.db_file)

        self._client: YTMusicClient | None = None
        self._remote_playlists: list[RemotePlaylist] = []
        self._download_signals = DownloadSignals()
        self._plan_signals = PlanSignals()
        self._tracks_signals = TracksFetchSignals()
        self._pending_download_count = 0
        self._active_tracks_playlist_id: str | None = None
        self._cancel_event: threading.Event | None = None
        self._current_batch_tasks: dict[str, DownloadTask] = {}
        self._failed_tasks: dict[str, DownloadTask] = {}

        self.setWindowTitle("YT Music Sync")
        self.resize(900, 640)

        self._sidebar = PlaylistSidebar()
        self._sidebar.refresh_requested.connect(self.refresh_playlists)
        self._sidebar.selection_changed.connect(self._on_playlist_selection_changed)
        self._sidebar.playlist_activated.connect(self._on_playlist_activated)

        self._sync_now_button = QPushButton("Sync Now")
        self._sync_now_button.clicked.connect(self._on_sync_now_clicked)

        self._stop_button = QPushButton("Stop")
        self._stop_button.setEnabled(False)
        self._stop_button.clicked.connect(self._on_stop_clicked)

        self._retry_failed_button = QPushButton("Retry Failed")
        self._retry_failed_button.setEnabled(False)
        self._retry_failed_button.clicked.connect(self._on_retry_failed_clicked)

        self._progress_panel = ProgressPanel()

        self._sync_tab = QWidget()
        sync_layout = QVBoxLayout(self._sync_tab)
        sync_buttons_row = QHBoxLayout()
        sync_buttons_row.addWidget(self._sync_now_button)
        sync_buttons_row.addWidget(self._stop_button)
        sync_buttons_row.addWidget(self._retry_failed_button)
        sync_layout.addLayout(sync_buttons_row)
        sync_layout.addWidget(self._progress_panel, stretch=1)

        self._tracks_view = PlaylistTracksView()
        self._tracks_view.download_selected_requested.connect(self._on_download_selected_requested)
        self._library_browser = LibraryBrowser(self._repo)

        self._tabs = QTabWidget()
        self._tabs.addTab(self._sync_tab, "Sync")
        self._tabs.addTab(self._tracks_view, "Tracks")
        self._tabs.addTab(self._library_browser, "Library")

        splitter = QSplitter()
        splitter.addWidget(self._sidebar)
        splitter.addWidget(self._tabs)
        splitter.setSizes([260, 640])
        self.setCentralWidget(splitter)
        self.setStatusBar(QStatusBar())
        self._build_menu_bar()

        self._download_signals.track_started.connect(self._progress_panel.mark_started)
        self._download_signals.track_progress.connect(self._progress_panel.update_progress)
        self._download_signals.track_finished.connect(self._on_track_finished)
        self._plan_signals.plan_ready.connect(self._on_plan_ready)
        self._plan_signals.plan_failed.connect(self._on_plan_failed)
        self._tracks_signals.tracks_ready.connect(self._on_tracks_ready)
        self._tracks_signals.tracks_failed.connect(self._on_tracks_failed)

        self._ensure_authenticated()
        self.refresh_playlists()
        self._library_browser.refresh()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        self._repo.close()
        super().closeEvent(event)

    def _build_menu_bar(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        settings_action = file_menu.addAction("Settings...")
        settings_action.triggered.connect(self._on_settings_clicked)
        reauth_action = file_menu.addAction("Re-authenticate...")
        reauth_action.triggered.connect(self._on_reauthenticate_clicked)
        file_menu.addSeparator()
        quit_action = file_menu.addAction("Quit")
        quit_action.triggered.connect(self.close)

    def _on_settings_clicked(self) -> None:
        dialog = SettingsDialog(self._settings, self)
        if dialog.exec() == SettingsDialog.DialogCode.Accepted:
            self._settings = dialog.result_settings()
            self._settings.save(self._paths.settings_file)
            self.statusBar().showMessage("Settings saved.")

    def _on_reauthenticate_clicked(self) -> None:
        if self._run_setup_dialog():
            self.refresh_playlists()

    def _ensure_authenticated(self) -> None:
        if self._auth_manager.has_saved_auth():
            return
        self._run_setup_dialog()

    def _run_setup_dialog(self) -> bool:
        if _SETUP_DIALOG_NEEDS_PATHS:
            dialog = _SetupDialogImpl(self._auth_manager, self._paths, self)
        else:
            dialog = _SetupDialogImpl(self._auth_manager, self)
        return dialog.exec() == _SetupDialogImpl.DialogCode.Accepted

    def refresh_playlists(self) -> None:
        try:
            client = self._auth_manager.load_client()
            self._auth_manager.validate_client(client)
        except AuthError:
            message = (
                "Please connect your account to continue."
                if not self._auth_manager.has_saved_auth()
                else "Your saved login has expired. Please re-authenticate."
            )
            self.statusBar().showMessage(message)
            if not self._run_setup_dialog():
                return
            try:
                client = self._auth_manager.load_client()
            except AuthError as e:
                QMessageBox.critical(self, "Authentication failed", str(e))
                return

        self._client = YTMusicClient(client)
        try:
            self._remote_playlists = self._client.list_playlists()
        except Exception as e:  # noqa: BLE001 - surface any remote failure to the user
            QMessageBox.critical(self, "Failed to load playlists", str(e))
            return

        selected_ids = set(self._repo.get_selected_playlist_ids())
        self._sidebar.set_playlists(self._remote_playlists, selected_ids)
        self.statusBar().showMessage(f"Loaded {len(self._remote_playlists)} playlists.")

    def _on_playlist_selection_changed(self, playlist_id: str, checked: bool) -> None:
        self._repo.set_playlist_selected(playlist_id, checked)

    def _on_playlist_activated(self, playlist_id: str) -> None:
        if self._client is None:
            return
        playlist = next((p for p in self._remote_playlists if p.playlist_id == playlist_id), None)
        if playlist is None:
            return

        self._active_tracks_playlist_id = playlist_id
        self._tracks_view.show_loading(playlist.title)
        self._tabs.setCurrentWidget(self._tracks_view)

        worker = TracksFetchWorker(self._client, playlist_id, self._tracks_signals)
        QThreadPool.globalInstance().start(worker)

    def _on_tracks_ready(self, playlist_id: str, tracks: list) -> None:
        if playlist_id != self._active_tracks_playlist_id:
            return  # user clicked a different playlist before this one finished loading
        playlist = next((p for p in self._remote_playlists if p.playlist_id == playlist_id), None)
        if playlist is None:
            return
        # Keep the local index up to date with what's actually in the playlist right
        # now, so per-track status/downloads work even if this playlist was never
        # checked for whole-playlist sync.
        self._repo.upsert_remote_snapshot(playlist, tracks)
        statuses = self._repo.get_statuses([t.video_id for t in tracks])
        self._tracks_view.show_tracks(playlist.title, tracks, statuses)

    def _on_tracks_failed(self, playlist_id: str, message: str) -> None:
        if playlist_id != self._active_tracks_playlist_id:
            return
        playlist = next((p for p in self._remote_playlists if p.playlist_id == playlist_id), None)
        title = playlist.title if playlist else playlist_id
        self._tracks_view.show_error(title, message)

    def _on_sync_now_clicked(self) -> None:
        if self._client is None:
            return
        if self._pending_download_count > 0:
            QMessageBox.information(self, "Download in progress", "Please wait for the current download to finish.")
            return
        selected_ids = self._sidebar.selected_playlist_ids()
        if not selected_ids:
            QMessageBox.information(self, "Nothing selected", "Select at least one playlist to sync.")
            return

        self._set_download_controls_enabled(False)
        self.statusBar().showMessage("Planning sync...")
        plan_worker = PlanWorker(
            self._paths.db_file, self._client, selected_ids, self._remote_playlists, self._plan_signals
        )
        QThreadPool.globalInstance().start(plan_worker)

    def _on_plan_failed(self, message: str) -> None:
        self._set_download_controls_enabled(True)
        QMessageBox.critical(self, "Sync planning failed", message)

    def _on_plan_ready(self, tasks: list) -> None:
        if not tasks:
            self.statusBar().showMessage("Everything is already up to date.")
            self._set_download_controls_enabled(True)
            return
        self._start_downloads(tasks)

    def _on_download_selected_requested(self, tracks: list) -> None:
        if self._client is None:
            return
        if self._pending_download_count > 0:
            QMessageBox.information(self, "Download in progress", "Please wait for the current download to finish.")
            return

        playlist = next(
            (p for p in self._remote_playlists if p.playlist_id == self._active_tracks_playlist_id), None
        )
        playlist_title = playlist.title if playlist is not None else "Unknown Playlist"
        tasks = [
            DownloadTask(
                video_id=t.video_id,
                title=t.title,
                artist=t.artist,
                album=t.album,
                duration_seconds=t.duration_seconds,
                thumbnail_url=t.thumbnail_url,
                playlist_title=playlist_title,
            )
            for t in tracks
        ]
        self._tabs.setCurrentWidget(self._sync_tab)
        self._start_downloads(tasks)

    def _start_downloads(self, tasks: list[DownloadTask]) -> None:
        self._settings = Settings.load(self._paths.settings_file)
        QThreadPool.globalInstance().setMaxThreadCount(max(1, self._settings.max_concurrent_downloads))

        self._cancel_event = threading.Event()
        self._current_batch_tasks = {task.video_id: task for task in tasks}
        self._set_download_controls_enabled(False)
        self._progress_panel.set_tasks(tasks)
        self._pending_download_count = len(tasks)
        self.statusBar().showMessage(f"Downloading {len(tasks)} track(s)...")

        for task in tasks:
            self._repo.mark_downloading(task.video_id)
            worker = DownloadWorker(
                task,
                self._download_signals,
                self._settings.library_root,
                self._settings.mp3_quality_kbps,
                self._cancel_event,
            )
            QThreadPool.globalInstance().start(worker)

    def _on_stop_clicked(self) -> None:
        if self._cancel_event is None:
            return
        self._cancel_event.set()
        self._stop_button.setEnabled(False)
        self.statusBar().showMessage("Stopping...")

    def _on_retry_failed_clicked(self) -> None:
        if self._pending_download_count > 0 or not self._failed_tasks:
            return
        tasks = list(self._failed_tasks.values())
        self._failed_tasks = {}
        self._tabs.setCurrentWidget(self._sync_tab)
        self._start_downloads(tasks)

    def _set_download_controls_enabled(self, enabled: bool) -> None:
        self._sync_now_button.setEnabled(enabled)
        self._tracks_view.set_downloading_enabled(enabled)
        self._stop_button.setEnabled(not enabled)
        self._retry_failed_button.setEnabled(enabled and bool(self._failed_tasks))

    def _on_track_finished(self, video_id: str, success: bool, message: str) -> None:
        self._progress_panel.mark_finished(video_id, success, message)
        if success:
            self._repo.mark_downloaded(video_id, message)
            self._failed_tasks.pop(video_id, None)
        else:
            self._repo.mark_failed(video_id, message)
            task = self._current_batch_tasks.get(video_id)
            if task is not None:
                self._failed_tasks[video_id] = task

        self._pending_download_count -= 1
        if self._pending_download_count <= 0:
            was_cancelled = self._cancel_event is not None and self._cancel_event.is_set()
            self._cancel_event = None
            refresh_playlist_folder_links(self._repo, self._settings.library_root)
            self._set_download_controls_enabled(True)
            self.statusBar().showMessage("Stopped." if was_cancelled else "Sync complete.")
            self._library_browser.refresh()
            if self._active_tracks_playlist_id is not None:
                self._on_playlist_activated(self._active_tracks_playlist_id)
