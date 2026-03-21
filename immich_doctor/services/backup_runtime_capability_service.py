from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from immich_doctor.adapters.external_tools import ExternalToolsAdapter
from immich_doctor.core.models import CheckStatus
from immich_doctor.services.backup_job_service import BackgroundJobRuntime


@dataclass(slots=True)
class BackupRuntimeCapabilityService:
    runtime: BackgroundJobRuntime
    tools: ExternalToolsAdapter = field(default_factory=ExternalToolsAdapter)

    def probe_rsync(self) -> dict[str, object]:
        check = self.tools.inspect_runtime_tool(
            "rsync",
            version_argv=["rsync", "--version"],
        )
        summary = (
            "Local rsync is available in the doctor runtime."
            if check.status == CheckStatus.PASS
            else "Local rsync is not available in the doctor runtime."
        )
        snapshot = {
            "tool": "rsync",
            "checkedAt": datetime.now(UTC).isoformat(),
            "available": check.status == CheckStatus.PASS,
            "summary": summary,
            "check": check.to_dict(),
        }
        self.runtime.set_capability_snapshot("rsync", snapshot)
        return snapshot

    def trigger_startup_probe(self) -> dict[str, object]:
        return {
            "rsync": self.probe_rsync(),
        }

    def cached_rsync_snapshot(self) -> dict[str, object] | None:
        return self.runtime.get_capability_snapshot("rsync")
