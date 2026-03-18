from __future__ import annotations

from pathlib import Path

from immich_doctor.backup.core.job_models import BackgroundJobRecord, BackgroundJobState
from immich_doctor.backup.core.paths import backup_manifest_root
from immich_doctor.core.config import AppSettings


def backup_job_root(settings: AppSettings, job_type: str) -> Path:
    return backup_manifest_root(settings) / "jobs" / job_type


def backup_job_path(settings: AppSettings, job_type: str, job_id: str) -> Path:
    return backup_job_root(settings, job_type) / f"{job_id}.json"


class BackgroundJobStore:
    def persist_job(
        self,
        settings: AppSettings,
        record: BackgroundJobRecord,
    ) -> BackgroundJobRecord:
        path = backup_job_path(settings, record.job_type, record.job_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(record.model_dump_json(by_alias=True, indent=2), encoding="utf-8")
        return record

    def load_job(
        self,
        settings: AppSettings,
        *,
        job_type: str,
        job_id: str,
    ) -> BackgroundJobRecord:
        path = backup_job_path(settings, job_type, job_id)
        return BackgroundJobRecord.model_validate_json(path.read_text(encoding="utf-8"))

    def list_jobs(self, settings: AppSettings, *, job_type: str) -> list[BackgroundJobRecord]:
        root = backup_job_root(settings, job_type)
        if not root.exists():
            return []

        jobs = [
            BackgroundJobRecord.model_validate_json(path.read_text(encoding="utf-8"))
            for path in sorted(root.glob("*.json"))
        ]
        jobs.sort(key=lambda item: item.updated_at, reverse=True)
        return jobs

    def find_latest_job(
        self,
        settings: AppSettings,
        *,
        job_type: str,
        states: set[BackgroundJobState] | None = None,
    ) -> BackgroundJobRecord | None:
        jobs = self.list_jobs(settings, job_type=job_type)
        if states is None:
            return jobs[0] if jobs else None

        for job in jobs:
            if job.state in states:
                return job
        return None
