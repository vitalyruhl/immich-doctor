from __future__ import annotations

import shutil

from immich_doctor.core.models import CheckResult, CheckStatus


class ExternalToolsAdapter:
    def validate_required_tools(self, tools: list[str]) -> list[CheckResult]:
        checks: list[CheckResult] = []
        for tool in tools:
            location = shutil.which(tool)
            if location:
                checks.append(
                    CheckResult(
                        name=f"tool_{tool}",
                        status=CheckStatus.PASS,
                        message="Required external tool is available.",
                        details={"tool": tool, "path": location},
                    )
                )
            else:
                checks.append(
                    CheckResult(
                        name=f"tool_{tool}",
                        status=CheckStatus.FAIL,
                        message="Required external tool is not available on PATH.",
                        details={"tool": tool},
                    )
                )
        return checks

