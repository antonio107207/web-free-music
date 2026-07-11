from __future__ import annotations

from ytmusic_sync.storage.repository import (
    STATUS_DOWNLOADED,
    STATUS_DOWNLOADING,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_UNAVAILABLE,
)

STATUS_LABELS: dict[str, str] = {
    STATUS_PENDING: "Not downloaded",
    STATUS_DOWNLOADING: "Downloading...",
    STATUS_DOWNLOADED: "Downloaded",
    STATUS_FAILED: "Failed",
    STATUS_UNAVAILABLE: "Unavailable",
}
