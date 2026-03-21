from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from immich_doctor.backup.targets.models import (
    BackupRestoreReadiness,
    BackupTargetConfig,
    BackupTargetAuthMode,
    BackupTargetKnownHostMode,
    BackupTargetMountStrategy,
    BackupTargetTransportSettings,
    BackupTargetType,
    BackupTargetUpsertPayload,
    BackupTargetVerificationStatus,
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
                "SMB pre-mounted path targets may execute through the path-like "
                "workflow when the mounted path is already available. SMB system-mount "
                "execution remains disabled in this phase.",
                "Local targets provide partial asset-aware selective restore "
                "only after explicit review and confirmation; SSH/rsync targets "
                "still do not imply restore readiness.",
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
            port=payload.port or 22,
            share=payload.share,
            remotePath=payload.remote_path,
            username=payload.username,
            authMode=payload.auth_mode,
            mountStrategy=payload.mount_strategy,
            mountedPath=payload.mounted_path,
            knownHostMode=payload.known_host_mode,
            knownHostReference=payload.known_host_reference,
            domain=payload.domain,
            mountOptions=payload.mount_options,
            passwordSecretRef=self._password_secret_reference(
                settings,
                payload=payload,
                existing=existing,
            ),
            privateKeySecretRef=self._private_key_secret_reference(
                settings,
                payload=payload,
                existing=existing,
            ),
        )
        self._validate_resolved_transport(payload=payload, transport=transport)
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
            restoreReadiness=self._restore_readiness_for_payload(payload),
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

    def _password_secret_reference(
        self,
        settings: AppSettings,
        *,
        payload: BackupTargetUpsertPayload,
        existing: BackupTargetConfig | None,
    ) -> SecretReferenceSummary | None:
        if payload.target_type == BackupTargetType.SMB:
            if payload.mount_strategy != BackupTargetMountStrategy.SYSTEM_MOUNT:
                return None
            return self._resolve_secret_reference(
                settings,
                secret_kind="password",
                requested=payload.password_secret,
                current=existing.transport.password_secret_ref if existing else None,
            )
        if payload.target_type not in {BackupTargetType.SSH, BackupTargetType.RSYNC}:
            return None
        if payload.auth_mode != BackupTargetAuthMode.PASSWORD:
            return None
        return self._resolve_secret_reference(
            settings,
            secret_kind="password",
            requested=payload.password_secret,
            current=existing.transport.password_secret_ref if existing else None,
        )

    def _private_key_secret_reference(
        self,
        settings: AppSettings,
        *,
        payload: BackupTargetUpsertPayload,
        existing: BackupTargetConfig | None,
    ) -> SecretReferenceSummary | None:
        if payload.target_type not in {BackupTargetType.SSH, BackupTargetType.RSYNC}:
            return None
        if payload.auth_mode != BackupTargetAuthMode.PRIVATE_KEY:
            return None
        return self._resolve_secret_reference(
            settings,
            secret_kind="private_key",
            requested=payload.private_key_secret,
            current=existing.transport.private_key_secret_ref if existing else None,
        )

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
            if payload.mount_strategy == BackupTargetMountStrategy.PRE_MOUNTED_PATH:
                warnings.append(
                    "SMB pre-mounted targets rely on an already authenticated mount. "
                    "When the mounted path is usable, execution follows the same "
                    "path-like check/sync workflow as other mounted destinations."
                )
            else:
                warnings.append(
                    "SMB targets require authentication for system mount. "
                    "Execution still disabled in this phase."
                )
        if payload.target_type == BackupTargetType.LOCAL:
            warnings.append(
                "Local targets allow asset-aware check/sync, test copy, and "
                "explicit selective restore with quarantine-first overwrite protection."
            )
        if payload.target_type in {BackupTargetType.SSH, BackupTargetType.RSYNC}:
            warnings.append(
                "Remote targets currently provide files-only backup scope and do "
                "not imply restore readiness."
            )
            if payload.auth_mode == BackupTargetAuthMode.PASSWORD:
                warnings.append(
                    "Password-based SSH/rsync execution is not implemented in this phase."
                )
            if payload.known_host_mode == BackupTargetKnownHostMode.DISABLED:
                warnings.append(
                    "Known-host verification is explicitly disabled for this target."
                )
        if payload.retention_policy and payload.retention_policy.prune_automatically:
            warnings.append(
                "Automatic retention pruning is not implemented; old backups are "
                "never deleted automatically."
            )
        return warnings

    def _validate_resolved_transport(
        self,
        *,
        payload: BackupTargetUpsertPayload,
        transport: BackupTargetTransportSettings,
    ) -> None:
        if payload.target_type in {BackupTargetType.SSH, BackupTargetType.RSYNC}:
            if transport.auth_mode == BackupTargetAuthMode.PRIVATE_KEY:
                if transport.private_key_secret_ref is None:
                    raise ValueError(
                        "SSH and rsync targets using private_key auth require a private key secret reference."
                    )
            elif transport.auth_mode == BackupTargetAuthMode.PASSWORD:
                if transport.password_secret_ref is None:
                    raise ValueError(
                        "SSH and rsync targets using password auth require a password secret reference."
                    )
            elif transport.auth_mode != BackupTargetAuthMode.AGENT:
                raise ValueError("SSH and rsync targets require a supported auth mode.")
        if payload.target_type != BackupTargetType.SMB:
            return
        if transport.mount_strategy == BackupTargetMountStrategy.PRE_MOUNTED_PATH:
            if transport.mounted_path is None:
                raise ValueError("SMB pre-mounted targets require a mounted path.")
            return
        if transport.mount_strategy != BackupTargetMountStrategy.SYSTEM_MOUNT:
            raise ValueError("SMB targets require a supported mount strategy.")
        if not transport.username:
            raise ValueError("SMB system-mount targets require a username.")
        if transport.password_secret_ref is None:
            raise ValueError(
                "SMB system-mount targets require a password secret reference."
            )

    def _restore_readiness_for_payload(
        self,
        payload: BackupTargetUpsertPayload,
    ) -> BackupRestoreReadiness:
        if payload.target_type == BackupTargetType.LOCAL:
            return BackupRestoreReadiness.PARTIAL
        if (
            payload.target_type == BackupTargetType.SMB
            and payload.mount_strategy == BackupTargetMountStrategy.PRE_MOUNTED_PATH
        ):
            return BackupRestoreReadiness.PARTIAL
        return BackupRestoreReadiness.NOT_IMPLEMENTED
