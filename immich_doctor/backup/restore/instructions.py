from __future__ import annotations

from dataclasses import dataclass

from immich_doctor.backup.core.models import BackupSnapshot
from immich_doctor.backup.restore.models import RestoreInstruction
from immich_doctor.core.config import AppSettings


@dataclass(slots=True, frozen=True)
class RestoreInstructionProfile:
    name: str


def detect_restore_instruction_profile(settings: AppSettings) -> RestoreInstructionProfile:
    environment = settings.environment.lower()
    if "unraid" in environment:
        return RestoreInstructionProfile(name="docker-unraid")
    if "docker" in environment:
        return RestoreInstructionProfile(name="docker")
    return RestoreInstructionProfile(name="generic")


def build_restore_instructions(
    *,
    settings: AppSettings,
    snapshot: BackupSnapshot,
    profile: RestoreInstructionProfile,
) -> list[RestoreInstruction]:
    if profile.name in {"docker", "docker-unraid"}:
        library_root = (
            settings.immich_library_root.as_posix()
            if settings.immich_library_root
            else "/mnt/immich/storage/"
        )
        return [
            RestoreInstruction(
                step_id="stop-services",
                phase="prepare",
                description="Stop Immich services before overwriting live state.",
                command=(
                    "docker compose stop immich-server immich-microservices "
                    "immich-machine-learning immich_postgres redis"
                ),
            ),
            RestoreInstruction(
                step_id="stop-doctor",
                phase="prepare",
                description="Stop immich-doctor during restore execution.",
                command="docker compose stop immich-doctor",
            ),
            RestoreInstruction(
                step_id="wipe-live-state",
                phase="destructive",
                description=(
                    "Wipe the current broken state only after verifying the selected "
                    "snapshot and matching DB/storage plan."
                ),
            ),
            RestoreInstruction(
                step_id="restore-db",
                phase="restore",
                description=(
                    "Restore the PostgreSQL artifact if the selected snapshot includes one."
                ),
            ),
            RestoreInstruction(
                step_id="restore-files",
                phase="restore",
                description="Restore file artifacts from the selected snapshot target path.",
                command=(
                    f"rsync -a --info=progress2 /restore/source/{snapshot.snapshot_id}/ "
                    f"{library_root}"
                ),
            ),
            RestoreInstruction(
                step_id="restart-services",
                phase="finalize",
                description="Restart Immich services after restore completion.",
                command=(
                    "docker compose up -d immich-server immich-microservices "
                    "immich-machine-learning immich_postgres redis immich-doctor"
                ),
            ),
        ]

    return [
        RestoreInstruction(
            step_id="stop-services",
            phase="prepare",
            description="Stop Immich services before overwriting live state.",
        ),
        RestoreInstruction(
            step_id="wipe-live-state",
            phase="destructive",
            description="Wipe the current broken state after verifying snapshot integrity.",
        ),
        RestoreInstruction(
            step_id="restore-db",
            phase="restore",
            description="Restore the database artifact if present in the selected snapshot.",
        ),
        RestoreInstruction(
            step_id="restore-files",
            phase="restore",
            description=(
                "Restore file artifacts from the selected snapshot to the live storage path."
            ),
        ),
        RestoreInstruction(
            step_id="restart-services",
            phase="finalize",
            description="Restart Immich services after restore completion.",
        ),
    ]
