from __future__ import annotations

from dataclasses import dataclass

from immich_doctor.backup.targets.models import BackupTargetConfig, BackupTargetsDocument
from immich_doctor.backup.targets.paths import backup_targets_config_path
from immich_doctor.core.config import AppSettings


@dataclass(slots=True)
class BackupTargetStore:
    def load_document(self, settings: AppSettings) -> BackupTargetsDocument:
        path = backup_targets_config_path(settings)
        if not path.exists():
            return BackupTargetsDocument()
        return BackupTargetsDocument.model_validate_json(path.read_text(encoding="utf-8"))

    def save_document(
        self,
        settings: AppSettings,
        document: BackupTargetsDocument,
    ) -> BackupTargetsDocument:
        path = backup_targets_config_path(settings)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(document.model_dump_json(by_alias=True, indent=2), encoding="utf-8")
        return document

    def list_targets(self, settings: AppSettings) -> list[BackupTargetConfig]:
        return self.load_document(settings).items
