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
    AGENT = "agent"
    PASSWORD = "password"
    PRIVATE_KEY = "private_key"


class BackupTargetMountStrategy(StrEnum):
    SYSTEM_MOUNT = "system_mount"
    PRE_MOUNTED_PATH = "pre_mounted_path"


class BackupTargetKnownHostMode(StrEnum):
    STRICT = "strict"
    ACCEPT_NEW = "accept_new"
    DISABLED = "disabled"


class BackupRestoreReadiness(StrEnum):
    NOT_IMPLEMENTED = "not_implemented"
    PARTIAL = "partial"


class VerificationLevel(StrEnum):
    NONE = "none"
    TRANSPORT_SUCCESS_ONLY = "transport_success_only"
    DESTINATION_EXISTS = "destination_exists"
    BASIC_MANIFEST_VERIFIED = "basic_manifest_verified"
    COPIED_FILES_SHA256 = "copied_files_sha256"


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
    known_host_mode: BackupTargetKnownHostMode | None = Field(
        default=None,
        alias="knownHostMode",
    )
    known_host_reference: str | None = Field(default=None, alias="knownHostReference")
    domain: str | None = None
    mount_options: str | None = Field(default=None, alias="mountOptions")
    password_secret_ref: SecretReferenceSummary | None = Field(
        default=None,
        alias="passwordSecretRef",
    )
    private_key_secret_ref: SecretReferenceSummary | None = Field(
        default=None,
        alias="privateKeySecretRef",
    )

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_host_key_fields(
        cls,
        data: object,
    ) -> object:
        if not isinstance(data, dict):
            return data
        migrated = dict(data)
        if "hostKeyVerification" in migrated and "knownHostMode" not in migrated:
            migrated["knownHostMode"] = cls._legacy_known_host_mode(
                migrated.get("hostKeyVerification")
            )
        if "hostKeyReference" in migrated and "knownHostReference" not in migrated:
            migrated["knownHostReference"] = migrated.get("hostKeyReference")
        return migrated

    @staticmethod
    def _legacy_known_host_mode(value: object) -> object:
        if value == "known_hosts":
            return BackupTargetKnownHostMode.STRICT
        if value == "insecure_accept_any":
            return BackupTargetKnownHostMode.DISABLED
        return value


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

    @model_validator(mode="after")
    def clear_empty_values(self) -> BackupTargetSecretInput:
        if self.label == "":
            self.label = None
        if self.material == "":
            self.material = None
        if self.secret_id == "":
            self.secret_id = None
        return self


class ParsedBackupConnectionString(BaseModel):
    username: str
    host: str
    port: int | None = None


def parse_backup_connection_string(connection_string: str) -> ParsedBackupConnectionString:
    candidate = connection_string.strip()
    username, separator, host_reference = candidate.partition("@")
    if separator == "" or not username or not host_reference:
        raise ValueError("Connection string must use the form username@host.")
    host, port = _parse_connection_host_reference(host_reference)
    return ParsedBackupConnectionString(username=username, host=host, port=port)


def _parse_connection_host_reference(host_reference: str) -> tuple[str, int | None]:
    if host_reference.startswith("["):
        closing_index = host_reference.find("]")
        if closing_index <= 1:
            raise ValueError("Connection string contains an invalid bracketed host.")
        host = host_reference[1:closing_index]
        remainder = host_reference[closing_index + 1 :]
        if remainder == "":
            return host, None
        if not remainder.startswith(":"):
            raise ValueError("Connection string must use the form username@host or username@host:port.")
        return host, _parse_connection_port(remainder[1:])

    colon_count = host_reference.count(":")
    if colon_count == 1:
        host, candidate_port = host_reference.rsplit(":", maxsplit=1)
        if candidate_port.isdigit():
            if not host:
                raise ValueError("Connection string host is missing.")
            return host, _parse_connection_port(candidate_port)
    if not host_reference:
        raise ValueError("Connection string host is missing.")
    return host_reference, None


