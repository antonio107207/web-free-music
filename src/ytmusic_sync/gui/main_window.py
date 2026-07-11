from __future__ import annotations

from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import (
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
from ytmusic_sync.gui.setup_dialog import SetupDialog
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

        self.setWindowTitle("YT Music Sync")
        self.resize(900, 640)

        self._sidebar = PlaylistSidebar()
        self._sidebar.refresh_requested.connect(self.refresh_playlists)
        self._sidebar.selection_changed.connect(self._on_playlist_selection_changed)
        self._sidebar.playlist_activated.connect(self._on_playlist_activated)

        self._sync_now_button = QPushButton("Sync Now")
        self._sync_now_button.clicked.connect(self._on_sync_now_clicked)

        self._progress_panel = ProgressPanel()

        sync_tab = QWidget()
        sync_layout = QVBoxLayout(sync_tab)
        sync_layout.addWidget(self._sync_now_button)
        sync_layout.addWidget(self._progress_panel, stretch=1)

        self._tracks_view = PlaylistTracksView()
        self._library_browser = LibraryBrowser(self._repo)

        self._tabs = QTabWidget()
        self._tabs.addTab(sync_tab, "Sync")
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
        dialog = SetupDialog(self._auth_manager, self)
        return dialog.exec() == SetupDialog.DialogCode.Accepted

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
        selected_ids = self._sidebar.selected_playlist_ids()
        if not selected_ids:
            QMessageBox.information(self, "Nothing selected", "Select at least one playlist to sync.")
            return

        self._sync_now_button.setEnabled(False)
        self.statusBar().showMessage("Planning sync...")
        plan_worker = PlanWorker(
            self._paths.db_file, self._client, selected_ids, self._remote_playlists, self._plan_signals
        )
        QThreadPool.globalInstance().start(plan_worker)

    def _on_plan_failed(self, message: str) -> None:
        self._sync_now_button.setEnabled(True)
        QMessageBox.critical(self, "Sync planning failed", message)

    def _on_plan_ready(self, tasks: list) -> None:
        if not tasks:
            self.statusBar().showMessage("Everything is already up to date.")
            self._sync_now_button.setEnabled(True)
            return

        self._settings = Settings.load(self._paths.settings_file)
        QThreadPool.globalInstance().setMaxThreadCount(max(1, self._settings.max_concurrent_downloads))

        self._progress_panel.set_tasks(tasks)
        self._pending_download_count = len(tasks)
        self.statusBar().showMessage(f"Downloading {len(tasks)} track(s)...")

        for task in tasks:
            self._repo.mark_downloading(task.video_id)
            worker = DownloadWorker(
                task, self._download_signals, self._settings.library_root, self._settings.mp3_quality_kbps
            )
            QThreadPool.globalInstance().start(worker)

    def _on_track_finished(self, video_id: str, success: bool, message: str) -> None:
        self._progress_panel.mark_finished(video_id, success, message)
        if success:
            self._repo.mark_downloaded(video_id, message)
        else:
            self._repo.mark_failed(video_id, message)

        self._pending_download_count -= 1
        if self._pending_download_count <= 0:
            refresh_playlist_folder_links(self._repo, self._settings.library_root)
            self._sync_now_button.setEnabled(True)
            self.statusBar().showMessage("Sync complete.")
            self._library_browser.refresh()
            if self._active_tracks_playlist_id is not None:
                self._on_playlist_activated(self._active_tracks_playlist_id)
