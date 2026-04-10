from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

from immich_doctor.adapters.external_tools import ExternalToolsAdapter
from immich_doctor.adapters.filesystem import FilesystemAdapter
from immich_doctor.adapters.postgres import PostgresAdapter
from immich_doctor.catalog.consistency_state import (
    SOURCE_ROOT_SLUG,
    CatalogConsistencyState,
    CatalogConsistencyStateCollector,
    truthy_path,
)
from immich_doctor.catalog.remediation_models import (
    BrokenDbOriginalClassification,
    BrokenDbOriginalFinding,
    CatalogRemediationActionKind,
    CatalogRemediationApplyResult,
    CatalogRemediationFindingKind,
    CatalogRemediationOperationItem,
    CatalogRemediationOperationStatus,
    CatalogRemediationPreviewResult,
    CatalogRemediationScanResult,
    FuseHiddenOrphanClassification,
    FuseHiddenOrphanFinding,
    ZeroByteClassification,
    ZeroByteFinding,
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
from immich_doctor.storage.path_mapping import ImmichStoragePathResolver


@dataclass(slots=True, frozen=True)
class _LocatedFile:
    root_slug: str
    relative_path: str
    absolute_path: str
    file_name: str
    size_bytes: int


@dataclass(slots=True)
class CatalogRemediationService:
    postgres: PostgresAdapter = field(default_factory=PostgresAdapter)
    filesystem: FilesystemAdapter = field(default_factory=FilesystemAdapter)
    external_tools: ExternalToolsAdapter = field(default_factory=ExternalToolsAdapter)
    repair_store: RepairJournalStore = field(default_factory=RepairJournalStore)

    def scan(
        self,
        settings: AppSettings,
        *,
        classifications: tuple[str, ...] = (),
    ) -> CatalogRemediationScanResult:
        snapshot_collector = CatalogConsistencyStateCollector(postgres=self.postgres)
        snapshot_state = snapshot_collector.prepare_snapshot_state(settings)
        if not snapshot_state.ready:
            return CatalogRemediationScanResult(
                summary="Catalog remediation is waiting for a current committed storage index.",
                checks=snapshot_state.checks,
                broken_db_originals=[],
                zero_byte_findings=[],
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
                zero_byte_findings=[],
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
                zero_byte_findings=[],
                fuse_hidden_orphans=[],
                metadata={"latestSnapshots": snapshot_state.latest_snapshots},
            )

        state = snapshot_collector.collect(settings)
        broken_db_originals = self._build_broken_db_original_findings(settings, state=state)
        zero_byte_findings = self._build_zero_byte_findings(settings, state=state)
        fuse_hidden_orphans = self._build_fuse_hidden_findings(settings, state=state)
        result = CatalogRemediationScanResult(
            summary=(
                "Catalog remediation classified "
                f"{len(broken_db_originals)} broken DB originals, "
                f"{len(zero_byte_findings)} zero-byte files, and "
                f"{len(fuse_hidden_orphans)} `.fuse_hidden*` orphan artifacts."
            ),
            checks=state.checks,
            broken_db_originals=broken_db_originals,
            zero_byte_findings=zero_byte_findings,
            fuse_hidden_orphans=fuse_hidden_orphans,
            metadata={
                "configuredRoots": state.configured_root_slugs,
                "latestSnapshots": state.latest_snapshots,
                "snapshotBasis": state.snapshot_basis,
                "latestScanCommittedAt": state.latest_scan_committed_at,
                "totals": {
                    "brokenDbOriginals": len(broken_db_originals),
                    "brokenDbCleanupEligible": sum(
                        1
                        for item in broken_db_originals
                        if item.supports_action(CatalogRemediationActionKind.BROKEN_DB_CLEANUP)
                    ),
                    "brokenDbPathFixEligible": sum(
                        1
                        for item in broken_db_originals
                        if item.supports_action(CatalogRemediationActionKind.BROKEN_DB_PATH_FIX)
                    ),
                    "zeroByteFindings": len(zero_byte_findings),
                    "zeroByteEligible": sum(
                        1 for item in zero_byte_findings if item.action_eligible
                    ),
                    "fuseHiddenOrphans": len(fuse_hidden_orphans),
                    "fuseHiddenEligible": sum(
                        1 for item in fuse_hidden_orphans if item.action_eligible
                    ),
                },
            },
            recommendations=[
                "Review `found_elsewhere` rows manually before any path-fix decision.",
                "Only hash-verified path mismatches become eligible for explicit "
                "DB path correction.",
                "Zero-byte uploads referenced as originals remain inspect-only by default.",
            ],
        )
        return self._filter_scan_result(result, classifications=classifications)

    def preview_broken_db_cleanup(
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
            action_kind=CatalogRemediationActionKind.BROKEN_DB_CLEANUP,
        )
        return self._preview_result(
            settings,
            scan_result=scan_result,
            finding_kind=CatalogRemediationFindingKind.BROKEN_DB_ORIGINAL,
            action_kind=CatalogRemediationActionKind.BROKEN_DB_CLEANUP,
            selected_items=[item.to_dict() for item in selected_findings],
            selected_ids=[item.asset_id for item in selected_findings],
            scope_key="asset_ids",
            select_all=select_all,
        )

    def preview_broken_db_path_fix(
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
            action_kind=CatalogRemediationActionKind.BROKEN_DB_PATH_FIX,
        )
        return self._preview_result(
            settings,
            scan_result=scan_result,
            finding_kind=CatalogRemediationFindingKind.BROKEN_DB_ORIGINAL,
            action_kind=CatalogRemediationActionKind.BROKEN_DB_PATH_FIX,
            selected_items=[item.to_dict() for item in selected_findings],
            selected_ids=[item.asset_id for item in selected_findings],
            scope_key="asset_ids",
            select_all=select_all,
        )

    def preview_zero_byte_files(
        self,
        settings: AppSettings,
        *,
        finding_ids: tuple[str, ...],
        select_all: bool,
    ) -> CatalogRemediationPreviewResult:
        scan_result = self.scan(settings)
        selected_findings = self._select_zero_byte_findings(
            findings=scan_result.zero_byte_findings,
            finding_ids=finding_ids,
            select_all=select_all,
        )
        return self._preview_result(
            settings,
            scan_result=scan_result,
            finding_kind=CatalogRemediationFindingKind.ZERO_BYTE_FILE,
            action_kind=CatalogRemediationActionKind.ZERO_BYTE_DELETE,
            selected_items=[item.to_dict() for item in selected_findings],
            selected_ids=[item.finding_id for item in selected_findings],
            scope_key="finding_ids",
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
            action_kind=CatalogRemediationActionKind.FUSE_HIDDEN_DELETE,
            selected_items=[item.to_dict() for item in selected_findings],
            selected_ids=[item.finding_id for item in selected_findings],
            scope_key="finding_ids",
            select_all=select_all,
        )

    def apply(self, settings: AppSettings, *, repair_run_id: str) -> CatalogRemediationApplyResult:
        run = self.repair_store.load_run(settings, repair_run_id)
        plan_token = self.repair_store.load_plan_token(settings, repair_run_id)
        finding_kind = CatalogRemediationFindingKind(str(run.scope["finding_kind"]))
        action_kind = CatalogRemediationActionKind(str(run.scope["action_kind"]))
        scan_result = self.scan(settings)

        if finding_kind == CatalogRemediationFindingKind.BROKEN_DB_ORIGINAL:
            selected_findings = self._select_broken_db_originals(
                findings=scan_result.broken_db_originals,
                asset_ids=tuple(str(item) for item in run.scope.get("asset_ids", [])),
                select_all=bool(run.scope.get("select_all", False)),
                action_kind=action_kind,
            )
            current_scope_ids = [item.asset_id for item in selected_findings]
            scope_key = "asset_ids"
        elif finding_kind == CatalogRemediationFindingKind.ZERO_BYTE_FILE:
            selected_findings = self._select_zero_byte_findings(
                findings=scan_result.zero_byte_findings,
                finding_ids=tuple(str(item) for item in run.scope.get("finding_ids", [])),
                select_all=bool(run.scope.get("select_all", False)),
            )
            current_scope_ids = [item.finding_id for item in selected_findings]
            scope_key = "finding_ids"
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
                action_kind=action_kind,
                repair_run_id=repair_run_id,
                items=[],
                metadata={"environment": settings.environment, "dry_run": False},
                recommendations=[
                    "Re-run preview to bind a fresh plan token to the current live state.",
                ],
            )

        run.status = RepairRunStatus.RUNNING
        self.repair_store.update_run(settings, run)
        if action_kind == CatalogRemediationActionKind.BROKEN_DB_CLEANUP:
            items = self._apply_broken_db_cleanup(
                settings,
                repair_run=run,
                findings=selected_findings,
            )
        elif action_kind == CatalogRemediationActionKind.BROKEN_DB_PATH_FIX:
            items = self._apply_broken_db_path_fix(
                settings,
                repair_run=run,
                findings=selected_findings,
            )
        elif action_kind == CatalogRemediationActionKind.ZERO_BYTE_DELETE:
            items = self._apply_zero_byte_findings(
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
            action_kind=action_kind,
            repair_run_id=repair_run_id,
            items=items,
            metadata={"environment": settings.environment, "dry_run": False},
            recommendations=[
                "Review the repair journal and any generated restore metadata "
                "before follow-up actions.",
            ],
        )

    def _filter_scan_result(
        self,
        result: CatalogRemediationScanResult,
        *,
        classifications: tuple[str, ...],
    ) -> CatalogRemediationScanResult:
        if not classifications:
            return result
        allowed = {item.strip() for item in classifications if item.strip()}
        return CatalogRemediationScanResult(
            summary=result.summary,
            checks=result.checks,
            broken_db_originals=[
                item for item in result.broken_db_originals if item.classification.value in allowed
            ],
            zero_byte_findings=[
                item for item in result.zero_byte_findings if item.classification.value in allowed
            ],
            fuse_hidden_orphans=[
                item for item in result.fuse_hidden_orphans if item.classification.value in allowed
            ],
            metadata={**result.metadata, "classificationFilter": sorted(allowed)},
            recommendations=result.recommendations,
        )

    def _preview_result(
        self,
        settings: AppSettings,
        *,
        scan_result: CatalogRemediationScanResult,
        finding_kind: CatalogRemediationFindingKind,
        action_kind: CatalogRemediationActionKind,
        selected_items: list[dict[str, object]],
        selected_ids: list[str],
        scope_key: str,
        select_all: bool,
    ) -> CatalogRemediationPreviewResult:
        scope = {
            "domain": "consistency.catalog_remediation",
            "action": "preview",
            "finding_kind": finding_kind.value,
            "action_kind": action_kind.value,
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
                    "action_kind": action_kind.value,
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
            action_kind=action_kind,
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
        state: CatalogConsistencyState,
    ) -> list[BrokenDbOriginalFinding]:
        resolver = ImmichStoragePathResolver(settings)
        uploads_root = settings.immich_uploads_path
        if uploads_root is None:
            return []
        uploads_files_by_relative = {
            str(row["relative_path"]): row
            for row in state.latest_files
            if str(row.get("root_slug")) == SOURCE_ROOT_SLUG
        }
        files_by_name: dict[str, list[dict[str, object]]] = {}
        for row in state.latest_files:
            file_name = str(row.get("file_name") or "")
            if file_name:
                files_by_name.setdefault(file_name, []).append(row)

        findings: list[BrokenDbOriginalFinding] = []
        handled_assets: set[str] = set()
        for asset in state.asset_rows:
            asset_id = str(asset["id"])
            original_path = truthy_path(asset.get("originalPath"))
            if original_path is None:
                continue
            resolved_original = resolver.resolve(original_path)
            if resolved_original is None or resolved_original.root_slug != SOURCE_ROOT_SLUG:
                continue
            normalized_db_path = self._normalize_path_text(original_path)
            normalized_canonical_path = self._normalize_path_text(
                str(resolved_original.absolute_path)
            )
            canonical_row = uploads_files_by_relative.get(resolved_original.relative_path)
            if canonical_row is not None and normalized_db_path != normalized_canonical_path:
                findings.append(
                    self._build_located_broken_db_finding(
                        asset=asset,
                        expected_relative_path=resolved_original.relative_path,
                        expected_database_path=original_path,
                        expected_absolute_path=str(resolved_original.absolute_path),
                        located_file=_LocatedFile(
                            root_slug=SOURCE_ROOT_SLUG,
                            relative_path=resolved_original.relative_path,
                            absolute_path=str(resolved_original.absolute_path),
                            file_name=str(canonical_row["file_name"]),
                            size_bytes=int(canonical_row["size_bytes"]),
                        ),
                    )
                )
                handled_assets.add(asset_id)

        for row in state.db_missing_rows:
            asset_id = str(row["asset_id"])
            if asset_id in handled_assets:
                continue
            asset = next((item for item in state.asset_rows if str(item["id"]) == asset_id), None)
            if asset is None:
                continue
            asset_name = str(asset.get("originalFileName") or "").strip()
            try:
                located = self._search_for_relocated_file(
                    settings=settings,
                    files_by_name=files_by_name,
                    asset_name=asset_name,
                    expected_relative_path=str(row["relative_path"]),
                )
                if located is None:
                    findings.append(
                        BrokenDbOriginalFinding(
                            finding_id=f"broken-db-original:{asset_id}",
                            kind=CatalogRemediationFindingKind.BROKEN_DB_ORIGINAL,
                            asset_id=asset_id,
                            asset_name=asset_name or None,
                            asset_type=str(asset.get("type") or "") or None,
                            classification=BrokenDbOriginalClassification.MISSING_CONFIRMED,
                            expected_database_path=str(row["database_path"]),
                            expected_relative_path=str(row["relative_path"]),
                            expected_absolute_path=str(uploads_root / str(row["relative_path"])),
                            found_root_slug=None,
                            found_relative_path=None,
                            found_absolute_path=None,
                            found_size_bytes=None,
                            expected_size_bytes=None,
                            checksum_value=self._asset_checksum_value(asset),
                            checksum_algorithm=self._asset_checksum_algorithm(asset),
                            checksum_match=None,
                            eligible_actions=(CatalogRemediationActionKind.BROKEN_DB_CLEANUP,),
                            action_reason=(
                                "The expected storage path is absent and no "
                                "candidate file was found "
                                "in the current cached storage inventory."
                            ),
                            message=(
                                "Expected storage path is missing and the cached storage inventory "
                                "found no relocation candidate."
                            ),
                        )
                    )
                    continue
                findings.append(
                    self._build_located_broken_db_finding(
                        asset=asset,
                        expected_relative_path=str(row["relative_path"]),
                        expected_database_path=str(row["database_path"]),
                        expected_absolute_path=str(uploads_root / str(row["relative_path"])),
                        located_file=located,
                    )
                )
            except Exception as exc:
                findings.append(
                    BrokenDbOriginalFinding(
                        finding_id=f"broken-db-original:{asset_id}",
                        kind=CatalogRemediationFindingKind.BROKEN_DB_ORIGINAL,
                        asset_id=asset_id,
                        asset_name=asset_name or None,
                        asset_type=str(asset.get("type") or "") or None,
                        classification=BrokenDbOriginalClassification.UNRESOLVED_SEARCH_ERROR,
                        expected_database_path=str(row["database_path"]),
                        expected_relative_path=str(row["relative_path"]),
                        expected_absolute_path=str(uploads_root / str(row["relative_path"])),
                        found_root_slug=None,
                        found_relative_path=None,
                        found_absolute_path=None,
                        found_size_bytes=None,
                        expected_size_bytes=None,
                        checksum_value=self._asset_checksum_value(asset),
                        checksum_algorithm=self._asset_checksum_algorithm(asset),
                        checksum_match=None,
                        eligible_actions=(),
                        action_reason="Relocation search did not complete safely.",
                        search_error=str(exc),
                        message="Relocation search failed and the row remains inspect-only.",
                    )
                )
        return findings

    def _build_located_broken_db_finding(
        self,
        *,
        asset: dict[str, object],
        expected_relative_path: str,
        expected_database_path: str,
        expected_absolute_path: str,
        located_file: _LocatedFile,
    ) -> BrokenDbOriginalFinding:
        checksum_value = self._asset_checksum_value(asset)
        checksum_algorithm = self._asset_checksum_algorithm(asset)
        checksum_match = None
        if checksum_value and checksum_algorithm:
            checksum_match = self._verify_file_checksum(
                path=Path(located_file.absolute_path),
                checksum_value=checksum_value,
                checksum_algorithm=checksum_algorithm,
            )
        classification = BrokenDbOriginalClassification.FOUND_ELSEWHERE
        eligible_actions: tuple[CatalogRemediationActionKind, ...] = ()
        action_reason = (
            "A candidate file was found elsewhere in storage. "
            "This row remains inspect-only by default."
        )
        message = (
            "Expected storage path is missing, but a candidate file was found "
            "elsewhere in the cached storage inventory."
        )
        if checksum_match is True and located_file.root_slug == SOURCE_ROOT_SLUG:
            classification = BrokenDbOriginalClassification.FOUND_WITH_HASH_MATCH
            eligible_actions = (CatalogRemediationActionKind.BROKEN_DB_PATH_FIX,)
            action_reason = (
                "The candidate file matches the DB checksum and can be used "
                "for an explicit DB path fix."
            )
            message = (
                "A relocated file was found and its checksum matches the DB checksum. "
                "This row is eligible for explicit path correction."
            )
        elif checksum_match is False:
            action_reason = (
                "A candidate file was found, but its checksum does not match the DB checksum."
            )
        elif checksum_value and checksum_algorithm is None:
            action_reason = (
                "A candidate file was found, but the DB checksum format is "
                "not supported for auto-verification."
            )
        return BrokenDbOriginalFinding(
            finding_id=f"broken-db-original:{asset['id']}",
            kind=CatalogRemediationFindingKind.BROKEN_DB_ORIGINAL,
            asset_id=str(asset["id"]),
            asset_name=truthy_path(asset.get("originalFileName")),
            asset_type=truthy_path(asset.get("type")),
            classification=classification,
            expected_database_path=expected_database_path,
            expected_relative_path=expected_relative_path,
            expected_absolute_path=expected_absolute_path,
            found_root_slug=located_file.root_slug,
            found_relative_path=located_file.relative_path,
            found_absolute_path=located_file.absolute_path,
            found_size_bytes=located_file.size_bytes,
            expected_size_bytes=None,
            checksum_value=checksum_value,
            checksum_algorithm=checksum_algorithm,
            checksum_match=checksum_match,
            eligible_actions=eligible_actions,
            action_reason=action_reason,
            message=message,
        )

    def _build_zero_byte_findings(
        self,
        settings: AppSettings,
        *,
        state: CatalogConsistencyState,
    ) -> list[ZeroByteFinding]:
        asset_by_id = {str(asset["id"]): asset for asset in state.asset_rows}
        original_asset_by_relative = {
            relative_path: asset_id for asset_id, relative_path in state.original_by_asset.items()
        }
        derivative_asset_by_key = self._build_derivative_asset_index(settings, state=state)
        findings: list[ZeroByteFinding] = []
        for row in state.zero_byte_rows:
            root_slug = str(row["root_slug"])
            relative_path = str(row["relative_path"])
            file_name = str(row["file_name"])
            if file_name == ".immich" or file_name.startswith(".fuse_hidden"):
                continue
            absolute_path = self._absolute_path_for(
                settings,
                root_slug=root_slug,
                relative_path=relative_path,
            )
            if absolute_path is None:
                continue

            if root_slug == SOURCE_ROOT_SLUG:
                asset_id = original_asset_by_relative.get(relative_path)
                asset = asset_by_id.get(asset_id) if asset_id is not None else None
                if asset is not None:
                    findings.append(
                        ZeroByteFinding(
                            finding_id=f"zero-byte:{root_slug}:{relative_path}",
                            kind=CatalogRemediationFindingKind.ZERO_BYTE_FILE,
                            root_slug=root_slug,
                            relative_path=relative_path,
                            absolute_path=str(absolute_path),
                            file_name=file_name,
                            size_bytes=int(row["size_bytes"]),
                            classification=ZeroByteClassification.ZERO_BYTE_UPLOAD_CRITICAL,
                            asset_id=asset_id,
                            asset_name=truthy_path(asset.get("originalFileName")),
                            original_relative_path=relative_path,
                            eligible_actions=(),
                            action_reason=(
                                "The zero-byte upload is referenced by the DB "
                                "as the original file."
                            ),
                            message=(
                                "The original upload is zero bytes and must "
                                "not be auto-deleted."
                            ),
                        )
                    )
                    continue
                findings.append(
                    ZeroByteFinding(
                        finding_id=f"zero-byte:{root_slug}:{relative_path}",
                        kind=CatalogRemediationFindingKind.ZERO_BYTE_FILE,
                        root_slug=root_slug,
                        relative_path=relative_path,
                        absolute_path=str(absolute_path),
                        file_name=file_name,
                        size_bytes=int(row["size_bytes"]),
                        classification=ZeroByteClassification.ZERO_BYTE_UPLOAD_ORPHAN,
                        asset_id=None,
                        asset_name=None,
                        original_relative_path=None,
                        eligible_actions=(CatalogRemediationActionKind.ZERO_BYTE_DELETE,),
                        action_reason="The zero-byte upload has no DB original reference.",
                        message=(
                            "The zero-byte upload is an orphan storage artifact "
                            "and can be deleted."
                        ),
                    )
                )
                continue

            if root_slug not in {"thumbs", "video"}:
                continue

            asset_id = derivative_asset_by_key.get((root_slug, relative_path))
            asset = asset_by_id.get(asset_id) if asset_id is not None else None
            if asset is None:
                continue
            original_relative_path = state.original_by_asset.get(asset_id)
            if original_relative_path is None or original_relative_path not in state.uploads_index:
                continue
            findings.append(
                ZeroByteFinding(
                    finding_id=f"zero-byte:{root_slug}:{relative_path}",
                    kind=CatalogRemediationFindingKind.ZERO_BYTE_FILE,
                    root_slug=root_slug,
                    relative_path=relative_path,
                    absolute_path=str(absolute_path),
                    file_name=file_name,
                    size_bytes=int(row["size_bytes"]),
                    classification=(
                        ZeroByteClassification.ZERO_BYTE_VIDEO_DERIVATIVE
                        if root_slug == "video"
                        else ZeroByteClassification.ZERO_BYTE_THUMB_DERIVATIVE
                    ),
                    asset_id=asset_id,
                    asset_name=truthy_path(asset.get("originalFileName")),
                    original_relative_path=original_relative_path,
                    eligible_actions=(CatalogRemediationActionKind.ZERO_BYTE_DELETE,),
                    action_reason=(
                        "The zero-byte derivative is linked to an asset whose "
                        "original upload still exists."
                    ),
                    message=(
                        "The derivative is zero bytes and can be deleted so "
                        "it may be regenerated later."
                    ),
                )
            )
        return findings

    def _build_derivative_asset_index(
        self,
        settings: AppSettings,
        *,
        state: CatalogConsistencyState,
    ) -> dict[tuple[str, str], str]:
        resolver = ImmichStoragePathResolver(settings)
        index: dict[tuple[str, str], str] = {}
        for asset in state.asset_rows:
            asset_id = str(asset["id"])
            encoded_video_path = truthy_path(asset.get("encodedVideoPath"))
            if encoded_video_path:
                resolved_video = resolver.resolve(encoded_video_path)
                if resolved_video is not None:
                    index[(resolved_video.root_slug, resolved_video.relative_path)] = asset_id
        for derivative in state.asset_file_rows:
            asset_id = str(derivative["assetId"])
            path_text = truthy_path(derivative.get("path"))
            if path_text is None:
                continue
            resolved = resolver.resolve(path_text)
            if resolved is None:
                continue
            index[(resolved.root_slug, resolved.relative_path)] = asset_id
        return index

    def _build_fuse_hidden_findings(
        self,
        settings: AppSettings,
        *,
        state: CatalogConsistencyState,
    ) -> list[FuseHiddenOrphanFinding]:
        uploads_root = settings.immich_uploads_path
        if uploads_root is None:
            return []
        findings: list[FuseHiddenOrphanFinding] = []
        for row in state.storage_missing_rows:
            file_name = str(row["file_name"])
            if file_name == ".immich" or not file_name.startswith(".fuse_hidden"):
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
                        eligible_actions=(),
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
                        eligible_actions=(CatalogRemediationActionKind.FUSE_HIDDEN_DELETE,),
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
                    eligible_actions=(),
                    action_reason="The in-use check was unavailable or failed.",
                    in_use_check_tool=tool,
                    in_use_check_reason=reason,
                    message="The in-use check could not be completed safely.",
                )
            )
        return findings

    def _search_for_relocated_file(
        self,
        *,
        settings: AppSettings,
        files_by_name: dict[str, list[dict[str, object]]],
        asset_name: str,
        expected_relative_path: str,
    ) -> _LocatedFile | None:
        if not asset_name:
            return None
        matches = files_by_name.get(asset_name, [])
        for item in matches:
            relative_path = str(item["relative_path"])
            root_slug = str(item["root_slug"])
            if root_slug == SOURCE_ROOT_SLUG and relative_path == expected_relative_path:
                continue
            return _LocatedFile(
                root_slug=root_slug,
                relative_path=relative_path,
                absolute_path=str(
                    self._absolute_path_for(
                        settings,
                        root_slug=root_slug,
                        relative_path=relative_path,
                    )
                    or Path(root_slug) / relative_path
                ),
                file_name=str(item["file_name"]),
                size_bytes=int(item["size_bytes"]),
            )
        return None

    def _select_broken_db_originals(
        self,
        *,
        findings: list[BrokenDbOriginalFinding],
        asset_ids: tuple[str, ...],
        select_all: bool,
        action_kind: CatalogRemediationActionKind,
    ) -> list[BrokenDbOriginalFinding]:
        selected_ids = set(asset_ids)
        return [
            finding
            for finding in findings
            if finding.supports_action(action_kind)
            and (select_all or finding.asset_id in selected_ids)
        ]

    def _select_zero_byte_findings(
        self,
        *,
        findings: list[ZeroByteFinding],
        finding_ids: tuple[str, ...],
        select_all: bool,
    ) -> list[ZeroByteFinding]:
        selected_ids = set(finding_ids)
        return [
            finding
            for finding in findings
            if finding.supports_action(CatalogRemediationActionKind.ZERO_BYTE_DELETE)
            and (select_all or finding.finding_id in selected_ids)
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
            if finding.supports_action(CatalogRemediationActionKind.FUSE_HIDDEN_DELETE)
            and (select_all or finding.finding_id in selected_ids)
        ]

    def _apply_broken_db_cleanup(
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
            items.append(
                self._map_missing_asset_operation(
                    finding.finding_id,
                    result,
                    action_kind=CatalogRemediationActionKind.BROKEN_DB_CLEANUP,
                )
            )
        return items

    def _apply_broken_db_path_fix(
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
        items: list[CatalogRemediationOperationItem] = []
        for finding in findings:
            target_path = truthy_path(finding.found_absolute_path)
            if target_path is None:
                items.append(
                    CatalogRemediationOperationItem(
                        finding_id=finding.finding_id,
                        kind=CatalogRemediationFindingKind.BROKEN_DB_ORIGINAL,
                        action_kind=CatalogRemediationActionKind.BROKEN_DB_PATH_FIX,
                        target_id=finding.asset_id,
                        status=CatalogRemediationOperationStatus.SKIPPED,
                        message="No target path is available for DB path correction.",
                    )
                )
                continue
            try:
                update_row = self.postgres.update_asset_original_path(
                    dsn,
                    timeout,
                    asset_id=finding.asset_id,
                    new_original_path=target_path,
                )
                self._record_db_path_fix_journal(
                    settings,
                    repair_run=repair_run,
                    finding=finding,
                    old_original_path=str(update_row["oldOriginalPath"]),
                    new_original_path=str(update_row["newOriginalPath"]),
                )
                items.append(
                    CatalogRemediationOperationItem(
                        finding_id=finding.finding_id,
                        kind=CatalogRemediationFindingKind.BROKEN_DB_ORIGINAL,
                        action_kind=CatalogRemediationActionKind.BROKEN_DB_PATH_FIX,
                        target_id=finding.asset_id,
                        status=CatalogRemediationOperationStatus.APPLIED,
                        message="Asset originalPath was updated to the verified storage path.",
                        details={
                            "oldOriginalPath": update_row["oldOriginalPath"],
                            "newOriginalPath": update_row["newOriginalPath"],
                        },
                    )
                )
            except Exception as exc:
                items.append(
                    CatalogRemediationOperationItem(
                        finding_id=finding.finding_id,
                        kind=CatalogRemediationFindingKind.BROKEN_DB_ORIGINAL,
                        action_kind=CatalogRemediationActionKind.BROKEN_DB_PATH_FIX,
                        target_id=finding.asset_id,
                        status=CatalogRemediationOperationStatus.FAILED,
                        message=f"DB path correction failed: {exc}",
                    )
                )
        return items

    def _apply_zero_byte_findings(
        self,
        settings: AppSettings,
        *,
        repair_run: RepairRun,
        findings: list[ZeroByteFinding],
    ) -> list[CatalogRemediationOperationItem]:
        items: list[CatalogRemediationOperationItem] = []
        for finding in findings:
            target_path = Path(finding.absolute_path)
            root_path = self._root_path_for(settings, root_slug=finding.root_slug)
            if root_path is None or not self.filesystem.is_child_path(root_path, target_path):
                items.append(
                    CatalogRemediationOperationItem(
                        finding_id=finding.finding_id,
                        kind=CatalogRemediationFindingKind.ZERO_BYTE_FILE,
                        action_kind=CatalogRemediationActionKind.ZERO_BYTE_DELETE,
                        target_id=finding.relative_path,
                        status=CatalogRemediationOperationStatus.SKIPPED,
                        message=(
                            "Target path is outside the configured storage root "
                            "and was not touched."
                        ),
                    )
                )
                continue
            if not self.filesystem.path_exists(target_path):
                items.append(
                    CatalogRemediationOperationItem(
                        finding_id=finding.finding_id,
                        kind=CatalogRemediationFindingKind.ZERO_BYTE_FILE,
                        action_kind=CatalogRemediationActionKind.ZERO_BYTE_DELETE,
                        target_id=finding.relative_path,
                        status=CatalogRemediationOperationStatus.ALREADY_REMOVED,
                        message="Zero-byte file is already absent from storage.",
                    )
                )
                continue
            try:
                self.filesystem.delete_file(target_path)
                self._record_storage_delete_journal(
                    settings,
                    repair_run=repair_run,
                    finding_kind=CatalogRemediationFindingKind.ZERO_BYTE_FILE,
                    action_kind=CatalogRemediationActionKind.ZERO_BYTE_DELETE,
                    target_id=finding.relative_path,
                    absolute_path=finding.absolute_path,
                    classification=finding.classification.value,
                )
                items.append(
                    CatalogRemediationOperationItem(
                        finding_id=finding.finding_id,
                        kind=CatalogRemediationFindingKind.ZERO_BYTE_FILE,
                        action_kind=CatalogRemediationActionKind.ZERO_BYTE_DELETE,
                        target_id=finding.relative_path,
                        status=CatalogRemediationOperationStatus.APPLIED,
                        message="Zero-byte file was deleted from storage.",
                        details={"absolute_path": finding.absolute_path},
                    )
                )
            except Exception as exc:
                items.append(
                    CatalogRemediationOperationItem(
                        finding_id=finding.finding_id,
                        kind=CatalogRemediationFindingKind.ZERO_BYTE_FILE,
                        action_kind=CatalogRemediationActionKind.ZERO_BYTE_DELETE,
                        target_id=finding.relative_path,
                        status=CatalogRemediationOperationStatus.FAILED,
                        message=f"Deletion failed: {exc}",
                    )
                )
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
                items.append(
                    CatalogRemediationOperationItem(
                        finding_id=finding.finding_id,
                        kind=CatalogRemediationFindingKind.FUSE_HIDDEN_ORPHAN,
                        action_kind=CatalogRemediationActionKind.FUSE_HIDDEN_DELETE,
                        target_id=finding.relative_path,
                        status=CatalogRemediationOperationStatus.SKIPPED,
                        message="Target path is outside the uploads root and was not touched.",
                    )
                )
                continue
            if not self.filesystem.path_exists(target_path):
                items.append(
                    CatalogRemediationOperationItem(
                        finding_id=finding.finding_id,
                        kind=CatalogRemediationFindingKind.FUSE_HIDDEN_ORPHAN,
                        action_kind=CatalogRemediationActionKind.FUSE_HIDDEN_DELETE,
                        target_id=finding.relative_path,
                        status=CatalogRemediationOperationStatus.ALREADY_REMOVED,
                        message="Artifact is already absent from storage.",
                    )
                )
                continue
            try:
                self.filesystem.delete_file(target_path)
                self._record_storage_delete_journal(
                    settings,
                    repair_run=repair_run,
                    finding_kind=CatalogRemediationFindingKind.FUSE_HIDDEN_ORPHAN,
                    action_kind=CatalogRemediationActionKind.FUSE_HIDDEN_DELETE,
                    target_id=finding.relative_path,
                    absolute_path=finding.absolute_path,
                    classification=finding.classification.value,
                )
                items.append(
                    CatalogRemediationOperationItem(
                        finding_id=finding.finding_id,
                        kind=CatalogRemediationFindingKind.FUSE_HIDDEN_ORPHAN,
                        action_kind=CatalogRemediationActionKind.FUSE_HIDDEN_DELETE,
                        target_id=finding.relative_path,
                        status=CatalogRemediationOperationStatus.APPLIED,
                        message="Artifact was deleted from storage.",
                        details={"absolute_path": finding.absolute_path},
                    )
                )
            except Exception as exc:
                items.append(
                    CatalogRemediationOperationItem(
                        finding_id=finding.finding_id,
                        kind=CatalogRemediationFindingKind.FUSE_HIDDEN_ORPHAN,
                        action_kind=CatalogRemediationActionKind.FUSE_HIDDEN_DELETE,
                        target_id=finding.relative_path,
                        status=CatalogRemediationOperationStatus.FAILED,
                        message=f"Deletion failed: {exc}",
                    )
                )
        return items

    def _map_missing_asset_operation(
        self,
        finding_id: str,
        result: MissingAssetOperationItem,
        *,
        action_kind: CatalogRemediationActionKind,
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
            action_kind=action_kind,
            target_id=result.asset_id,
            status=mapped_status,
            message=result.message,
            details=result.details,
        )

    def _record_db_path_fix_journal(
        self,
        settings: AppSettings,
        *,
        repair_run: RepairRun,
        finding: BrokenDbOriginalFinding,
        old_original_path: str,
        new_original_path: str,
    ) -> None:
        entry = RepairJournalEntry(
            entry_id=uuid4().hex,
            repair_run_id=repair_run.repair_run_id,
            operation_type="fix_asset_original_path",
            status=RepairJournalEntryStatus.APPLIED,
            asset_id=finding.asset_id,
            table="public.asset",
            old_db_values={"originalPath": old_original_path},
            new_db_values={"originalPath": new_original_path},
            original_path=old_original_path,
            quarantine_path=None,
            undo_type=UndoType.RESTORE_DB_VALUES,
            undo_payload={
                "table": "public.asset",
                "asset_id": finding.asset_id,
                "old_values": {"originalPath": old_original_path},
                "new_values": {"originalPath": new_original_path},
            },
            error_details=None,
        )
        self.repair_store.append_journal_entry(settings, entry)

    def _record_storage_delete_journal(
        self,
        settings: AppSettings,
        *,
        repair_run: RepairRun,
        finding_kind: CatalogRemediationFindingKind,
        action_kind: CatalogRemediationActionKind,
        target_id: str,
        absolute_path: str,
        classification: str,
    ) -> None:
        entry = RepairJournalEntry(
            entry_id=uuid4().hex,
            repair_run_id=repair_run.repair_run_id,
            operation_type=action_kind.value,
            status=RepairJournalEntryStatus.APPLIED,
            asset_id=None,
            table=None,
            old_db_values=None,
            new_db_values={
                "finding_kind": finding_kind.value,
                "target_id": target_id,
                "absolute_path": absolute_path,
                "classification": classification,
            },
            original_path=absolute_path,
            quarantine_path=None,
            undo_type=UndoType.NONE,
            undo_payload={},
            error_details=None,
        )
        self.repair_store.append_journal_entry(settings, entry)

    def _asset_checksum_value(self, asset: dict[str, object]) -> str | None:
        for key in ("checksum", "originalChecksum"):
            value = truthy_path(asset.get(key))
            if value is not None:
                return value
        return None

    def _asset_checksum_algorithm(self, asset: dict[str, object]) -> str | None:
        explicit_algorithm = truthy_path(asset.get("checksumAlgorithm"))
        if explicit_algorithm is not None:
            return explicit_algorithm.lower()
        checksum_value = self._asset_checksum_value(asset)
        if checksum_value is None:
            return None
        normalized = checksum_value.lower()
        if normalized.startswith("\\x"):
            normalized = normalized[2:]
        if len(normalized) == 64 and all(char in "0123456789abcdef" for char in normalized):
            return "sha256"
        if len(normalized) == 40 and all(char in "0123456789abcdef" for char in normalized):
            return "sha1"
        return None

    def _verify_file_checksum(
        self,
        *,
        path: Path,
        checksum_value: str,
        checksum_algorithm: str,
    ) -> bool | None:
        if not self.filesystem.path_exists(path):
            return None
        normalized = checksum_value.strip().lower()
        if normalized.startswith("\\x"):
            normalized = normalized[2:]
        try:
            actual = self.filesystem.compute_file_checksum(path, algorithm=checksum_algorithm)
        except Exception:
            return None
        return actual.lower() == normalized

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

    def _normalize_path_text(self, value: str) -> str:
        return value.replace("\\", "/")

    def _root_path_for(self, settings: AppSettings, *, root_slug: str) -> Path | None:
        return {
            "uploads": settings.immich_uploads_path,
            "thumbs": settings.immich_thumbs_path,
            "profile": settings.immich_profile_path,
            "video": settings.immich_video_path,
            "library": settings.immich_library_root,
        }.get(root_slug)

    def _absolute_path_for(
        self,
        settings: AppSettings,
        *,
        root_slug: str,
        relative_path: str,
    ) -> Path | None:
        root_path = self._root_path_for(settings, root_slug=root_slug)
        if root_path is None:
            return None
        return root_path / relative_path
