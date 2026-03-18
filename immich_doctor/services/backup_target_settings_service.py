from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from immich_doctor.backup.targets.models import (
    BackupRestoreReadiness,
    BackupTargetConfig,
    BackupTargetTransportSettings,
    BackupTargetType,
    BackupTargetUpsertPayload,
    BackupTargetVerificationStatus,
    HostKeyVerificationStrategy,
    RetentionPolicy,
    SecretReferenceSummary,
)
from immich_doctor.backup.targets.paths import backup_config_root, backup_targets_config_path
from immich_doctor.backup.targets.secrets import LocalSecretStore
from immich_doctor.backup.targets.store import BackupTargetStore
from immich_doctor.core.config import AppSettings


@dataclass(slots=True)
class BackupTargetSettingsService:
    store: BackupTargetStore = field(default_factory=BackupTargetStore)
    secrets: LocalSecretStore = field(default_factory=LocalSecretStore)

    def list_targets(self, settings: AppSettings) -> dict[str, object]:
        items = [
            target.model_dump(by_alias=True, mode="json")
            for target in self.store.list_targets(settings)
        ]
        return {
            "generatedAt": datetime.now(UTC).isoformat(),
            "configPath": backup_targets_config_path(settings).as_posix(),
            "configRoot": backup_config_root(settings).as_posix(),
            "items": items,
            "limitations": [
                "Target configuration is persisted locally under the configured "
                "config path or data/config when CONFIG_PATH is unset.",
                "SMB targets are configuration and validation only in this phase; "
                "productive SMB backup execution is intentionally disabled.",
                "Restore readiness remains not implemented even when backup "
                "targets are configured.",
            ],
        }

    def create_target(
        self,
        settings: AppSettings,
        payload: BackupTargetUpsertPayload,
    ) -> dict[str, object]:
        document = self.store.load_document(settings)
        target = self._build_target(settings, payload=payload, existing=None)
        document.items.append(target)
        self.store.save_document(settings, document)
        return {
            "applied": True,
            "summary": "Backup target saved.",
            "item": target.model_dump(by_alias=True, mode="json"),
        }

    def get_target(self, settings: AppSettings, *, target_id: str) -> BackupTargetConfig:
        for target in self.store.load_document(settings).items:
            if target.target_id == target_id:
                return target
        raise KeyError(f"Backup target not found: {target_id}")

    def update_target(
        self,
        settings: AppSettings,
        *,
        target_id: str,
        payload: BackupTargetUpsertPayload,
    ) -> dict[str, object]:
        document = self.store.load_document(settings)
        for index, target in enumerate(document.items):
            if target.target_id != target_id:
                continue
            updated = self._build_target(settings, payload=payload, existing=target)
            document.items[index] = updated
            self.store.save_document(settings, document)
            return {
                "applied": True,
                "summary": "Backup target updated.",
                "item": updated.model_dump(by_alias=True, mode="json"),
            }
        raise KeyError(f"Backup target not found: {target_id}")

    def delete_target(self, settings: AppSettings, *, target_id: str) -> dict[str, object]:
        document = self.store.load_document(settings)
        remaining = [target for target in document.items if target.target_id != target_id]
        applied = len(remaining) != len(document.items)
        document.items = remaining
        self.store.save_document(settings, document)
        return {
            "applied": applied,
            "summary": "Backup target removed." if applied else "Backup target did not exist.",
            "targetId": target_id,
        }

    def save_target(
        self,
        settings: AppSettings,
        updated_target: BackupTargetConfig,
    ) -> BackupTargetConfig:
        document = self.store.load_document(settings)
        replaced = False
        for index, target in enumerate(document.items):
            if target.target_id != updated_target.target_id:
                continue
            document.items[index] = updated_target
            replaced = True
            break
        if not replaced:
            document.items.append(updated_target)
        self.store.save_document(settings, document)
        return updated_target

    def _build_target(
        self,
        settings: AppSettings,
        *,
        payload: BackupTargetUpsertPayload,
        existing: BackupTargetConfig | None,
    ) -> BackupTargetConfig:
        current_retention = existing.retention_policy if existing is not None else None
        retention_policy = payload.retention_policy or current_retention or RetentionPolicy()
        transport = BackupTargetTransportSettings(
            path=(
                self._validated_path(payload)
                if payload.target_type == BackupTargetType.LOCAL
                else None
            ),
            host=payload.host,
            port=payload.port,
            share=payload.share,
            remotePath=payload.remote_path,
            username=payload.username,
            authMode=payload.auth_mode,
            mountStrategy=payload.mount_strategy,
            mountedPath=payload.mounted_path,
            hostKeyVerification=payload.host_key_verification,
            hostKeyReference=payload.host_key_reference,
            passwordSecretRef=self._resolve_secret_reference(
                settings,
                secret_kind="password",
                requested=payload.password_secret,
                current=existing.transport.password_secret_ref if existing else None,
            ),
            privateKeySecretRef=self._resolve_secret_reference(
                settings,
                secret_kind="private_key",
                requested=payload.private_key_secret,
                current=existing.transport.private_key_secret_ref if existing else None,
            ),
        )
        created_at = existing.created_at if existing is not None else datetime.now(UTC).isoformat()
        return BackupTargetConfig(
            targetId=existing.target_id if existing else uuid4().hex,
            targetName=payload.target_name,
            targetType=payload.target_type,
            enabled=payload.enabled,
            transport=transport,
            verificationStatus=BackupTargetVerificationStatus.UNKNOWN,
            lastTestResult=existing.last_test_result if existing else None,
            lastSuccessfulBackup=existing.last_successful_backup if existing else None,
            retentionPolicy=retention_policy,
            restoreReadiness=BackupRestoreReadiness.NOT_IMPLEMENTED,
            sourceScope="files_only",
            schedulingCompatible=True,
            warnings=self._warnings_for_payload(payload),
            createdAt=created_at,
            updatedAt=datetime.now(UTC).isoformat(),
        )

    def _resolve_secret_reference(
        self,
        settings: AppSettings,
        *,
        secret_kind: str,
        requested: object,
        current: SecretReferenceSummary | None,
    ) -> SecretReferenceSummary | None:
        if requested is None:
            return current

        material = getattr(requested, "material", None)
        if material:
            label = getattr(requested, "label", None) or f"{secret_kind.replace('_', ' ')} secret"
            return self.secrets.persist_secret(
                settings,
                kind=secret_kind,
                label=label,
                material=material,
            )

        secret_id = getattr(requested, "secret_id", None)
        if secret_id:
            return self.secrets.reuse_secret(settings, secret_id=secret_id)
        return current

    def _validated_path(self, payload: BackupTargetUpsertPayload) -> str:
        if payload.path is None:
            raise ValueError("Local targets require a path.")
        path = Path(payload.path).expanduser()
        if not path.is_absolute():
            raise ValueError("Local targets require an absolute destination path.")
        return path.as_posix()

    def _warnings_for_payload(self, payload: BackupTargetUpsertPayload) -> list[str]:
        warnings: list[str] = []
        if payload.target_type == BackupTargetType.SMB:
            warnings.append(
                "SMB targets are configuration and validation only in this phase; "
                "productive execution is disabled."
            )
        if payload.target_type in {BackupTargetType.SSH, BackupTargetType.RSYNC}:
            warnings.append(
                "Remote targets currently provide files-only backup scope and do "
                "not imply restore readiness."
            )
            if payload.host_key_verification == HostKeyVerificationStrategy.INSECURE_ACCEPT_ANY:
                warnings.append(
                    "Host key verification is explicitly configured as insecure_accept_any."
                )
        if payload.retention_policy and payload.retention_policy.prune_automatically:
            warnings.append(
                "Automatic retention pruning is not implemented; old backups are "
                "never deleted automatically."
            )
        return warnings
