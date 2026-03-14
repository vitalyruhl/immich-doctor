from __future__ import annotations

from contextlib import closing

import psycopg


def can_connect(dsn: str, timeout_seconds: int) -> tuple[bool, str]:
    try:
        with closing(psycopg.connect(dsn, connect_timeout=timeout_seconds)):
            return True, "PostgreSQL connection established."
    except Exception as exc:  # pragma: no cover - exact driver errors vary by environment
        return False, f"PostgreSQL connection failed: {exc}"
