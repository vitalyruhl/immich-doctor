from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from typing import Any


@dataclass(slots=True)
class EmptyFolderScanStatusTracker:
    _lock: Lock = field(default_factory=Lock, init=False, repr=False)
    _payload: dict[str, Any] = field(
        default_factory=lambda: {"status": "idle", "progress": 0, "eta_seconds": None},
        init=False,
        repr=False,
    )

    def start(self) -> None:
        with self._lock:
            self._payload = {"status": "running", "progress": 0, "eta_seconds": None}

    def update(self, payload: dict[str, Any]) -> None:
        with self._lock:
            directories = int(payload.get("directoriesScanned") or 0)
            progress = min(99, max(0, directories))
            self._payload = {
                "status": "running",
                "progress": progress,
                "eta_seconds": None,
                **payload,
            }

    def finish(self) -> None:
        with self._lock:
            self._payload = {"status": "done", "progress": 100, "eta_seconds": None}

    def fail(self, message: str) -> None:
        with self._lock:
            self._payload = {
                "status": "done",
                "progress": 100,
                "eta_seconds": None,
                "message": message,
            }

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._payload)
