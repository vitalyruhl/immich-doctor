from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from immich_doctor.backup.targets.models import SecretReferenceSummary
from immich_doctor.backup.targets.paths import backup_secret_path, backup_secret_root
from immich_doctor.core.config import AppSettings


class StoredSecretRecord(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    secret_id: str = Field(alias="secretId")
    kind: str
    label: str
    created_at: str = Field(alias="createdAt")
    material: str


@dataclass(slots=True)
class LocalSecretStore:
    def persist_secret(
        self,
        settings: AppSettings,
        *,
        kind: str,
        label: str,
        material: str,
    ) -> SecretReferenceSummary:
        secret_id = uuid4().hex
        record = StoredSecretRecord(
            secretId=secret_id,
            kind=kind,
            label=label,
            createdAt=datetime.now(UTC).isoformat(),
            material=self._normalize_material(kind=kind, material=material),
        )
        path = backup_secret_path(settings, secret_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(record.model_dump_json(by_alias=True, indent=2), encoding="utf-8")
        self._try_restrict_permissions(path)
        return self._summary(record)

    def reuse_secret(
        self,
        settings: AppSettings,
        *,
        secret_id: str,
    ) -> SecretReferenceSummary:
        record = self.load_secret(settings, secret_id=secret_id)
        return self._summary(record)

    def load_secret(self, settings: AppSettings, *, secret_id: str) -> StoredSecretRecord:
        path = backup_secret_path(settings, secret_id)
        return StoredSecretRecord.model_validate_json(path.read_text(encoding="utf-8"))

    def load_secret_material(self, settings: AppSettings, *, secret_id: str) -> str:
        record = self.load_secret(settings, secret_id=secret_id)
        return self._normalize_material(kind=record.kind, material=record.material)

    def root_exists(self, settings: AppSettings) -> bool:
        return backup_secret_root(settings).exists()

    def _summary(self, record: StoredSecretRecord) -> SecretReferenceSummary:
        return SecretReferenceSummary(
            secretId=record.secret_id,
            kind=record.kind,
            label=record.label,
            createdAt=record.created_at,
        )

    def _try_restrict_permissions(self, path: Path) -> None:
        try:
            os.chmod(path, 0o600)
        except OSError:
            return

    def _normalize_material(self, *, kind: str, material: str) -> str:
        if kind != "private_key":
            return material
        normalized = material.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
        if normalized and not normalized.endswith("\n"):
            normalized = f"{normalized}\n"
        return normalized
