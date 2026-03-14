from __future__ import annotations

from immich_doctor.core.models import CheckResult, CheckStatus
from immich_doctor.db.connection import can_connect


class PostgresAdapter:
    def validate_connection(self, dsn: str, timeout_seconds: int) -> CheckResult:
        connected, message = can_connect(dsn, timeout_seconds)
        return CheckResult(
            name="postgres_connection",
            status=CheckStatus.PASS if connected else CheckStatus.FAIL,
            message=message,
        )

