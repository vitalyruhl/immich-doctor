from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from immich_doctor.core.config import AppSettings
from immich_doctor.repair.models import PlanToken, QuarantineItem, RepairJournalEntry, RepairRun
from immich_doctor.repair.paths import (
    quarantine_index_file,
    repair_journal_file,
    repair_manifests_root,
    repair_plan_token_file,
    repair_quarantine_items_file,
    repair_run_directory,
    repair_run_file,
)


class RepairJournalStore:
    def create_run(
        self,
        settings: AppSettings,
        *,
        repair_run: RepairRun,
        plan_token: PlanToken,
    ) -> None:
        repair_manifests_root(settings).mkdir(parents=True, exist_ok=True)
        repair_run_directory(settings, repair_run.repair_run_id).mkdir(
            parents=True,
            exist_ok=True,
        )
        settings.quarantine_path.mkdir(parents=True, exist_ok=True)

        self._write_json(repair_run_file(settings, repair_run.repair_run_id), repair_run.to_dict())
        self._write_json(
            repair_plan_token_file(settings, repair_run.repair_run_id),
            plan_token.to_dict(),
        )
        repair_journal_file(settings, repair_run.repair_run_id).touch(exist_ok=True)
        repair_quarantine_items_file(settings, repair_run.repair_run_id).touch(exist_ok=True)
        quarantine_index_file(settings).touch(exist_ok=True)

    def update_run(self, settings: AppSettings, repair_run: RepairRun) -> None:
        self._write_json(repair_run_file(settings, repair_run.repair_run_id), repair_run.to_dict())

    def append_journal_entry(
        self,
        settings: AppSettings,
        entry: RepairJournalEntry,
    ) -> None:
        self._append_json_line(repair_journal_file(settings, entry.repair_run_id), entry.to_dict())

    def append_quarantine_item(self, settings: AppSettings, item: QuarantineItem) -> None:
        payload = item.to_dict()
        self._append_json_line(
            repair_quarantine_items_file(settings, item.repair_run_id),
            payload,
        )
        self._append_json_line(quarantine_index_file(settings), payload)

    def load_run(self, settings: AppSettings, repair_run_id: str) -> RepairRun:
        return RepairRun.from_dict(self._read_json(repair_run_file(settings, repair_run_id)))

    def load_plan_token(self, settings: AppSettings, repair_run_id: str) -> PlanToken:
        return PlanToken.from_dict(self._read_json(repair_plan_token_file(settings, repair_run_id)))

    def load_journal_entries(
        self,
        settings: AppSettings,
        repair_run_id: str,
    ) -> list[RepairJournalEntry]:
        return [
            RepairJournalEntry.from_dict(payload)
            for payload in self._read_json_lines(repair_journal_file(settings, repair_run_id))
        ]

    def load_quarantine_items(
        self,
        settings: AppSettings,
        repair_run_id: str,
    ) -> list[QuarantineItem]:
        return self._collapse_quarantine_items(
            [
                QuarantineItem.from_dict(payload)
                for payload in self._read_json_lines(
                    repair_quarantine_items_file(settings, repair_run_id)
                )
            ]
        )

    def load_quarantine_index(self, settings: AppSettings) -> list[QuarantineItem]:
        return self._collapse_quarantine_items(
            [
                QuarantineItem.from_dict(payload)
                for payload in self._read_json_lines(quarantine_index_file(settings))
            ]
        )

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def _read_json(self, path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    def _append_json_line(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")

    def _read_json_lines(self, path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        rows: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                rows.append(json.loads(line))
        return rows

    def _collapse_quarantine_items(self, items: list[QuarantineItem]) -> list[QuarantineItem]:
        latest_by_id: dict[str, QuarantineItem] = {}
        for item in items:
            latest_by_id[item.quarantine_item_id] = item
        return list(latest_by_id.values())