def _parse_connection_port(candidate_port: str) -> int:
    if not candidate_port.isdigit():
        raise ValueError("Connection string port must be numeric.")
    port = int(candidate_port)
    if port < 1 or port > 65535:
        raise ValueError("Connection string port must be between 1 and 65535.")
    return port


class BackupTargetUpsertPayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    target_name: str = Field(alias="targetName")
    target_type: BackupTargetType = Field(alias="targetType")
    enabled: bool = True
    path: str | None = None
    connection_string: str | None = Field(default=None, alias="connectionString")
    host: str | None = None
    port: int | None = None
    share: str | None = None
    remote_path: str | None = Field(default=None, alias="remotePath")
    username: str | None = None
    auth_mode: BackupTargetAuthMode | None = Field(default=None, alias="authMode")
    mount_strategy: BackupTargetMountStrategy | None = Field(
        default=None,
        alias="mountStrategy",
    )
    mounted_path: str | None = Field(default=None, alias="mountedPath")
    known_host_mode: BackupTargetKnownHostMode | None = Field(
        default=None,
        alias="knownHostMode",
    )
    known_host_reference: str | None = Field(default=None, alias="knownHostReference")
    domain: str | None = None
    mount_options: str | None = Field(default=None, alias="mountOptions")
    password_secret: BackupTargetSecretInput | None = Field(
        default=None,
        alias="passwordSecret",
    )
    private_key_secret: BackupTargetSecretInput | None = Field(
        default=None,
        alias="privateKeySecret",
    )
    retention_policy: RetentionPolicy | None = Field(default=None, alias="retentionPolicy")

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_fields(
        cls,
        data: object,
    ) -> object:
        if not isinstance(data, dict):
            return data
        normalized = dict(data)
        for field_name in (
            "path",
            "connectionString",
            "host",
            "share",
            "remotePath",
            "username",
            "mountedPath",
            "knownHostReference",
            "domain",
            "mountOptions",
        ):
            value = normalized.get(field_name)
            if isinstance(value, str):
                stripped = value.strip()
                normalized[field_name] = stripped or None
        if "hostKeyVerification" in normalized and "knownHostMode" not in normalized:
            normalized["knownHostMode"] = BackupTargetTransportSettings._legacy_known_host_mode(
                normalized.get("hostKeyVerification")
            )
        if "hostKeyReference" in normalized and "knownHostReference" not in normalized:
            normalized["knownHostReference"] = normalized.get("hostKeyReference")
        return normalized

    @model_validator(mode="after")
    def apply_connection_string(self) -> BackupTargetUpsertPayload:
        if self.target_type not in {BackupTargetType.SSH, BackupTargetType.RSYNC}:
            return self
        if self.connection_string is None:
            return self
        parsed = parse_backup_connection_string(self.connection_string)
        if self.username and self.username != parsed.username:
            raise ValueError("Connection string username does not match the username field.")
        if self.host and self.host != parsed.host:
            raise ValueError("Connection string host does not match the host field.")
        if parsed.port is not None and self.port is not None and self.port != parsed.port:
            raise ValueError("Connection string port does not match the port field.")
        self.username = parsed.username
        self.host = parsed.host
        if parsed.port is not None:
            self.port = parsed.port
        return self

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
            if self.mount_strategy == BackupTargetMountStrategy.PRE_MOUNTED_PATH:
                if not self.mounted_path:
                    raise ValueError("SMB pre-mounted targets require a mounted path.")
            elif self.mount_strategy == BackupTargetMountStrategy.SYSTEM_MOUNT:
                if not self.username:
                    raise ValueError("SMB system-mount targets require a username.")
            else:
                raise ValueError("SMB targets require a supported mount strategy.")
        elif self.target_type in {BackupTargetType.SSH, BackupTargetType.RSYNC}:
            required = [
                self.host,
                self.remote_path,
                self.username,
                self.auth_mode,
                self.known_host_mode,
            ]
            if any(value in {None, ""} for value in required):
                raise ValueError(
                    "SSH and rsync targets require host, remote path, username, auth mode, "
                    "and explicit known host handling."
                )
        return self


class BackupTargetsDocument(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    version: str = "v1"
    items: list[BackupTargetConfig] = Field(default_factory=list)
