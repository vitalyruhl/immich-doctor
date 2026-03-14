from __future__ import annotations

import platform
import sys

from immich_doctor.core.models import CheckResult, CheckStatus, ValidationReport
from immich_doctor.version import __version__


class RuntimeHealthCheckService:
    def run(self) -> ValidationReport:
        checks = [
            CheckResult(
                name="python_runtime",
                status=CheckStatus.PASS,
                message="Python runtime is available.",
                details={"version": sys.version.split()[0]},
            ),
            CheckResult(
                name="platform",
                status=CheckStatus.PASS,
                message="Platform information collected.",
                details={"platform": platform.platform()},
            ),
        ]
        return ValidationReport(
            domain="runtime.health",
            action="check",
            summary="Runtime health checks completed.",
            checks=checks,
            metadata={"version": __version__},
        )
