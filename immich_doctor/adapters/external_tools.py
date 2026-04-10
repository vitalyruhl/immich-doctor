from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

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

    def inspect_runtime_tool(
        self,
        tool: str,
        *,
        version_argv: list[str] | None = None,
    ) -> CheckResult:
        location = shutil.which(tool)
        if not location:
            return CheckResult(
                name=f"tool_{tool}",
                status=CheckStatus.FAIL,
                message=f"Required external tool `{tool}` is not available on PATH.",
                details={"tool": tool},
            )
        details: dict[str, object] = {"tool": tool, "path": location}
        if version_argv is not None:
            try:
                probe = subprocess.run(
                    version_argv,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
            except OSError as exc:
                return CheckResult(
                    name=f"tool_{tool}",
                    status=CheckStatus.FAIL,
                    message=f"Required external tool `{tool}` could not be executed: {exc}",
                    details=details,
                )
            except subprocess.TimeoutExpired:
                return CheckResult(
                    name=f"tool_{tool}",
                    status=CheckStatus.FAIL,
                    message=f"Required external tool `{tool}` did not respond in time.",
                    details=details,
                )
            if probe.returncode != 0:
                details["stdout"] = probe.stdout
                details["stderr"] = probe.stderr
                return CheckResult(
                    name=f"tool_{tool}",
                    status=CheckStatus.FAIL,
                    message=(
                        f"Required external tool `{tool}` is present on PATH, but the runtime "
                        "could not execute it successfully."
                    ),
                    details=details,
                )
            version_line = next(
                (line.strip() for line in probe.stdout.splitlines() if line.strip()),
                None,
            )
            if version_line is not None:
                details["version"] = version_line
        return CheckResult(
            name=f"tool_{tool}",
            status=CheckStatus.PASS,
            message=f"Required external tool `{tool}` is available in the runtime.",
            details=details,
        )

    def inspect_open_file_handles(self, path: Path) -> dict[str, object]:
        tool = "lsof"
        location = shutil.which(tool)
        if not location:
            return {
                "status": "unavailable",
                "tool": tool,
                "reason": f"Required external tool `{tool}` is not available on PATH.",
            }

        try:
            probe = subprocess.run(
                [location, str(path)],
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
            )
        except OSError as exc:
            return {
                "status": "failed",
                "tool": tool,
                "reason": f"External tool `{tool}` could not be executed: {exc}",
            }
        except subprocess.TimeoutExpired:
            return {
                "status": "failed",
                "tool": tool,
                "reason": f"External tool `{tool}` did not respond in time.",
            }

        if probe.returncode == 0:
            lines = [line for line in probe.stdout.splitlines() if line.strip()]
            return {
                "status": "in_use",
                "tool": tool,
                "reason": "Open file handles were detected for the path.",
                "stdout": probe.stdout,
                "handle_count": max(len(lines) - 1, 1),
            }
        if probe.returncode == 1:
            return {
                "status": "not_in_use",
                "tool": tool,
                "reason": "No open file handles were reported for the path.",
            }
        return {
            "status": "failed",
            "tool": tool,
            "reason": (
                f"External tool `{tool}` returned a non-zero status while inspecting the path."
            ),
            "stdout": probe.stdout,
            "stderr": probe.stderr,
            "returncode": probe.returncode,
        }
