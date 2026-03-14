from __future__ import annotations

import os
from dataclasses import dataclass, field

try:
    import pwd
except ImportError:  # pragma: no cover - not available on Windows
    pwd = None

try:
    from grp import getgrgid
except ImportError:  # pragma: no cover - not available on Windows
    getgrgid = None

from immich_doctor.core.config import AppSettings
from immich_doctor.core.models import CheckResult, CheckStatus, ValidationReport
from immich_doctor.runtime.health.service import RuntimeHealthCheckService


@dataclass(slots=True)
class RuntimeValidationService:
    health: RuntimeHealthCheckService = field(default_factory=RuntimeHealthCheckService)

    def run(self, settings: AppSettings) -> ValidationReport:
        checks: list[CheckResult] = []
        checks.extend(self.health.run().checks)
        checks.append(self._validate_identity())

        return ValidationReport(
            domain="runtime",
            action="validate",
            summary="Runtime validation completed.",
            checks=checks,
            metadata={"environment": settings.environment},
        )

    def _validate_identity(self) -> CheckResult:
        uid = getattr(os, "getuid", lambda: None)()
        gid = getattr(os, "getgid", lambda: None)()

        return CheckResult(
            name="runtime_identity",
            status=CheckStatus.PASS,
            message="Runtime identity information collected.",
            details={
                "uid": uid,
                "gid": gid,
                "username": self._username(uid),
                "group": self._group_name(gid),
                "cwd": os.getcwd(),
                "umask": self._current_umask(),
            },
        )

    def _username(self, uid: int | None) -> str | None:
        if uid is None:
            return None
        if pwd is None:
            return None
        try:
            return pwd.getpwuid(uid).pw_name
        except KeyError:
            return None

    def _group_name(self, gid: int | None) -> str | None:
        if gid is None:
            return None
        if getgrgid is None:
            return None
        try:
            return getgrgid(gid).gr_name
        except KeyError:
            return None

    def _current_umask(self) -> str | None:
        if not hasattr(os, "umask"):
            return None
        current = os.umask(0)
        os.umask(current)
        return format(current, "03o")
