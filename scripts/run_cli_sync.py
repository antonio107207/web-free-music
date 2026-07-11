#!/usr/bin/env python3
"""Headless sync runner for testing the download engine without the GUI.

Usage:
    python scripts/run_cli_sync.py --playlist-id LM
    python scripts/run_cli_sync.py --all-selected
"""
from __future__ import annotations

import argparse
import sys

from ytmusic_sync.auth.ytm_auth import AuthError, YTMAuthManager
from ytmusic_sync.config import AppPaths, Settings
from ytmusic_sync.remote.client import YTMusicClient
from ytmusic_sync.storage.repository import LibraryRepository
from ytmusic_sync.sync.downloader import download_track
from ytmusic_sync.sync.planner import build_sync_plan, refresh_playlist_folder_links


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--playlist-id", help="Sync a single playlist id (use 'LM' for Liked Songs)")
    group.add_argument(
        "--all-selected", action="store_true", help="Sync all playlists marked selected in the DB"
    )
    args = parser.parse_args()

    paths = AppPaths()
    auth_manager = YTMAuthManager(paths)
    if not auth_manager.has_saved_auth():
        print("No saved credentials. Run the GUI app once to complete setup first.", file=sys.stderr)
        return 1

    try:
        yt_client = auth_manager.load_client()
        auth_manager.validate_client(yt_client)
    except AuthError as e:
        print(f"Authentication error: {e}", file=sys.stderr)
        return 1

    client = YTMusicClient(yt_client)
    repo = LibraryRepository(paths.db_file)
    settings = Settings.load(paths.settings_file)

    if args.playlist_id:
        repo.set_playlist_selected(args.playlist_id, True)
        selected_ids = [args.playlist_id]
    else:
        selected_ids = repo.get_selected_playlist_ids()
        if not selected_ids:
            print("No playlists are marked selected.", file=sys.stderr)
            return 1

    print(f"Planning sync for playlists: {selected_ids}")
    tasks = build_sync_plan(repo, client, selected_ids)
    print(f"{len(tasks)} track(s) to download.")

    succeeded = 0
    failed = 0
    for i, task in enumerate(tasks, start=1):
        print(f"[{i}/{len(tasks)}] {task.artist} - {task.title} ...", end=" ", flush=True)
        repo.mark_downloading(task.video_id)

        def hook(d: dict, _title: str = task.title) -> None:
            if d.get("status") == "downloading":
                pct = d.get("_percent_str", "").strip()
                if pct:
                    print(f"\r  {pct}", end="", flush=True)

        try:
            final_path = download_track(task, settings.library_root, settings.mp3_quality_kbps, hook)
            repo.mark_downloaded(task.video_id, final_path)
            succeeded += 1
            print(f"\rdone -> {final_path}")
        except Exception as e:  # noqa: BLE001 - one bad track shouldn't abort the whole sync
            repo.mark_failed(task.video_id, str(e))
            failed += 1
            print(f"\rFAILED: {e}")

    refresh_playlist_folder_links(repo, settings.library_root)
    repo.close()

    print(f"\nDone. {succeeded} succeeded, {failed} failed.")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
