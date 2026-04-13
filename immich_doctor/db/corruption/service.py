from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from immich_doctor.adapters.postgres import PostgresAdapter
from immich_doctor.core.config import AppSettings
from immich_doctor.core.models import CheckResult, CheckStatus, ValidationReport, ValidationSection
from immich_doctor.repair import (
    RepairJournalEntry,
    RepairJournalEntryStatus,
    RepairJournalStore,
    RepairRun,
    RepairRunStatus,
    UndoType,
    build_live_state_fingerprint,
    create_plan_token,
    fingerprint_payload,
    validate_plan_token,
)
from immich_doctor.repair.paths import repair_run_directory


@dataclass(slots=True)
class DbCorruptionScanService:
    postgres: PostgresAdapter = field(default_factory=PostgresAdapter)

    def run(self, settings: AppSettings) -> ValidationReport:
        dsn = settings.postgres_dsn_value()
        if not dsn:
            return ValidationReport(
                domain="db.corruption",
                action="scan",
                summary="Database corruption scan failed because database access is not configured.",
                checks=[
                    CheckResult(
                        name="postgres_connection",
                        status=CheckStatus.FAIL,
                        message="Database DSN is not configured.",
                    )
                ],
                metadata={"environment": settings.environment},
            )

        timeout = settings.postgres_connect_timeout_seconds
        connection_check = self.postgres.validate_connection(dsn, timeout)
        if connection_check.status == CheckStatus.FAIL:
            return ValidationReport(
                domain="db.corruption",
                action="scan",
                summary="Database corruption scan failed because PostgreSQL could not be reached.",
                checks=[connection_check],
                metadata={"environment": settings.environment},
            )

        snapshot = self._collect_snapshot(dsn, timeout)
        checks = [
            connection_check,
            self._toast_check(snapshot["toast"]),
            CheckResult(
                name="invalid_system_indexes",
                status=CheckStatus.FAIL if snapshot["invalid_system_indexes"] else CheckStatus.PASS,
                message=(
                    f"Detected {len(snapshot['invalid_system_indexes'])} invalid system indexes."
                    if snapshot["invalid_system_indexes"]
                    else "No invalid system indexes were detected."
                ),
            ),
            CheckResult(
                name="invalid_user_indexes",
                status=CheckStatus.FAIL if snapshot["invalid_user_indexes"] else CheckStatus.PASS,
                message=(
                    f"Detected {len(snapshot['invalid_user_indexes'])} invalid user indexes."
                    if snapshot["invalid_user_indexes"]
                    else "No invalid user indexes were detected."
                ),
            ),
            CheckResult(
                name="duplicate_asset_checksum_groups",
                status=CheckStatus.FAIL if snapshot["duplicate_asset_groups"] else CheckStatus.PASS,
                message=(
                    f"Detected {len(snapshot['duplicate_asset_groups'])} duplicate asset checksum groups."
                    if snapshot["duplicate_asset_groups"]
                    else "No duplicate asset checksum groups were detected."
                ),
            ),
        ]
        return ValidationReport(
            domain="db.corruption",
            action="scan",
            summary=self._scan_summary(snapshot),
            checks=checks,
            sections=self._scan_sections(snapshot),
            metadata={
                "environment": settings.environment,
                "database_name": snapshot["database_name"],
                "duplicate_owner_count": len(
                    {row["owner_id"] for row in snapshot["duplicate_asset_groups"]}
                ),
                "duplicate_group_count": len(snapshot["duplicate_asset_groups"]),
                "duplicate_excess_rows": sum(
                    int(row["excess_row_count"]) for row in snapshot["duplicate_asset_groups"]
                ),
            },
        )

    def _collect_snapshot(self, dsn: str, timeout: int) -> dict[str, Any]:
        database_name = self.postgres.fetch_current_database_name(dsn, timeout)
        toast = self.postgres.read_pg_statistic_toast_health(dsn, timeout)
        invalid_system_indexes = self.postgres.list_invalid_system_indexes(dsn, timeout)
        invalid_user_indexes = self.postgres.list_invalid_user_indexes(dsn, timeout)
        duplicate_groups = self.postgres.list_duplicate_asset_checksum_groups(dsn, timeout)
        duplicate_rows = self.postgres.list_duplicate_asset_checksum_rows(dsn, timeout)
        grouped_rows: dict[tuple[str, str], list[dict[str, object]]] = {}
        for row in duplicate_rows:
            key = (str(row["owner_id"]), str(row["checksum_hex"]))
            grouped_rows.setdefault(key, []).append(dict(row))
        enriched_groups = []
        for row in duplicate_groups:
            key = (str(row["owner_id"]), str(row["checksum_hex"]))
            enriched_groups.append(
                {
                    **dict(row),
                    "candidate_rows": grouped_rows.get(key, []),
                    "proposed_keep_id": None,
                    "user_selected_delete_ids": [],
                }
            )
        fk_constraints = self.postgres.list_asset_referencing_foreign_keys(dsn, timeout)
        return {
            "database_name": database_name,
            "toast": toast,
            "invalid_system_indexes": invalid_system_indexes,
            "invalid_user_indexes": invalid_user_indexes,
            "duplicate_asset_groups": enriched_groups,
            "fk_constraints_on_asset": fk_constraints,
        }

    def _toast_check(self, toast: dict[str, object]) -> CheckResult:
        if bool(toast["detected"]):
            return CheckResult(
                name="pg_statistic_toast_health",
                status=CheckStatus.FAIL,
                message="A TOAST/system-catalog read failure was detected while reading pg_statistic.",
                details={"exception_text": toast.get("exception_text")},
            )
        return CheckResult(
            name="pg_statistic_toast_health",
            status=CheckStatus.PASS,
            message="No TOAST/system-catalog read failure was detected while reading pg_statistic.",
        )

    def _scan_summary(self, snapshot: dict[str, Any]) -> str:
        parts: list[str] = []
        if snapshot["toast"]["detected"]:
            parts.append("TOAST corruption signal detected")
        if snapshot["invalid_system_indexes"]:
            parts.append(f"{len(snapshot['invalid_system_indexes'])} invalid system indexes")
        if snapshot["invalid_user_indexes"]:
            parts.append(f"{len(snapshot['invalid_user_indexes'])} invalid user indexes")
        if snapshot["duplicate_asset_groups"]:
            parts.append(f"{len(snapshot['duplicate_asset_groups'])} duplicate asset groups")
        if not parts:
            return "Database corruption scan found no confirmed pg_statistic/index/duplicate-checksum issues."
        return "Database corruption scan detected " + ", ".join(parts) + "."

    def _scan_sections(self, snapshot: dict[str, Any]) -> list[ValidationSection]:
        toast_row = {
            "detected": bool(snapshot["toast"]["detected"]),
            "exception_text": snapshot["toast"].get("exception_text"),
            "read_ok": bool(snapshot["toast"].get("read_ok", False)),
        }
        return [
            ValidationSection(
                name="TOAST_CORRUPTION",
                status=CheckStatus.FAIL if toast_row["detected"] else CheckStatus.PASS,
                rows=[toast_row],
            ),
            ValidationSection(
                name="INVALID_SYSTEM_INDEXES",
                status=CheckStatus.FAIL if snapshot["invalid_system_indexes"] else CheckStatus.PASS,
                rows=snapshot["invalid_system_indexes"],
            ),
            ValidationSection(
                name="INVALID_USER_INDEXES",
                status=CheckStatus.FAIL if snapshot["invalid_user_indexes"] else CheckStatus.PASS,
                rows=snapshot["invalid_user_indexes"],
            ),
            ValidationSection(
                name="DUPLICATE_ASSET_GROUPS",
                status=CheckStatus.FAIL if snapshot["duplicate_asset_groups"] else CheckStatus.PASS,
                rows=snapshot["duplicate_asset_groups"],
            ),
            ValidationSection(
                name="ASSET_FK_CONSTRAINTS",
                status=CheckStatus.PASS if snapshot["fk_constraints_on_asset"] else CheckStatus.SKIP,
                rows=snapshot["fk_constraints_on_asset"],
            ),
        ]


