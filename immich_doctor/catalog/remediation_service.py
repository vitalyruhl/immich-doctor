from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

from immich_doctor.adapters.external_tools import ExternalToolsAdapter
from immich_doctor.adapters.filesystem import FilesystemAdapter
from immich_doctor.adapters.postgres import PostgresAdapter
from immich_doctor.catalog.consistency_state import (
    SOURCE_ROOT_SLUG,
    CatalogConsistencyStateCollector,
)
from immich_doctor.catalog.remediation_models import (
    BrokenDbOriginalClassification,
    BrokenDbOriginalFinding,
    CatalogRemediationApplyResult,
    CatalogRemediationFindingKind,
    CatalogRemediationOperationItem,
    CatalogRemediationOperationStatus,
    CatalogRemediationPreviewResult,
    CatalogRemediationScanResult,
    FuseHiddenOrphanClassification,
    FuseHiddenOrphanFinding,
)
from immich_doctor.consistency.missing_asset_models import (
    MissingAssetOperationItem,
    MissingAssetReferenceFinding,
    MissingAssetReferenceStatus,
    RepairReadinessStatus,
)
from immich_doctor.consistency.missing_asset_service import MissingAssetReferenceService
from immich_doctor.core.config import AppSettings
from immich_doctor.core.models import CheckResult, CheckStatus
from immich_doctor.db.schema_detection import DatabaseStateDetector
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
class CatalogRemediationService:
    postgres: PostgresAdapter = field(default_factory=PostgresAdapter)
    filesystem: FilesystemAdapter = field(default_factory=FilesystemAdapter)
    external_tools: ExternalToolsAdapter = field(default_factory=ExternalToolsAdapter)
    repair_store: RepairJournalStore = field(default_factory=RepairJournalStore)

    def scan(self, settings: AppSettings) -> CatalogRemediationScanResult:
        snapshot_collector = CatalogConsistencyStateCollector(postgres=self.postgres)
        snapshot_state = snapshot_collector.prepare_snapshot_state(settings)
        if not snapshot_state.ready:
            return CatalogRemediationScanResult(
                summary="Catalog remediation is waiting for a current committed storage index.",
                checks=snapshot_state.checks,
                broken_db_originals=[],
                fuse_hidden_orphans=[],
                metadata=snapshot_state.metadata,
                recommendations=[
                    "Run a catalog scan from the Storage page before preparing "
                    "remediation actions.",
                ],
            )

        dsn = settings.postgres_dsn_value()
        if not dsn:
            return CatalogRemediationScanResult(
                summary="Catalog remediation failed because database access is not configured.",
                checks=[
                    *snapshot_state.checks,
                    CheckResult(
                        name="postgres_connection",
                        status=CheckStatus.FAIL,
                        message="Database DSN is not configured.",
                    ),
                ],
                broken_db_originals=[],
                fuse_hidden_orphans=[],
                metadata={"latestSnapshots": snapshot_state.latest_snapshots},
            )

        timeout = settings.postgres_connect_timeout_seconds
        connection_check = self.postgres.validate_connection(dsn, timeout)
        if connection_check.status == CheckStatus.FAIL:
            return CatalogRemediationScanResult(
                summary="Catalog remediation failed because PostgreSQL could not be reached.",
                checks=[*snapshot_state.checks, connection_check],
                broken_db_originals=[],
                fuse_hidden_orphans=[],
                metadata={"latestSnapshots": snapshot_state.latest_snapshots},
            )

        state = snapshot_collector.collect(settings)
        broken_db_originals = self._build_broken_db_original_findings(settings, state=state)
        fuse_hidden_orphans = self._build_fuse_hidden_findings(settings, state=state)
        summary = (
            "Catalog remediation classified "
            f"{len(broken_db_originals)} broken DB originals and "
            f"{len(fuse_hidden_orphans)} `.fuse_hidden*` orphan artifacts."
        )
        return CatalogRemediationScanResult(
            summary=summary,
            checks=state.checks,
            broken_db_originals=broken_db_originals,
            fuse_hidden_orphans=fuse_hidden_orphans,
            metadata={
                "configuredRoots": state.configured_root_slugs,
                "latestSnapshots": state.latest_snapshots,
                "snapshotBasis": state.snapshot_basis,
                "latestScanCommittedAt": state.latest_scan_committed_at,
                "totals": {
                    "brokenDbOriginals": len(broken_db_originals),
                    "brokenDbOriginalsEligible": sum(
                        1 for item in broken_db_originals if item.action_eligible
                    ),
                    "fuseHiddenOrphans": len(fuse_hidden_orphans),
                    "fuseHiddenOrphansEligible": sum(
                        1 for item in fuse_hidden_orphans if item.action_eligible
                    ),
                },
            },
            recommendations=[
                "Review `found_elsewhere` rows manually before considering any path rebind flow.",
                "Only `missing_confirmed` and `deletable_orphan` rows become eligible for apply.",
            ],
        )

    def preview_broken_db_originals(
        self,
        settings: AppSettings,
        *,
        asset_ids: tuple[str, ...],
        select_all: bool,
    ) -> CatalogRemediationPreviewResult:
        scan_result = self.scan(settings)
        selected_findings = self._select_broken_db_originals(
            findings=scan_result.broken_db_originals,
            asset_ids=asset_ids,
            select_all=select_all,
        )
        return self._preview_result(
            settings,
            scan_result=scan_result,
            finding_kind=CatalogRemediationFindingKind.BROKEN_DB_ORIGINAL,
            selected_items=[item.to_dict() for item in selected_findings],
            selected_ids=[item.asset_id for item in selected_findings],
            scope_key="asset_ids",
            select_all=select_all,
        )

    def preview_fuse_hidden_orphans(
        self,
        settings: AppSettings,
        *,
        finding_ids: tuple[str, ...],
        select_all: bool,
    ) -> CatalogRemediationPreviewResult:
        scan_result = self.scan(settings)
        selected_findings = self._select_fuse_hidden_orphans(
            findings=scan_result.fuse_hidden_orphans,
            finding_ids=finding_ids,
            select_all=select_all,
        )
        return self._preview_result(
            settings,
            scan_result=scan_result,
            finding_kind=CatalogRemediationFindingKind.FUSE_HIDDEN_ORPHAN,
            selected_items=[item.to_dict() for item in selected_findings],
            selected_ids=[item.finding_id for item in selected_findings],
            scope_key="finding_ids",
            select_all=select_all,
        )

    def apply(self, settings: AppSettings, *, repair_run_id: str) -> CatalogRemediationApplyResult:
        run = self.repair_store.load_run(settings, repair_run_id)
        plan_token = self.repair_store.load_plan_token(settings, repair_run_id)
        finding_kind = CatalogRemediationFindingKind(str(run.scope["finding_kind"]))
        scan_result = self.scan(settings)

        if finding_kind == CatalogRemediationFindingKind.BROKEN_DB_ORIGINAL:
            selected_findings = self._select_broken_db_originals(
                findings=scan_result.broken_db_originals,
                asset_ids=tuple(str(item) for item in run.scope.get("asset_ids", [])),
                select_all=bool(run.scope.get("select_all", False)),
            )
            current_scope_ids = [item.asset_id for item in selected_findings]
            scope_key = "asset_ids"
        else:
            selected_findings = self._select_fuse_hidden_orphans(
                findings=scan_result.fuse_hidden_orphans,
                finding_ids=tuple(str(item) for item in run.scope.get("finding_ids", [])),
                select_all=bool(run.scope.get("select_all", False)),
            )
            current_scope_ids = [item.finding_id for item in selected_findings]
            scope_key = "finding_ids"

        scope = dict(run.scope)
        scope[scope_key] = current_scope_ids
        guard_result = validate_plan_token(
            plan_token,
            scope=scope,
            db_fingerprint=self._db_fingerprint(selected_findings),
            file_fingerprint=self._file_fingerprint(selected_findings),
        )
        guard_check = CheckResult(
            name="catalog_remediation_apply_guard",
            status=CheckStatus.PASS if guard_result.valid else CheckStatus.FAIL,
            message=guard_result.reason,
            details={
                "repair_run_id": repair_run_id,
                "token_id": guard_result.token_id,
                "expected_db_fingerprint": guard_result.expected_db_fingerprint,
                "expected_file_fingerprint": guard_result.expected_file_fingerprint,
                "actual_db_fingerprint": guard_result.actual_db_fingerprint,
                "actual_file_fingerprint": guard_result.actual_file_fingerprint,
            },
        )
        if not guard_result.valid:
            run.finish(RepairRunStatus.FAILED)
            self.repair_store.update_run(settings, run)
            return CatalogRemediationApplyResult(
                summary="Apply stopped because the preview scope drifted before mutation.",
                checks=[*scan_result.checks, guard_check],
                finding_kind=finding_kind,
                repair_run_id=repair_run_id,
                items=[],
                metadata={"environment": settings.environment, "dry_run": False},
                recommendations=[
                    "Re-run preview to bind a fresh plan token to the current live state.",
                ],
            )

        run.status = RepairRunStatus.RUNNING
        self.repair_store.update_run(settings, run)
        if finding_kind == CatalogRemediationFindingKind.BROKEN_DB_ORIGINAL:
            items = self._apply_broken_db_originals(
                settings,
                repair_run=run,
                findings=selected_findings,
            )
        else:
            items = self._apply_fuse_hidden_orphans(
                settings,
                repair_run=run,
                findings=selected_findings,
            )
        run.finish(self._final_run_status(items))
        self.repair_store.update_run(settings, run)
        return CatalogRemediationApplyResult(
            summary=f"Apply processed {len(items)} selected remediation items.",
            checks=[*scan_result.checks, guard_check, self._journal_check(settings, run)],
            finding_kind=finding_kind,
            repair_run_id=repair_run_id,
            items=items,
            metadata={"environment": settings.environment, "dry_run": False},
            recommendations=[
                "Review the repair journal and any generated restore metadata "
                "before follow-up actions.",
            ],
        )

    def _preview_result(
        self,
        settings: AppSettings,
        *,
        scan_result: CatalogRemediationScanResult,
        finding_kind: CatalogRemediationFindingKind,
        selected_items: list[dict[str, object]],
        selected_ids: list[str],
        scope_key: str,
        select_all: bool,
    ) -> CatalogRemediationPreviewResult:
        scope = {
            "domain": "consistency.catalog_remediation",
            "action": "preview",
            "finding_kind": finding_kind.value,
            scope_key: selected_ids,
            "select_all": select_all,
        }
        plan_token = create_plan_token(
            scope=scope,
            db_fingerprint=self._db_fingerprint(selected_items),
            file_fingerprint=self._file_fingerprint(selected_items),
        )
        repair_run = RepairRun.new(
            repair_run_id=uuid4().hex,
            scope=scope,
            status=RepairRunStatus.PLANNED,
            live_state_fingerprint=build_live_state_fingerprint(
                db_fingerprint=plan_token.db_fingerprint,
                file_fingerprint=plan_token.file_fingerprint,
            ),
            plan_token_id=plan_token.token_id,
        )
        self.repair_store.create_run(settings, repair_run=repair_run, plan_token=plan_token)
        checks = list(scan_result.checks)
        checks.append(
            CheckResult(
                name="catalog_remediation_preview_selection",
                status=CheckStatus.PASS if selected_items else CheckStatus.WARN,
                message=(
                    f"Preview selected {len(selected_items)} eligible remediation items."
                    if selected_items
                    else "Preview selected no eligible remediation items."
                ),
                details={
                    "select_all": select_all,
                    "repair_run_id": repair_run.repair_run_id,
                    "finding_kind": finding_kind.value,
                },
            )
        )
        checks.append(
            CheckResult(
                name="repair_run_foundation",
                status=CheckStatus.PASS,
                message="Preview persisted a repair run and plan token for later apply.",
                details={
                    "repair_run_id": repair_run.repair_run_id,
                    "repair_run_path": str(
                        repair_run_directory(settings, repair_run.repair_run_id)
                    ),
                    "plan_token_id": plan_token.token_id,
                },
            )
        )
        return CatalogRemediationPreviewResult(
            summary=f"Preview planned {len(selected_items)} remediation items.",
            checks=checks,
            finding_kind=finding_kind,
            repair_run_id=repair_run.repair_run_id,
            selected_items=selected_items,
            metadata={"environment": settings.environment, "dry_run": True},
            recommendations=[
                "Review the exact selected rows before apply and re-run preview "
                "after any scan change.",
            ],
        )

    def _build_broken_db_original_findings(
        self,
        settings: AppSettings,
        *,
        state,
    ) -> list[BrokenDbOriginalFinding]:
        files_by_name: dict[str, list[dict[str, object]]] = {}
        for row in state.latest_files:
            file_name = str(row.get("file_name") or "")
            if file_name:
                files_by_name.setdefault(file_name, []).append(row)

        findings: list[BrokenDbOriginalFinding] = []
        uploads_root = settings.immich_uploads_path
        for row in state.db_missing_rows:
            asset_name = str(row.get("asset_name") or "").strip() or None
            try:
                matches = files_by_name.get(asset_name or "", [])
                relocated_match = next(
                    (
                        item
                        for item in matches
                        if str(item["root_slug"]) == SOURCE_ROOT_SLUG
                        and str(item["relative_path"]) != str(row["relative_path"])
                    ),
                    None,
                )
                if relocated_match is not None and uploads_root is not None:
                    found_relative_path = str(relocated_match["relative_path"])
                    findings.append(
                        BrokenDbOriginalFinding(
                            finding_id=f"broken-db-original:{row['asset_id']}",
                            kind=CatalogRemediationFindingKind.BROKEN_DB_ORIGINAL,
                            asset_id=str(row["asset_id"]),
                            asset_name=asset_name,
                            asset_type=str(row.get("asset_type") or "") or None,
                            expected_database_path=str(row["database_path"]),
                            expected_relative_path=str(row["relative_path"]),
                            classification=BrokenDbOriginalClassification.FOUND_ELSEWHERE,
                            action_eligible=False,
                            action_reason=(
                                "A file with the same name exists elsewhere in storage. "
                                "This row is inspect-only by default."
                            ),
                            found_root_slug=str(relocated_match["root_slug"]),
                            found_relative_path=found_relative_path,
                            found_absolute_path=str(uploads_root / found_relative_path),
                            found_size_bytes=int(relocated_match["size_bytes"]),
                            expected_size_bytes=None,
                            message=(
                                "Expected storage path is missing, but a same-name file was found "
                                "elsewhere in the cached storage inventory."
                            ),
                        )
                    )
                    continue
                findings.append(
                    BrokenDbOriginalFinding(
                        finding_id=f"broken-db-original:{row['asset_id']}",
                        kind=CatalogRemediationFindingKind.BROKEN_DB_ORIGINAL,
                        asset_id=str(row["asset_id"]),
                        asset_name=asset_name,
                        asset_type=str(row.get("asset_type") or "") or None,
                        expected_database_path=str(row["database_path"]),
                        expected_relative_path=str(row["relative_path"]),
                        classification=BrokenDbOriginalClassification.MISSING_CONFIRMED,
                        action_eligible=True,
                        action_reason=(
                            "The expected storage path is absent and no same-name relocation was "
                            "found in the current cached storage inventory."
                        ),
                        message=(
                            "Expected storage path is missing and the cached storage inventory "
                            "found no same-name relocation."
                        ),
                    )
                )
            except Exception as exc:
                findings.append(
                    BrokenDbOriginalFinding(
                        finding_id=f"broken-db-original:{row['asset_id']}",
                        kind=CatalogRemediationFindingKind.BROKEN_DB_ORIGINAL,
                        asset_id=str(row["asset_id"]),
                        asset_name=asset_name,
                        asset_type=str(row.get("asset_type") or "") or None,
                        expected_database_path=str(row["database_path"]),
                        expected_relative_path=str(row["relative_path"]),
                        classification=BrokenDbOriginalClassification.UNRESOLVED_SEARCH_ERROR,
                        action_eligible=False,
                        action_reason="Relocation search did not complete safely.",
                        search_error=str(exc),
                        message="Relocation search failed and the row remains inspect-only.",
                    )
                )
        return findings

    def _build_fuse_hidden_findings(
        self,
        settings: AppSettings,
        *,
        state,
    ) -> list[FuseHiddenOrphanFinding]:
        uploads_root = settings.immich_uploads_path
        if uploads_root is None:
            return []

        findings: list[FuseHiddenOrphanFinding] = []
        for row in state.storage_missing_rows:
            file_name = str(row["file_name"])
            if file_name == ".immich":
                continue
            if not file_name.startswith(".fuse_hidden"):
                continue
            absolute_path = uploads_root / str(row["relative_path"])
            inspection = self.external_tools.inspect_open_file_handles(absolute_path)
            tool = str(inspection.get("tool")) if inspection.get("tool") is not None else None
            reason = str(inspection.get("reason") or "").strip() or None
            status = str(inspection.get("status") or "")
            if status == "in_use":
                findings.append(
                    FuseHiddenOrphanFinding(
                        finding_id=f"fuse-hidden:{row['root_slug']}:{row['relative_path']}",
                        kind=CatalogRemediationFindingKind.FUSE_HIDDEN_ORPHAN,
                        root_slug=str(row["root_slug"]),
                        relative_path=str(row["relative_path"]),
                        absolute_path=str(absolute_path),
                        file_name=file_name,
                        size_bytes=int(row["size_bytes"]),
                        classification=FuseHiddenOrphanClassification.BLOCKED_IN_USE,
                        action_eligible=False,
                        action_reason="The orphan artifact is still held open by a process.",
                        in_use_check_tool=tool,
                        in_use_check_reason=reason,
                        message="The file is still in use and cannot be removed safely.",
                    )
                )
                continue
            if status == "not_in_use":
                findings.append(
                    FuseHiddenOrphanFinding(
                        finding_id=f"fuse-hidden:{row['root_slug']}:{row['relative_path']}",
                        kind=CatalogRemediationFindingKind.FUSE_HIDDEN_ORPHAN,
                        root_slug=str(row["root_slug"]),
                        relative_path=str(row["relative_path"]),
                        absolute_path=str(absolute_path),
                        file_name=file_name,
                        size_bytes=int(row["size_bytes"]),
                        classification=FuseHiddenOrphanClassification.DELETABLE_ORPHAN,
                        action_eligible=True,
                        action_reason="The orphan artifact is not reported as in use.",
                        in_use_check_tool=tool,
                        in_use_check_reason=reason,
                        message=(
                            "The orphan artifact can be deleted through an "
                            "explicit apply step."
                        ),
                    )
                )
                continue
            findings.append(
                FuseHiddenOrphanFinding(
                    finding_id=f"fuse-hidden:{row['root_slug']}:{row['relative_path']}",
                    kind=CatalogRemediationFindingKind.FUSE_HIDDEN_ORPHAN,
                    root_slug=str(row["root_slug"]),
                    relative_path=str(row["relative_path"]),
                    absolute_path=str(absolute_path),
                    file_name=file_name,
                    size_bytes=int(row["size_bytes"]),
                    classification=FuseHiddenOrphanClassification.CHECK_FAILED,
                    action_eligible=False,
                    action_reason="The in-use check was unavailable or failed.",
                    in_use_check_tool=tool,
                    in_use_check_reason=reason,
                    message="The in-use check could not be completed safely.",
                )
            )
        return findings

    def _select_broken_db_originals(
        self,
        *,
        findings: list[BrokenDbOriginalFinding],
        asset_ids: tuple[str, ...],
        select_all: bool,
    ) -> list[BrokenDbOriginalFinding]:
        selected_ids = set(asset_ids)
        return [
            finding
            for finding in findings
            if finding.action_eligible and (select_all or finding.asset_id in selected_ids)
        ]

    def _select_fuse_hidden_orphans(
        self,
        *,
        findings: list[FuseHiddenOrphanFinding],
        finding_ids: tuple[str, ...],
        select_all: bool,
    ) -> list[FuseHiddenOrphanFinding]:
        selected_ids = set(finding_ids)
        return [
            finding
            for finding in findings
            if finding.action_eligible and (select_all or finding.finding_id in selected_ids)
        ]

    def _apply_broken_db_originals(
        self,
        settings: AppSettings,
        *,
        repair_run: RepairRun,
        findings: list[BrokenDbOriginalFinding],
    ) -> list[CatalogRemediationOperationItem]:
        dsn = settings.postgres_dsn_value()
        if dsn is None:
            return []
        timeout = settings.postgres_connect_timeout_seconds
        asset_service = MissingAssetReferenceService(
            postgres=self.postgres,
            filesystem=self.filesystem,
            repair_store=self.repair_store,
        )
        profile = asset_service._detect_profile(
            DatabaseStateDetector(self.postgres).detect(dsn, timeout)
        )
        items: list[CatalogRemediationOperationItem] = []
        for finding in findings:
            synthetic_finding = MissingAssetReferenceFinding(
                finding_id=finding.finding_id,
                asset_id=finding.asset_id,
                asset_type=finding.asset_type or "unknown",
                status=MissingAssetReferenceStatus.MISSING_ON_DISK,
                logical_path=finding.expected_database_path,
                resolved_physical_path=finding.expected_relative_path,
                owner_id=None,
                created_at=None,
                updated_at=None,
                scan_timestamp="",
                repair_readiness=RepairReadinessStatus.READY,
                repair_blockers=(),
                repair_blocker_details=(),
                message=finding.message,
            )
            result = asset_service._apply_single_asset(
                settings,
                dsn=dsn,
                timeout=timeout,
                asset_id=finding.asset_id,
                finding=synthetic_finding,
                repair_run=repair_run,
                relations=profile.relations,
            )
            items.append(self._map_missing_asset_operation(finding.finding_id, result))
        return items

    def _apply_fuse_hidden_orphans(
        self,
        settings: AppSettings,
        *,
        repair_run: RepairRun,
        findings: list[FuseHiddenOrphanFinding],
    ) -> list[CatalogRemediationOperationItem]:
        items: list[CatalogRemediationOperationItem] = []
        uploads_root = settings.immich_uploads_path
        if uploads_root is None:
            return items
        for finding in findings:
            target_path = Path(finding.absolute_path)
            if not self.filesystem.is_child_path(uploads_root, target_path):
                self._record_fuse_hidden_journal(
                    settings,
                    repair_run=repair_run,
                    finding=finding,
                    status=RepairJournalEntryStatus.SKIPPED,
                    error_details={"reason": "Target path is outside the uploads root."},
                )
                items.append(
                    CatalogRemediationOperationItem(
                        finding_id=finding.finding_id,
                        kind=CatalogRemediationFindingKind.FUSE_HIDDEN_ORPHAN,
                        target_id=finding.relative_path,
                        status=CatalogRemediationOperationStatus.SKIPPED,
                        message="Target path is outside the uploads root and was not touched.",
                    )
                )
                continue
            if not self.filesystem.path_exists(target_path):
                self._record_fuse_hidden_journal(
                    settings,
                    repair_run=repair_run,
                    finding=finding,
                    status=RepairJournalEntryStatus.SKIPPED,
                    error_details={"reason": "Artifact is already absent."},
                )
                items.append(
                    CatalogRemediationOperationItem(
                        finding_id=finding.finding_id,
                        kind=CatalogRemediationFindingKind.FUSE_HIDDEN_ORPHAN,
                        target_id=finding.relative_path,
                        status=CatalogRemediationOperationStatus.ALREADY_REMOVED,
                        message="Artifact is already absent from storage.",
                    )
                )
                continue
            try:
                self.filesystem.delete_file(target_path)
            except Exception as exc:
                self._record_fuse_hidden_journal(
                    settings,
                    repair_run=repair_run,
                    finding=finding,
                    status=RepairJournalEntryStatus.FAILED,
                    error_details={"reason": str(exc)},
                )
                items.append(
                    CatalogRemediationOperationItem(
                        finding_id=finding.finding_id,
                        kind=CatalogRemediationFindingKind.FUSE_HIDDEN_ORPHAN,
                        target_id=finding.relative_path,
                        status=CatalogRemediationOperationStatus.FAILED,
                        message=f"Deletion failed: {exc}",
                    )
                )
                continue
            self._record_fuse_hidden_journal(
                settings,
                repair_run=repair_run,
                finding=finding,
                status=RepairJournalEntryStatus.APPLIED,
                error_details=None,
            )
            items.append(
                CatalogRemediationOperationItem(
                    finding_id=finding.finding_id,
                    kind=CatalogRemediationFindingKind.FUSE_HIDDEN_ORPHAN,
                    target_id=finding.relative_path,
                    status=CatalogRemediationOperationStatus.APPLIED,
                    message="Artifact was deleted from storage.",
                    details={"absolute_path": finding.absolute_path},
                )
            )
        return items

    def _map_missing_asset_operation(
        self,
        finding_id: str,
        result: MissingAssetOperationItem,
    ) -> CatalogRemediationOperationItem:
        if result.status.value == "applied":
            mapped_status = CatalogRemediationOperationStatus.APPLIED
        elif result.status.value == "already_removed":
            mapped_status = CatalogRemediationOperationStatus.ALREADY_REMOVED
        elif result.status.value == "failed":
            mapped_status = CatalogRemediationOperationStatus.FAILED
        else:
            mapped_status = CatalogRemediationOperationStatus.SKIPPED
        return CatalogRemediationOperationItem(
            finding_id=finding_id,
            kind=CatalogRemediationFindingKind.BROKEN_DB_ORIGINAL,
            target_id=result.asset_id,
            status=mapped_status,
            message=result.message,
            details=result.details,
        )

    def _record_fuse_hidden_journal(
        self,
        settings: AppSettings,
        *,
        repair_run: RepairRun,
        finding: FuseHiddenOrphanFinding,
        status: RepairJournalEntryStatus,
        error_details: dict[str, object] | None,
    ) -> None:
        entry = RepairJournalEntry(
            entry_id=uuid4().hex,
            repair_run_id=repair_run.repair_run_id,
            operation_type="delete_fuse_hidden_orphan",
            status=status,
            asset_id=None,
            table=None,
            old_db_values=None,
            new_db_values={"absolute_path": finding.absolute_path}
            if status == RepairJournalEntryStatus.APPLIED
            else None,
            original_path=finding.absolute_path,
            quarantine_path=None,
            undo_type=UndoType.NONE,
            undo_payload={},
            error_details=error_details,
        )
        self.repair_store.append_journal_entry(settings, entry)

    def _db_fingerprint(self, items: list[object]) -> str:
        return fingerprint_payload([self._fingerprintable_item(item) for item in items])

    def _file_fingerprint(self, items: list[object]) -> str:
        return fingerprint_payload([self._fingerprintable_item(item) for item in items])

    def _fingerprintable_item(self, item: object) -> object:
        if isinstance(item, dict):
            return item
        to_dict = getattr(item, "to_dict", None)
        if callable(to_dict):
            return to_dict()
        return str(item)

    def _final_run_status(self, items: list[CatalogRemediationOperationItem]) -> RepairRunStatus:
        if any(item.status == CatalogRemediationOperationStatus.FAILED for item in items):
            if any(item.status == CatalogRemediationOperationStatus.APPLIED for item in items):
                return RepairRunStatus.PARTIAL
            return RepairRunStatus.FAILED
        return RepairRunStatus.COMPLETED

    def _journal_check(self, settings: AppSettings, repair_run: RepairRun) -> CheckResult:
        return CheckResult(
            name="repair_journal",
            status=CheckStatus.PASS,
            message="Repair run foundation persisted manifest and journal files.",
            details={
                "repair_run_id": repair_run.repair_run_id,
                "repair_run_path": str(repair_run_directory(settings, repair_run.repair_run_id)),
                "plan_token_id": repair_run.plan_token_id,
            },
        )
