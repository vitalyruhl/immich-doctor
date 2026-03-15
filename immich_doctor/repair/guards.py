from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4

from immich_doctor.repair.models import PlanToken


def fingerprint_payload(payload: Any) -> str:
    normalized = _normalize(payload)
    serialized = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
    return sha256(serialized.encode("utf-8")).hexdigest()


def build_live_state_fingerprint(*, db_fingerprint: str, file_fingerprint: str) -> str:
    return fingerprint_payload(
        {
            "db_fingerprint": db_fingerprint,
            "file_fingerprint": file_fingerprint,
        }
    )


def create_plan_token(
    *,
    scope: dict[str, Any],
    db_fingerprint: str,
    file_fingerprint: str,
    ttl: timedelta | None = timedelta(minutes=30),
    now: datetime | None = None,
) -> PlanToken:
    created = (now or datetime.now(UTC)).astimezone(UTC)
    expires_at = (created + ttl).isoformat() if ttl is not None else None
    return PlanToken(
        token_id=uuid4().hex,
        created_at=created.isoformat(),
        scope=scope,
        db_fingerprint=db_fingerprint,
        file_fingerprint=file_fingerprint,
        expires_at=expires_at,
    )


@dataclass(slots=True, frozen=True)
class ApplyGuardResult:
    valid: bool
    reason: str
    token_id: str
    expected_db_fingerprint: str
    expected_file_fingerprint: str
    actual_db_fingerprint: str
    actual_file_fingerprint: str


def validate_plan_token(
    token: PlanToken,
    *,
    scope: dict[str, Any],
    db_fingerprint: str,
    file_fingerprint: str,
    now: datetime | None = None,
) -> ApplyGuardResult:
    current = (now or datetime.now(UTC)).astimezone(UTC)
    if token.expires_at is not None:
        expires = datetime.fromisoformat(token.expires_at)
        if current > expires:
            return ApplyGuardResult(
                valid=False,
                reason="Plan token expired before apply.",
                token_id=token.token_id,
                expected_db_fingerprint=token.db_fingerprint,
                expected_file_fingerprint=token.file_fingerprint,
                actual_db_fingerprint=db_fingerprint,
                actual_file_fingerprint=file_fingerprint,
            )

    if fingerprint_payload(scope) != fingerprint_payload(token.scope):
        return ApplyGuardResult(
            valid=False,
            reason="Repair scope changed between inspect and apply.",
            token_id=token.token_id,
            expected_db_fingerprint=token.db_fingerprint,
            expected_file_fingerprint=token.file_fingerprint,
            actual_db_fingerprint=db_fingerprint,
            actual_file_fingerprint=file_fingerprint,
        )

    if token.db_fingerprint != db_fingerprint or token.file_fingerprint != file_fingerprint:
        return ApplyGuardResult(
            valid=False,
            reason="Live state drift detected between inspect and apply.",
            token_id=token.token_id,
            expected_db_fingerprint=token.db_fingerprint,
            expected_file_fingerprint=token.file_fingerprint,
            actual_db_fingerprint=db_fingerprint,
            actual_file_fingerprint=file_fingerprint,
        )

    return ApplyGuardResult(
        valid=True,
        reason="Plan token matches the current live state.",
        token_id=token.token_id,
        expected_db_fingerprint=token.db_fingerprint,
        expected_file_fingerprint=token.file_fingerprint,
        actual_db_fingerprint=db_fingerprint,
        actual_file_fingerprint=file_fingerprint,
    )


def _normalize(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, dict):
        return {str(key): _normalize(val) for key, val in sorted(value.items(), key=str)}
    if isinstance(value, list | tuple | set | frozenset):
        return [_normalize(item) for item in value]
    return value
