# YT Music Sync

A personal desktop tool to back up your own YouTube Music playlists and liked
songs as local MP3 files.

This is for personal use only, syncing your own account's library. Downloading
from YouTube is against its Terms of Service — use at your own discretion, for
your own personal backups.

## Requirements

- Python 3.10+
- [ffmpeg](https://ffmpeg.org/) installed and on your `PATH`
  - Debian/Ubuntu: `sudo apt install ffmpeg`
  - Fedora: `sudo dnf install ffmpeg`
  - Arch: `sudo pacman -S ffmpeg`
- A YouTube Music account (logged in via your browser)

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Run

```bash
ytmusic-sync
```

or, without installing the console script:

```bash
python -m ytmusic_sync.app
```

### Desktop shortcut (Linux)

```bash
scripts/install_desktop_entry.sh
```

Installs an app-menu entry and a Desktop icon using this machine's actual
paths (nothing is hardcoded — `ytmusic-sync.desktop.in` is a template filled
in at install time, so re-run this after moving/re-cloning the repo).

On GNOME, the Desktop icon will show as a generic file icon and won't launch
until you right-click it and choose **"Allow Launching"** once — this is a
deliberate Nautilus security step for any `.desktop` file on the Desktop
(there's no way to pre-approve it from a script). The app-menu entry doesn't
need this and shows the correct icon immediately.

### First-time setup

On first launch, the app opens an embedded browser window — just log in to
YouTube Music with your Google account normally. The window closes and your
session is captured automatically once login completes; nothing to copy or
paste. A persistent login profile means future re-authentication is usually
just as fast (you'll often already be signed in).

If the embedded browser can't load for some reason, click "Trouble logging
in? Paste cookie manually" for the old manual flow:

1. Open `music.youtube.com` in your own browser and make sure you're logged in.
2. Open Developer Tools (F12) → the **Console** tab.
3. Type `copy(document.cookie)` and press Enter — this copies your session
   cookie straight to your clipboard (nothing will print, that's expected).
4. Paste it into the dialog and click "Save & Continue".

Your saved login can expire at any time (if you log out or clear cookies
elsewhere) — if that happens, the app will prompt you to reconnect
(`File > Re-authenticate...`).

## Usage

1. Check the playlists (and/or "Liked Songs") you want to keep synced in the
   left sidebar.
2. Click **Sync Now**. New tracks download in the background; already
   downloaded tracks are skipped on future syncs.
3. Browse your local library, search, reveal files in your file manager, or
   queue a re-download from the **Library** tab.

Downloaded files are organized under your configured library folder
(default `~/Music/YTMusicSync`):

```
YTMusicSync/
  Tracks/<Artist>/<Album>/<Title>.mp3     # canonical copy, one per track
  Playlists/<Playlist Name>/<...>.mp3     # hardlinks mirroring your playlists
```

Settings (library folder, MP3 bitrate, max concurrent downloads) are under
`File > Settings...`.

## Troubleshooting

- **Downloads suddenly failing for many tracks at once**: YouTube changes
  break `yt-dlp` from time to time. Try `pip install --upgrade yt-dlp`.
- **"ffmpeg not found" on startup**: install ffmpeg via your distro's package
  manager (see Requirements above) and restart the app.
- **"Your saved login has expired"**: use `File > Re-authenticate...` and
  paste fresh headers.

## Development

```bash
pip install -e ".[dev]"
pytest
```

CLI sync (for testing the download engine without the GUI):

```bash
python scripts/run_cli_sync.py --playlist-id LM   # LM = Liked Songs
python scripts/run_cli_sync.py --all-selected
```
