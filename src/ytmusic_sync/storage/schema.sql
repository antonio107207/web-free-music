PRAGMA user_version = 1;

CREATE TABLE IF NOT EXISTS playlists (
    playlist_id    TEXT PRIMARY KEY,
    title          TEXT NOT NULL,
    selected       INTEGER NOT NULL DEFAULT 0,
    last_synced_at TEXT
);

CREATE TABLE IF NOT EXISTS tracks (
    video_id          TEXT PRIMARY KEY,
    title             TEXT NOT NULL,
    artist            TEXT,
    album             TEXT,
    duration_seconds  INTEGER,
    thumbnail_url     TEXT,
    file_path         TEXT,
    status            TEXT NOT NULL DEFAULT 'pending',
    error_message     TEXT,
    added_at          TEXT NOT NULL,
    downloaded_at     TEXT
);

CREATE TABLE IF NOT EXISTS playlist_tracks (
    playlist_id TEXT NOT NULL REFERENCES playlists(playlist_id) ON DELETE CASCADE,
    video_id    TEXT NOT NULL REFERENCES tracks(video_id) ON DELETE CASCADE,
    position    INTEGER,
    PRIMARY KEY (playlist_id, video_id)
);

CREATE INDEX IF NOT EXISTS idx_tracks_status ON tracks(status);
