from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator


class BackupTargetType(StrEnum):
    LOCAL = "local"
    SMB = "smb"
    SSH = "ssh"
    RSYNC = "rsync"


class BackupTargetVerificationStatus(StrEnum):
    UNKNOWN = "unknown"
    READY = "ready"
    WARNING = "warning"
    FAILED = "failed"
    RUNNING = "running"
    UNSUPPORTED = "unsupported"


class BackupTargetAuthMode(StrEnum):
    PASSWORD = "password"
    PRIVATE_KEY = "private_key"


class BackupTargetMountStrategy(StrEnum):
    SYSTEM_MOUNT = "system_mount"
    PRE_MOUNTED_PATH = "pre_mounted_path"


class HostKeyVerificationStrategy(StrEnum):
    KNOWN_HOSTS = "known_hosts"
    PINNED_FINGERPRINT = "pinned_fingerprint"
    INSECURE_ACCEPT_ANY = "insecure_accept_any"


class BackupRestoreReadiness(StrEnum):
    NOT_IMPLEMENTED = "not_implemented"
    PARTIAL = "partial"


class VerificationLevel(StrEnum):
    NONE = "none"
    TRANSPORT_SUCCESS_ONLY = "transport_success_only"
    DESTINATION_EXISTS = "destination_exists"
    BASIC_MANIFEST_VERIFIED = "basic_manifest_verified"


class RetentionPolicy(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    mode: str = "keep_all"
    max_versions: int | None = Field(default=None, alias="maxVersions")
    prune_automatically: bool = Field(default=False, alias="pruneAutomatically")


class SecretReferenceSummary(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    secret_id: str = Field(alias="secretId")
    kind: str
    label: str
    masked_value: str = Field(alias="maskedValue")
    created_at: str = Field(alias="createdAt")


class BackupTargetLastTestResult(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    checked_at: str = Field(alias="checkedAt")
    status: BackupTargetVerificationStatus
    summary: str
    warnings: list[str] = Field(default_factory=list)
    details: dict[str, object] = Field(default_factory=dict)


class BackupTargetLastBackupMetadata(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    backup_id: str = Field(alias="backupId")
    completed_at: str = Field(alias="completedAt")
    source_scope: str = Field(alias="sourceScope")
    bytes_transferred: int | None = Field(default=None, alias="bytesTransferred")
    verification_level: VerificationLevel = Field(alias="verificationLevel")
    snapshot_id: str | None = Field(default=None, alias="snapshotId")


class BackupTargetTransportSettings(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    path: str | None = None
    host: str | None = None
    port: int | None = 22
    share: str | None = None
    remote_path: str | None = Field(default=None, alias="remotePath")
    username: str | None = None
    auth_mode: BackupTargetAuthMode | None = Field(default=None, alias="authMode")
    mount_strategy: BackupTargetMountStrategy | None = Field(
        default=None,
        alias="mountStrategy",
    )
    mounted_path: str | None = Field(default=None, alias="mountedPath")
    host_key_verification: HostKeyVerificationStrategy | None = Field(
        default=None,
        alias="hostKeyVerification",
    )
    host_key_reference: str | None = Field(default=None, alias="hostKeyReference")
    password_secret_ref: SecretReferenceSummary | None = Field(
        default=None,
        alias="passwordSecretRef",
    )
    private_key_secret_ref: SecretReferenceSummary | None = Field(
        default=None,
        alias="privateKeySecretRef",
    )


class BackupTargetConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    target_id: str = Field(alias="targetId")
    target_name: str = Field(alias="targetName")
    target_type: BackupTargetType = Field(alias="targetType")
    enabled: bool = True
    transport: BackupTargetTransportSettings
    verification_status: BackupTargetVerificationStatus = Field(
        default=BackupTargetVerificationStatus.UNKNOWN,
        alias="verificationStatus",
    )
    last_test_result: BackupTargetLastTestResult | None = Field(
        default=None,
        alias="lastTestResult",
    )
    last_successful_backup: BackupTargetLastBackupMetadata | None = Field(
        default=None,
        alias="lastSuccessfulBackup",
    )
    retention_policy: RetentionPolicy = Field(
        default_factory=RetentionPolicy,
        alias="retentionPolicy",
    )
    restore_readiness: BackupRestoreReadiness = Field(
        default=BackupRestoreReadiness.NOT_IMPLEMENTED,
        alias="restoreReadiness",
    )
    source_scope: str = Field(default="files_only", alias="sourceScope")
    scheduling_compatible: bool = Field(default=True, alias="schedulingCompatible")
    warnings: list[str] = Field(default_factory=list)
    created_at: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
        alias="createdAt",
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
        alias="updatedAt",
    )


class BackupTargetSecretInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    label: str | None = None
    material: str | None = None
    secret_id: str | None = Field(default=None, alias="secretId")


class BackupTargetUpsertPayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    target_name: str = Field(alias="targetName")
    target_type: BackupTargetType = Field(alias="targetType")
    enabled: bool = True
    path: str | None = None
    host: str | None = None
    port: int | None = 22
    share: str | None = None
    remote_path: str | None = Field(default=None, alias="remotePath")
    username: str | None = None
    auth_mode: BackupTargetAuthMode | None = Field(default=None, alias="authMode")
    mount_strategy: BackupTargetMountStrategy | None = Field(
        default=None,
        alias="mountStrategy",
    )
    mounted_path: str | None = Field(default=None, alias="mountedPath")
    host_key_verification: HostKeyVerificationStrategy | None = Field(
        default=None,
        alias="hostKeyVerification",
    )
    host_key_reference: str | None = Field(default=None, alias="hostKeyReference")
    password_secret: BackupTargetSecretInput | None = Field(
        default=None,
        alias="passwordSecret",
    )
    private_key_secret: BackupTargetSecretInput | None = Field(
        default=None,
        alias="privateKeySecret",
    )
    retention_policy: RetentionPolicy | None = Field(default=None, alias="retentionPolicy")

    @model_validator(mode="after")
    def validate_transport_requirements(self) -> BackupTargetUpsertPayload:
        if self.target_type == BackupTargetType.LOCAL:
            if not self.path:
                raise ValueError("Local targets require an absolute destination path.")
            if not Path(self.path).expanduser().is_absolute():
                raise ValueError("Local targets require an absolute destination path.")
        elif self.target_type == BackupTargetType.SMB:
            required = [self.host, self.share, self.remote_path, self.mount_strategy]
            if any(value in {None, ""} for value in required):
                raise ValueError(
                    "SMB targets require host, share, remote path, and explicit mount strategy."
                )
        elif self.target_type in {BackupTargetType.SSH, BackupTargetType.RSYNC}:
            required = [
                self.host,
                self.remote_path,
                self.username,
                self.auth_mode,
                self.host_key_verification,
            ]
            if any(value in {None, ""} for value in required):
                raise ValueError(
                    "SSH and rsync targets require host, remote path, username, auth mode, "
                    "and explicit host key verification."
                )
        return self


class BackupTargetsDocument(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    version: str = "v1"
    items: list[BackupTargetConfig] = Field(default_factory=list)