@dataclass(slots=True)
class DbCorruptionRepairService:
    postgres: PostgresAdapter = field(default_factory=PostgresAdapter)
    repair_store: RepairJournalStore = field(default_factory=RepairJournalStore)
    scan_service: DbCorruptionScanService = field(default_factory=DbCorruptionScanService)

    def preview(
        self,
        settings: AppSettings,
        *,
        selected_delete_ids: tuple[str, ...],
        backup_confirmed: bool,
        override_backup_requirement: bool,
        maintenance_mode_confirmed: bool,
        system_index_duplicate_error_text: str | None,
        high_risk_clear_pg_statistic_approval: bool,
        force_reindex_database: bool,
    ) -> ValidationReport:
        scan_report = self.scan_service.run(settings)
        if scan_report.overall_status == CheckStatus.FAIL and not scan_report.sections:
            return ValidationReport(
                domain="db.corruption",
                action="repair.preview",
                summary="Database corruption repair preview failed because scan prerequisites were not met.",
                checks=list(scan_report.checks),
                metadata={"environment": settings.environment, "dry_run": True},
            )

        dsn = settings.postgres_dsn_value()
        assert dsn is not None
        timeout = settings.postgres_connect_timeout_seconds
        snapshot = self.scan_service._collect_snapshot(dsn, timeout)
        preconditions = self._preconditions(
            dsn,
            timeout,
            backup_confirmed=backup_confirmed,
            override_backup_requirement=override_backup_requirement,
            maintenance_mode_confirmed=maintenance_mode_confirmed,
        )
        selection = self._selection_state(snapshot["duplicate_asset_groups"], selected_delete_ids)
        plan_rows = self._plan_rows(
            snapshot,
            selection,
            system_index_duplicate_error_text=system_index_duplicate_error_text,
            high_risk_clear_pg_statistic_approval=high_risk_clear_pg_statistic_approval,
            force_reindex_database=force_reindex_database,
        )
        scope = {
            "domain": "db.corruption",
            "action": "repair.apply",
            "selected_delete_ids": list(selected_delete_ids),
            "backup_confirmed": backup_confirmed,
            "override_backup_requirement": override_backup_requirement,
            "maintenance_mode_confirmed": maintenance_mode_confirmed,
            "system_index_duplicate_error_text": system_index_duplicate_error_text or "",
            "high_risk_clear_pg_statistic_approval": high_risk_clear_pg_statistic_approval,
            "force_reindex_database": force_reindex_database,
        }
        db_fingerprint = self._db_fingerprint(snapshot)
        file_fingerprint = self._file_fingerprint_from_scope(scope)
        plan_token = create_plan_token(
            scope=scope,
            db_fingerprint=db_fingerprint,
            file_fingerprint=file_fingerprint,
        )
        repair_run = RepairRun.new(
            repair_run_id=uuid4().hex,
            scope=scope,
            status=RepairRunStatus.PLANNED,
            live_state_fingerprint=build_live_state_fingerprint(
                db_fingerprint=db_fingerprint,
                file_fingerprint=file_fingerprint,
            ),
            plan_token_id=plan_token.token_id,
        )
        self.repair_store.create_run(settings, repair_run=repair_run, plan_token=plan_token)
        checks = list(scan_report.checks)
        checks.extend(preconditions["checks"])
        checks.append(
            CheckResult(
                name="repair_plan_foundation",
                status=CheckStatus.PASS,
                message="Preview persisted a repair run and plan token for later apply.",
                details={
                    "repair_run_id": repair_run.repair_run_id,
                    "repair_run_path": str(repair_run_directory(settings, repair_run.repair_run_id)),
                    "plan_token_id": plan_token.token_id,
                },
            )
        )
        return ValidationReport(
            domain="db.corruption",
            action="repair.preview",
            summary=self._preview_summary(plan_rows, preconditions["apply_allowed"]),
            checks=checks,
            sections=[
                ValidationSection(
                    name="PRECONDITIONS",
                    status=preconditions["status"],
                    rows=preconditions["rows"],
                ),
                ValidationSection(
                    name="PLAN_STEPS",
                    status=CheckStatus.WARN if plan_rows else CheckStatus.SKIP,
                    rows=plan_rows,
                ),
                ValidationSection(
                    name="DUPLICATE_ASSET_GROUPS",
                    status=CheckStatus.FAIL if snapshot["duplicate_asset_groups"] else CheckStatus.PASS,
                    rows=selection["groups"],
                ),
                ValidationSection(
                    name="ASSET_FK_CONSTRAINTS",
                    status=CheckStatus.PASS if snapshot["fk_constraints_on_asset"] else CheckStatus.SKIP,
                    rows=snapshot["fk_constraints_on_asset"],
                ),
            ],
            metadata={
                "environment": settings.environment,
                "dry_run": True,
                "repair_run_id": repair_run.repair_run_id,
                "plan_token_id": plan_token.token_id,
                "apply_allowed": preconditions["apply_allowed"],
                "database_name": snapshot["database_name"],
            },
            recommendations=[
                "Review the FK graph and duplicate candidate rows before approving any asset deletions.",
                "Use the generated repair_run_id with apply only after the preconditions are satisfied.",
            ],
        )

    def apply(self, settings: AppSettings, *, repair_run_id: str) -> ValidationReport:
        run = self.repair_store.load_run(settings, repair_run_id)
        token = self.repair_store.load_plan_token(settings, repair_run_id)
        dsn = settings.postgres_dsn_value()
        if not dsn:
            return ValidationReport(
                domain="db.corruption",
                action="repair.apply",
                summary="Database corruption apply failed because database access is not configured.",
                checks=[
                    CheckResult(
                        name="postgres_connection",
                        status=CheckStatus.FAIL,
                        message="Database DSN is not configured.",
                    )
                ],
                metadata={"environment": settings.environment, "repair_run_id": repair_run_id},
            )

        timeout = settings.postgres_connect_timeout_seconds
        connection_check = self.postgres.validate_connection(dsn, timeout)
        if connection_check.status == CheckStatus.FAIL:
            return ValidationReport(
                domain="db.corruption",
                action="repair.apply",
                summary="Database corruption apply failed because PostgreSQL could not be reached.",
                checks=[connection_check],
                metadata={"environment": settings.environment, "repair_run_id": repair_run_id},
            )

        snapshot_before = self.scan_service._collect_snapshot(dsn, timeout)
        guard = validate_plan_token(
            token,
            scope=dict(run.scope),
            db_fingerprint=self._db_fingerprint(snapshot_before),
            file_fingerprint=self._file_fingerprint_from_scope(run.scope),
        )
        guard_check = CheckResult(
            name="repair_apply_guard",
            status=CheckStatus.PASS if guard.valid else CheckStatus.FAIL,
            message=guard.reason,
            details={
                "repair_run_id": repair_run_id,
                "token_id": guard.token_id,
                "expected_db_fingerprint": guard.expected_db_fingerprint,
                "actual_db_fingerprint": guard.actual_db_fingerprint,
            },
        )
        preconditions = self._preconditions(
            dsn,
            timeout,
            backup_confirmed=bool(run.scope.get("backup_confirmed")),
            override_backup_requirement=bool(run.scope.get("override_backup_requirement")),
            maintenance_mode_confirmed=bool(run.scope.get("maintenance_mode_confirmed")),
        )
        if not guard.valid or not preconditions["apply_allowed"]:
            run.finish(RepairRunStatus.FAILED)
            self.repair_store.update_run(settings, run)
            return ValidationReport(
                domain="db.corruption",
                action="repair.apply",
                summary="Database corruption apply stopped before mutation because guards or preconditions failed.",
                checks=[connection_check, guard_check, *preconditions["checks"]],
                sections=[
                    ValidationSection(
                        name="PRECONDITIONS",
                        status=preconditions["status"],
                        rows=preconditions["rows"],
                    )
                ],
                metadata={
                    "environment": settings.environment,
                    "repair_run_id": repair_run_id,
                    "dry_run": False,
                },
            )

        selection = self._selection_state(
            snapshot_before["duplicate_asset_groups"],
            tuple(str(item) for item in run.scope.get("selected_delete_ids", [])),
        )
        plan_rows = self._plan_rows(
            snapshot_before,
            selection,
            system_index_duplicate_error_text=str(run.scope.get("system_index_duplicate_error_text") or ""),
            high_risk_clear_pg_statistic_approval=bool(
                run.scope.get("high_risk_clear_pg_statistic_approval")
            ),
            force_reindex_database=bool(run.scope.get("force_reindex_database")),
        )
        before_cascade = self._cascade_counts(
            dsn,
            timeout,
            snapshot_before["fk_constraints_on_asset"],
            selection["selected_delete_ids"],
        )
        return self._apply_plan(
            settings,
            run=run,
            connection_check=connection_check,
            guard_check=guard_check,
            preconditions=preconditions,
            dsn=dsn,
            timeout=timeout,
            snapshot_before=snapshot_before,
            plan_rows=plan_rows,
            selection=selection,
            before_cascade=before_cascade,
        )

    def _plan_rows(
        self,
        snapshot: dict[str, Any],
        selection: dict[str, Any],
        *,
        system_index_duplicate_error_text: str | None,
        high_risk_clear_pg_statistic_approval: bool,
        force_reindex_database: bool,
    ) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        step = 1
        system_issue = bool(snapshot["toast"]["detected"] or snapshot["invalid_system_indexes"])
        clear_available = bool(snapshot["toast"]["detected"] and (system_index_duplicate_error_text or "").strip())
        if system_issue:
            if clear_available:
                rows.append(
                    self._plan_row(
                        step,
                        "clear_pg_statistic",
                        "high-risk",
                        "Exceptional path to clear corrupted pg_statistic rows before rebuilding catalog indexes.",
                        "DELETE FROM pg_catalog.pg_statistic;",
                        execution_state="execute" if high_risk_clear_pg_statistic_approval else "blocked",
                        requires_approval=True,
                        message=(
                            "High-risk approval confirmed."
                            if high_risk_clear_pg_statistic_approval
                            else "Separate explicit high-risk approval is still required."
                        ),
                    )
                )
                step += 1
            rows.append(
                self._plan_row(
                    step,
                    "reindex_system",
                    "catalog",
                    "Rebuild all system catalog indexes for the current database.",
                    f"REINDEX SYSTEM {snapshot['database_name']};",
                )
            )
            step += 1
            rows.append(
                self._plan_row(
                    step,
                    "analyze_database",
                    "catalog",
                    "Rebuild planner statistics after the system-catalog repair path.",
                    "ANALYZE;",
                )
            )
            step += 1

        for index_row in snapshot["invalid_user_indexes"]:
            rows.append(
                self._plan_row(
                    step,
                    f"reindex_invalid_user_index:{index_row['schema_name']}.{index_row['index_name']}",
                    "user-index",
                    f"Rebuild invalid user index `{index_row['index_name']}`.",
                    f"REINDEX INDEX {index_row['schema_name']}.{index_row['index_name']};",
                )
            )
            step += 1

        if snapshot["duplicate_asset_groups"]:
            rows.append(
                self._plan_row(
                    step,
                    "present_duplicate_asset_groups",
                    "review",
                    "Present duplicate asset groups and FK cascade impact before any deletion is offered.",
                    None,
                    execution_state="review",
                    message=(
                        "Operator-selected delete IDs are attached."
                        if selection["selected_delete_ids"]
                        else "No delete IDs selected yet; deletion SQL is intentionally absent."
                    ),
                )
            )
            step += 1
            if selection["delete_step_allowed"]:
                rows.append(
                    self._plan_row(
                        step,
                        "delete_duplicate_assets",
                        "asset",
                        "Delete only the operator-selected duplicate asset rows.",
                        self._delete_sql_preview(selection["selected_delete_ids"]),
                    )
                )
                step += 1

        if force_reindex_database or snapshot["invalid_user_indexes"]:
            rows.append(
                self._plan_row(
                    step,
                    "reindex_database",
                    "database",
                    "Rebuild database indexes after invalid-user-index repair or explicit operator request.",
                    f"REINDEX DATABASE {snapshot['database_name']};",
                )
            )
            step += 1

        rows.append(
            self._plan_row(
                step,
                "verify",
                "verify",
                "Re-run corruption detection and compare before/after state.",
                None,
                execution_state="review",
                message="Always runs after any mutation.",
            )
        )
        return rows

    def _preconditions(
        self,
        dsn: str,
        timeout: int,
        *,
        backup_confirmed: bool,
        override_backup_requirement: bool,
        maintenance_mode_confirmed: bool,
    ) -> dict[str, object]:
        capabilities = self.postgres.current_role_capabilities(dsn, timeout)
        active_sessions = self.postgres.count_active_non_idle_sessions(dsn, timeout)
        rows = [
            {
                "name": "superuser_privileges",
                "status": "pass" if capabilities["is_superuser"] else "fail",
                "message": (
                    "Current PostgreSQL role is superuser."
                    if capabilities["is_superuser"]
                    else "Current PostgreSQL role is not superuser."
                ),
                "current_user": capabilities["current_user"],
            },
            {
                "name": "backup_confirmation",
                "status": "pass" if (backup_confirmed or override_backup_requirement) else "fail",
                "message": (
                    "Backup requirement satisfied."
                    if (backup_confirmed or override_backup_requirement)
                    else "A recent database backup must be confirmed or explicitly overridden."
                ),
                "backup_confirmed": backup_confirmed,
                "override_backup_requirement": override_backup_requirement,
            },
            {
                "name": "maintenance_mode",
                "status": (
                    "pass"
                    if maintenance_mode_confirmed and active_sessions == 0
                    else "fail"
                ),
                "message": (
                    "Maintenance mode confirmation is present and no non-idle peer sessions were found."
                    if maintenance_mode_confirmed and active_sessions == 0
                    else "Maintenance mode is not confirmed or non-idle peer sessions are still active."
                ),
                "maintenance_mode_confirmed": maintenance_mode_confirmed,
                "active_non_idle_sessions": active_sessions,
            },
        ]
        checks = [
            CheckResult(
                name=str(row["name"]),
                status=CheckStatus.PASS if row["status"] == "pass" else CheckStatus.FAIL,
                message=str(row["message"]),
                details={key: value for key, value in row.items() if key not in {"name", "status", "message"}},
            )
            for row in rows
        ]
        apply_allowed = all(row["status"] == "pass" for row in rows)
        return {
            "rows": rows,
            "checks": checks,
            "status": CheckStatus.PASS if apply_allowed else CheckStatus.FAIL,
            "apply_allowed": apply_allowed,
        }

    def _selection_state(
        self,
        duplicate_groups: list[dict[str, object]],
        selected_delete_ids: tuple[str, ...],
    ) -> dict[str, object]:
        selected = set(selected_delete_ids)
        groups: list[dict[str, object]] = []
        delete_allowed = True if not selected else False
        for group in duplicate_groups:
            candidate_rows = [dict(item) for item in group.get("candidate_rows", [])]
            chosen = [str(row["id"]) for row in candidate_rows if str(row["id"]) in selected]
            remaining = len(candidate_rows) - len(chosen)
            if chosen and remaining >= 1:
                delete_allowed = True
            if chosen and remaining < 1:
                delete_allowed = False
            groups.append(
                {
                    **dict(group),
                    "user_selected_delete_ids": chosen,
                    "selected_delete_count": len(chosen),
                    "remaining_row_count_after_delete": remaining,
                }
            )
        if selected and not groups:
            delete_allowed = False
        return {
            "groups": groups,
            "selected_delete_ids": tuple(str(item) for item in selected_delete_ids),
            "delete_step_allowed": bool(selected) and delete_allowed,
        }

    def _plan_row(
        self,
        step_number: int,
        step_key: str,
        target: str,
        description: str,
        sql_preview: str | None,
        *,
        execution_state: str = "execute",
        requires_approval: bool = False,
        message: str | None = None,
    ) -> dict[str, object]:
        return {
            "step_number": step_number,
            "step_key": step_key,
            "target": target,
            "description": description,
            "sql_preview": sql_preview,
            "execution_state": execution_state,
            "requires_approval": requires_approval,
            "message": message,
        }

    def _apply_plan(
        self,
        settings: AppSettings,
        *,
        run: RepairRun,
        connection_check: CheckResult,
        guard_check: CheckResult,
        preconditions: dict[str, object],
        dsn: str,
        timeout: int,
        snapshot_before: dict[str, Any],
        plan_rows: list[dict[str, object]],
        selection: dict[str, object],
        before_cascade: dict[str, int],
    ) -> ValidationReport:
        executed_rows: list[dict[str, object]] = []
        any_applied = False
        run.status = RepairRunStatus.RUNNING
        self.repair_store.update_run(settings, run)
        try:
            for row in plan_rows:
                if row["execution_state"] == "blocked":
                    executed_rows.append({**row, "status": "blocked"})
                    continue
                if row["execution_state"] == "review":
                    executed_rows.append({**row, "status": "review"})
                    continue
                self._execute_step(
                    dsn,
                    timeout,
                    row,
                    selection["selected_delete_ids"],
                    snapshot_before["database_name"],
                )
                any_applied = True
                executed_rows.append({**row, "status": "applied"})
                self._append_journal(
                    settings,
                    run,
                    operation_type=str(row["step_key"]),
                    status=RepairJournalEntryStatus.APPLIED,
                    new_db_values={"sql_preview": row["sql_preview"]},
                )
        except Exception as exc:
            self._append_journal(
                settings,
                run,
                operation_type=str(row["step_key"]),
                status=RepairJournalEntryStatus.FAILED,
                new_db_values={"sql_preview": row.get("sql_preview")},
                error_details={"reason": str(exc)},
            )
            run.finish(RepairRunStatus.PARTIAL if any_applied else RepairRunStatus.FAILED)
            self.repair_store.update_run(settings, run)
            return ValidationReport(
                domain="db.corruption",
                action="repair.apply",
                summary=f"Database corruption apply failed during step `{row['step_key']}`: {exc}",
                checks=[connection_check, guard_check, *preconditions["checks"]],
                sections=[
                    ValidationSection(
                        name="EXECUTED_STEPS",
                        status=CheckStatus.FAIL,
                        rows=executed_rows,
                    )
                ],
                metadata={
                    "environment": settings.environment,
                    "repair_run_id": run.repair_run_id,
                    "dry_run": False,
                },
            )

        snapshot_after = self.scan_service._collect_snapshot(dsn, timeout)
        diff_rows = self._before_after_diff(
            snapshot_before,
            snapshot_after,
            selection["selected_delete_ids"],
            before_cascade,
        )
        run.finish(RepairRunStatus.COMPLETED)
        self.repair_store.update_run(settings, run)
        return ValidationReport(
            domain="db.corruption",
            action="repair.apply",
            summary="Database corruption apply completed and re-ran verification.",
            checks=[
                connection_check,
                guard_check,
                *preconditions["checks"],
                self._journal_check(settings, run),
            ],
            sections=[
                ValidationSection(
                    name="PRECONDITIONS",
                    status=preconditions["status"],
                    rows=preconditions["rows"],
                ),
                ValidationSection(
                    name="EXECUTED_STEPS",
                    status=CheckStatus.PASS if any_applied else CheckStatus.WARN,
                    rows=executed_rows,
                ),
                ValidationSection(
                    name="BEFORE_AFTER_DIFF",
                    status=CheckStatus.PASS,
                    rows=diff_rows,
                ),
            ],
            metadata={
                "environment": settings.environment,
                "repair_run_id": run.repair_run_id,
                "dry_run": False,
            },
            recommendations=[
                "Review the before/after diff and repair journal before performing further database maintenance.",
            ],
        )

    def _execute_step(
        self,
        dsn: str,
        timeout: int,
        row: dict[str, object],
        selected_delete_ids: tuple[str, ...],
        database_name: str,
    ) -> None:
        step_key = str(row["step_key"])
        if step_key == "clear_pg_statistic":
            self.postgres.execute_statement(dsn, timeout, "DELETE FROM pg_catalog.pg_statistic;")
            return
        if step_key == "reindex_system":
            self.postgres.execute_statement(dsn, timeout, str(row["sql_preview"]))
            return
        if step_key == "analyze_database":
            self.postgres.execute_statement(dsn, timeout, "ANALYZE;")
            return
        if step_key.startswith("reindex_invalid_user_index:"):
            self.postgres.execute_statement(dsn, timeout, str(row["sql_preview"]))
            return
        if step_key == "delete_duplicate_assets":
            self.postgres.delete_rows_by_column_values_returning_all(
                dsn,
                timeout,
                table_schema="public",
                table_name="asset",
                column_name="id",
                values=selected_delete_ids,
            )
            return
        if step_key == "reindex_database":
            self.postgres.execute_statement(dsn, timeout, str(row["sql_preview"]))
            return

    def _before_after_diff(
        self,
        before: dict[str, Any],
        after: dict[str, Any],
        selected_delete_ids: tuple[str, ...],
        before_cascade: dict[str, int],
    ) -> list[dict[str, object]]:
        return [
            {
                "metric": "toast_read_attempted",
                "before": "FAIL" if before["toast"]["detected"] else "PASS",
                "after": "FAIL" if after["toast"]["detected"] else "PASS",
            },
            {
                "metric": "invalid_system_indexes",
                "before": len(before["invalid_system_indexes"]),
                "after": len(after["invalid_system_indexes"]),
            },
            {
                "metric": "invalid_user_indexes",
                "before": len(before["invalid_user_indexes"]),
                "after": len(after["invalid_user_indexes"]),
            },
            {
                "metric": "duplicate_asset_groups",
                "before": len(before["duplicate_asset_groups"]),
                "after": len(after["duplicate_asset_groups"]),
            },
            {
                "metric": "rows_deleted_asset",
                "before": 0,
                "after": len(selected_delete_ids),
                "selected_ids": list(selected_delete_ids),
            },
            {
                "metric": "cascade_deletes_estimated",
                "before": before_cascade,
                "after": before_cascade,
            },
        ]

    def _cascade_counts(
        self,
        dsn: str,
        timeout: int,
        fk_constraints: list[dict[str, object]],
        selected_delete_ids: tuple[str, ...],
    ) -> dict[str, int]:
        counts: dict[str, int] = {}
        if not selected_delete_ids:
            return counts
        for row in fk_constraints:
            column_name = str(row.get("referencing_column") or "")
            if "," in column_name or not column_name:
                continue
            table_schema = str(row.get("referencing_schema") or "public")
            table_name = str(row["referencing_table"])
            related = self.postgres.list_rows_by_column_values(
                dsn,
                timeout,
                table_schema=table_schema,
                table_name=table_name,
                column_name=column_name,
                values=selected_delete_ids,
            )
            counts[f"{table_schema}.{table_name}"] = len(related)
        return counts

    def _db_fingerprint(self, snapshot: dict[str, Any]) -> str:
        return fingerprint_payload(
            {
                "toast": snapshot["toast"],
                "invalid_system_indexes": snapshot["invalid_system_indexes"],
                "invalid_user_indexes": snapshot["invalid_user_indexes"],
                "duplicate_asset_groups": [
                    {
                        "owner_id": row["owner_id"],
                        "checksum_hex": row["checksum_hex"],
                        "row_count": row["row_count"],
                        "candidate_ids": [candidate["id"] for candidate in row["candidate_rows"]],
                    }
                    for row in snapshot["duplicate_asset_groups"]
                ],
                "fk_constraints_on_asset": snapshot["fk_constraints_on_asset"],
            }
        )

    def _file_fingerprint_from_scope(self, scope: dict[str, Any]) -> str:
        return fingerprint_payload(
            {
                "selected_delete_ids": list(scope.get("selected_delete_ids", [])),
                "force_reindex_database": bool(scope.get("force_reindex_database")),
                "system_index_duplicate_error_text": str(
                    scope.get("system_index_duplicate_error_text") or ""
                ),
                "high_risk_clear_pg_statistic_approval": bool(
                    scope.get("high_risk_clear_pg_statistic_approval")
                ),
            }
        )

    def _delete_sql_preview(self, selected_delete_ids: tuple[str, ...]) -> str:
        joined = ", ".join(f"'{item}'" for item in selected_delete_ids)
        return f"DELETE FROM public.asset WHERE id IN ({joined});"

    def _preview_summary(self, plan_rows: list[dict[str, object]], apply_allowed: bool) -> str:
        executable = [
            row
            for row in plan_rows
            if row["execution_state"] == "execute" and row.get("sql_preview")
        ]
        if not executable:
            return "Database corruption repair preview produced only review steps and no executable SQL."
        if apply_allowed:
            return (
                f"Database corruption repair preview prepared {len(executable)} executable SQL steps."
            )
        return (
            f"Database corruption repair preview prepared {len(executable)} SQL steps, "
            "but apply remains blocked until the preconditions pass."
        )

    def _append_journal(
        self,
        settings: AppSettings,
        run: RepairRun,
        *,
        operation_type: str,
        status: RepairJournalEntryStatus,
        new_db_values: dict[str, object] | None,
        error_details: dict[str, object] | None = None,
    ) -> None:
        self.repair_store.append_journal_entry(
            settings,
            RepairJournalEntry(
                entry_id=uuid4().hex,
                repair_run_id=run.repair_run_id,
                operation_type=operation_type,
                status=status,
                asset_id=None,
                table=None,
                old_db_values=None,
                new_db_values=new_db_values,
                original_path=None,
                quarantine_path=None,
                undo_type=UndoType.NONE,
                undo_payload={},
                error_details=error_details,
            ),
        )

    def _journal_check(self, settings: AppSettings, run: RepairRun) -> CheckResult:
        return CheckResult(
            name="repair_journal",
            status=CheckStatus.PASS,
            message="Repair run foundation persisted manifest and journal files.",
            details={
                "repair_run_id": run.repair_run_id,
                "repair_run_path": str(repair_run_directory(settings, run.repair_run_id)),
                "plan_token_id": run.plan_token_id,
            },
        )
