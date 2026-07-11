from __future__ import annotations

import json
import stat
from dataclasses import asdict, dataclass, field
from pathlib import Path

import platformdirs

APP_NAME = "ytmusic-sync"


class AppPaths:
    def __init__(self) -> None:
        self.config_dir = Path(platformdirs.user_config_dir(APP_NAME))
        self.data_dir = Path(platformdirs.user_data_dir(APP_NAME))
        self.log_dir = Path(platformdirs.user_log_dir(APP_NAME))
        for d in (self.config_dir, self.data_dir, self.log_dir):
            d.mkdir(parents=True, exist_ok=True)

    @property
    def auth_file(self) -> Path:
        return self.config_dir / "auth.json"

    @property
    def settings_file(self) -> Path:
        return self.config_dir / "settings.json"

    @property
    def db_file(self) -> Path:
        return self.data_dir / "library.sqlite3"

    def secure_auth_file(self) -> None:
        if self.auth_file.exists():
            self.auth_file.chmod(stat.S_IRUSR | stat.S_IWUSR)


@dataclass
class Settings:
    library_root: Path = field(default_factory=lambda: Path.home() / "Music" / "YTMusicSync")
    mp3_quality_kbps: str = "192"
    max_concurrent_downloads: int = 3

    @classmethod
    def load(cls, path: Path) -> "Settings":
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return cls()
        defaults = cls()
        return cls(
            library_root=Path(data.get("library_root", defaults.library_root)),
            mp3_quality_kbps=str(data.get("mp3_quality_kbps", defaults.mp3_quality_kbps)),
            max_concurrent_downloads=int(
                data.get("max_concurrent_downloads", defaults.max_concurrent_downloads)
            ),
        )

    def save(self, path: Path) -> None:
        payload = asdict(self)
        payload["library_root"] = str(self.library_root)
        path.write_text(json.dumps(payload, indent=2))
