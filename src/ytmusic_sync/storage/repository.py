from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path

from ytmusic_sync.remote.models import RemotePlaylist, RemoteTrack

STATUS_PENDING = "pending"
STATUS_DOWNLOADING = "downloading"
STATUS_DOWNLOADED = "downloaded"
STATUS_FAILED = "failed"
STATUS_UNAVAILABLE = "unavailable"


@dataclass
class TrackRow:
    video_id: str
    title: str
    artist: str | None
    album: str | None
    duration_seconds: int | None
    thumbnail_url: str | None
    file_path: str | None
    status: str


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _schema_sql() -> str:
    return resources.files("ytmusic_sync.storage").joinpath("schema.sql").read_text()


class LibraryRepository:
    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(_schema_sql())
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # -- playlists -----------------------------------------------------

    def upsert_remote_snapshot(self, playlist: RemotePlaylist, tracks: list[RemoteTrack]) -> None:
        conn = self._conn
        conn.execute(
            """
            INSERT INTO playlists (playlist_id, title, last_synced_at)
            VALUES (?, ?, ?)
            ON CONFLICT(playlist_id) DO UPDATE SET
                title = excluded.title,
                last_synced_at = excluded.last_synced_at
            """,
            (playlist.playlist_id, playlist.title, _now()),
        )
        # A real playlist can contain the same track more than once (a user added it
        # twice, etc). playlist_tracks has a (playlist_id, video_id) primary key -- it
        # records membership, not "how many times", so dedupe by video_id here, keeping
        # each track's first position.
        seen_video_ids: set[str] = set()
        deduped_tracks: list[RemoteTrack] = []
        for track in tracks:
            if track.video_id and track.video_id not in seen_video_ids:
                seen_video_ids.add(track.video_id)
                deduped_tracks.append(track)

        for track in deduped_tracks:
            status = STATUS_UNAVAILABLE if not track.is_available else STATUS_PENDING
            conn.execute(
                """
                INSERT INTO tracks (video_id, title, artist, album, duration_seconds,
                                     thumbnail_url, status, added_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(video_id) DO UPDATE SET
                    title = excluded.title,
                    artist = excluded.artist,
                    album = excluded.album,
                    duration_seconds = excluded.duration_seconds,
                    thumbnail_url = excluded.thumbnail_url,
                    status = CASE
                        WHEN tracks.status IN ('downloaded', 'downloading') THEN tracks.status
                        WHEN excluded.status = 'unavailable' THEN 'unavailable'
                        WHEN tracks.status = 'unavailable' AND excluded.status != 'unavailable'
                            THEN 'pending'
                        ELSE tracks.status
                    END
                """,
                (
                    track.video_id,
                    track.title,
                    track.artist,
                    track.album,
                    track.duration_seconds,
                    track.thumbnail_url,
                    status,
                    _now(),
                ),
            )
        conn.execute("DELETE FROM playlist_tracks WHERE playlist_id = ?", (playlist.playlist_id,))
        conn.executemany(
            "INSERT INTO playlist_tracks (playlist_id, video_id, position) VALUES (?, ?, ?)",
            [(playlist.playlist_id, t.video_id, i) for i, t in enumerate(deduped_tracks)],
        )
        conn.commit()

    def set_playlist_selected(self, playlist_id: str, selected: bool) -> None:
        self._conn.execute(
            "UPDATE playlists SET selected = ? WHERE playlist_id = ?",
            (1 if selected else 0, playlist_id),
        )
        self._conn.commit()

    def get_selected_playlist_ids(self) -> list[str]:
        rows = self._conn.execute("SELECT playlist_id FROM playlists WHERE selected = 1").fetchall()
        return [r["playlist_id"] for r in rows]

    # -- tracks ----------------------------------------------------------

    def get_pending_tracks(self, playlist_ids: list[str]) -> list[TrackRow]:
        if not playlist_ids:
            return []
        placeholders = ",".join("?" for _ in playlist_ids)
        rows = self._conn.execute(
            f"""
            SELECT DISTINCT t.video_id, t.title, t.artist, t.album, t.duration_seconds,
                            t.thumbnail_url, t.file_path, t.status
            FROM tracks t
            JOIN playlist_tracks pt ON pt.video_id = t.video_id
            WHERE pt.playlist_id IN ({placeholders})
              AND t.status IN (?, ?)
            """,
            (*playlist_ids, STATUS_PENDING, STATUS_FAILED),
        ).fetchall()
        return [
            TrackRow(
                video_id=r["video_id"],
                title=r["title"],
                artist=r["artist"],
                album=r["album"],
                duration_seconds=r["duration_seconds"],
                thumbnail_url=r["thumbnail_url"],
                file_path=r["file_path"],
                status=r["status"],
            )
            for r in rows
        ]

    def get_playlist_titles_for_tracks(
        self, video_ids: list[str], playlist_ids: list[str]
    ) -> dict[str, list[str]]:
        """Playlist titles each of the given tracks belongs to, restricted to the
        given playlist_ids (e.g. the set currently selected for sync). Used to
        pick a download folder for a track that may belong to more than one of
        the playlists being synced in this batch.
        """
        if not video_ids or not playlist_ids:
            return {}
        video_placeholders = ",".join("?" for _ in video_ids)
        playlist_placeholders = ",".join("?" for _ in playlist_ids)
        rows = self._conn.execute(
            f"""
            SELECT pt.video_id, p.title AS playlist_title
            FROM playlist_tracks pt
            JOIN playlists p ON p.playlist_id = pt.playlist_id
            WHERE pt.video_id IN ({video_placeholders})
              AND pt.playlist_id IN ({playlist_placeholders})
            """,
            (*video_ids, *playlist_ids),
        ).fetchall()
        result: dict[str, list[str]] = {}
        for r in rows:
            result.setdefault(r["video_id"], []).append(r["playlist_title"])
        return result

    def get_statuses(self, video_ids: list[str]) -> dict[str, str]:
        if not video_ids:
            return {}
        placeholders = ",".join("?" for _ in video_ids)
        rows = self._conn.execute(
            f"SELECT video_id, status FROM tracks WHERE video_id IN ({placeholders})",
            video_ids,
        ).fetchall()
        return {r["video_id"]: r["status"] for r in rows}

    def mark_downloading(self, video_id: str) -> None:
        self._conn.execute(
            "UPDATE tracks SET status = ?, error_message = NULL WHERE video_id = ?",
            (STATUS_DOWNLOADING, video_id),
        )
        self._conn.commit()

    def mark_downloaded(self, video_id: str, file_path: Path) -> None:
        self._conn.execute(
            """
            UPDATE tracks SET status = ?, file_path = ?, downloaded_at = ?, error_message = NULL
            WHERE video_id = ?
            """,
            (STATUS_DOWNLOADED, str(file_path), _now(), video_id),
        )
        self._conn.commit()

    def mark_failed(self, video_id: str, error_message: str) -> None:
        self._conn.execute(
            "UPDATE tracks SET status = ?, error_message = ? WHERE video_id = ?",
            (STATUS_FAILED, error_message, video_id),
        )
        self._conn.commit()

    def reconcile_missing_files(self) -> int:
        rows = self._conn.execute(
            "SELECT video_id, file_path FROM tracks WHERE status = ? AND file_path IS NOT NULL",
            (STATUS_DOWNLOADED,),
        ).fetchall()
        reset_count = 0
        for r in rows:
            if not Path(r["file_path"]).exists():
                self._conn.execute(
                    """
                    UPDATE tracks SET status = ?, file_path = NULL, downloaded_at = NULL
                    WHERE video_id = ?
                    """,
                    (STATUS_PENDING, r["video_id"]),
                )
                reset_count += 1
        if reset_count:
            self._conn.commit()
        return reset_count

    def get_downloaded_tracks_with_playlists(self) -> dict[str, tuple[TrackRow, list[str]]]:
        rows = self._conn.execute(
            """
            SELECT t.video_id, t.title, t.artist, t.album, t.duration_seconds,
                   t.thumbnail_url, t.file_path, t.status, p.title AS playlist_title
            FROM tracks t
            JOIN playlist_tracks pt ON pt.video_id = t.video_id
            JOIN playlists p ON p.playlist_id = pt.playlist_id
            WHERE t.status = ? AND t.file_path IS NOT NULL
            """,
            (STATUS_DOWNLOADED,),
        ).fetchall()
        result: dict[str, tuple[TrackRow, list[str]]] = {}
        for r in rows:
            video_id = r["video_id"]
            if video_id not in result:
                track = TrackRow(
                    video_id=video_id,
                    title=r["title"],
                    artist=r["artist"],
                    album=r["album"],
                    duration_seconds=r["duration_seconds"],
                    thumbnail_url=r["thumbnail_url"],
                    file_path=r["file_path"],
                    status=r["status"],
                )
                result[video_id] = (track, [])
            result[video_id][1].append(r["playlist_title"])
        return result

    def list_all_tracks(self) -> list[sqlite3.Row]:
        return self._conn.execute(
            """
            SELECT t.*, GROUP_CONCAT(p.title, ', ') AS playlist_titles
            FROM tracks t
            LEFT JOIN playlist_tracks pt ON pt.video_id = t.video_id
            LEFT JOIN playlists p ON p.playlist_id = pt.playlist_id
            GROUP BY t.video_id
            ORDER BY t.artist, t.album, t.title
            """
        ).fetchall()
