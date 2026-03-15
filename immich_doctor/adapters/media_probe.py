from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, UnidentifiedImageError


@dataclass(slots=True, frozen=True)
class MediaProbeResult:
    ok: bool
    detected_format: str | None = None
    error_category: str | None = None
    error_message: str | None = None


class MediaProbeAdapter:
    def ffprobe_available(self) -> bool:
        return shutil.which("ffprobe") is not None

    def probe_unknown(self, path: Path) -> MediaProbeResult:
        try:
            with path.open("rb") as handle:
                header = handle.read(16)
        except PermissionError as exc:
            return MediaProbeResult(
                ok=False,
                error_category="permission_denied",
                error_message=str(exc),
            )
        except FileNotFoundError as exc:
            return MediaProbeResult(
                ok=False,
                error_category="missing_file",
                error_message=str(exc),
            )
        except OSError as exc:
            return MediaProbeResult(
                ok=False,
                error_category="runtime_tooling_error",
                error_message=str(exc),
            )

        if not header:
            return MediaProbeResult(
                ok=False,
                error_category="truncated",
                error_message="Unknown file type probe read no data.",
            )
        return MediaProbeResult(ok=True)

    def probe_image(self, path: Path) -> MediaProbeResult:
        try:
            with Image.open(path) as image:
                image.verify()
                detected_format = image.format.lower() if image.format else None
        except PermissionError as exc:
            return MediaProbeResult(
                ok=False,
                error_category="permission_denied",
                error_message=str(exc),
            )
        except FileNotFoundError as exc:
            return MediaProbeResult(
                ok=False,
                error_category="missing_file",
                error_message=str(exc),
            )
        except UnidentifiedImageError as exc:
            return MediaProbeResult(
                ok=False,
                error_category="type_mismatch",
                error_message=str(exc),
            )
        except OSError as exc:
            error_message = str(exc)
            return MediaProbeResult(
                ok=False,
                error_category=self._classify_image_error(error_message),
                error_message=error_message,
            )

        return MediaProbeResult(ok=True, detected_format=detected_format)

    def probe_av(self, path: Path) -> MediaProbeResult:
        if not self.ffprobe_available():
            return MediaProbeResult(
                ok=False,
                error_category="tool_missing",
                error_message="ffprobe is not available on PATH.",
            )

        command = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=format_name",
            "-of",
            "json",
            str(path),
        ]
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
        except PermissionError as exc:
            return MediaProbeResult(
                ok=False,
                error_category="permission_denied",
                error_message=str(exc),
            )
        except OSError as exc:
            return MediaProbeResult(
                ok=False,
                error_category="runtime_tooling_error",
                error_message=str(exc),
            )

        if completed.returncode != 0:
            error_message = (completed.stderr or completed.stdout or "").strip()
            return MediaProbeResult(
                ok=False,
                error_category=self._classify_ffprobe_error(error_message),
                error_message=error_message or "ffprobe failed without stderr output.",
            )

        detected_format = self._extract_ffprobe_format(completed.stdout)
        return MediaProbeResult(ok=True, detected_format=detected_format)

    def _classify_image_error(self, error_message: str) -> str:
        lowered = error_message.lower()
        if "truncated" in lowered or "unexpected end of file" in lowered or "eof" in lowered:
            return "truncated"
        if "cannot identify image file" in lowered:
            return "type_mismatch"
        return "corrupted"

    def _classify_ffprobe_error(self, error_message: str) -> str:
        lowered = error_message.lower()
        if "permission denied" in lowered:
            return "permission_denied"
        if "no such file" in lowered or "not found" in lowered:
            return "missing_file"
        if "moov atom not found" in lowered:
            return "container_broken"
        if "invalid data found when processing input" in lowered:
            return "container_broken"
        if "end of file" in lowered or "truncated" in lowered:
            return "truncated"
        if "invalid argument" in lowered or "unsupported" in lowered:
            return "unsupported_format"
        return "runtime_tooling_error"

    def _extract_ffprobe_format(self, payload: str) -> str | None:
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            return None
        format_name = parsed.get("format", {}).get("format_name")
        return str(format_name).lower() if format_name else None
