<template>
  <section class="panel catalog-remediation-panel">
    <div class="settings-section__header">
      <div>
        <h3>Catalog findings workspace</h3>
        <p>
          Review grouped snapshot findings, stage explicit operator actions, and
          keep blocked rows visible with the exact reason they are not eligible.
        </p>
      </div>
      <StatusTag :status="panelStatus" />
    </div>

    <p class="health-card__summary">
      {{ workspaceSummary }}
    </p>
    <p class="health-card__details">
      No destructive action runs automatically from this page. Actions below only
      stage explicit operator intent.
    </p>
    <p v-if="remediationSupportMessage" class="health-card__details">
      {{ remediationSupportMessage }}
    </p>

    <section class="catalog-remediation-toolbar">
      <div class="runtime-actions">
        <button
          type="button"
          class="runtime-action runtime-action--secondary"
          :disabled="!selectableRows.length"
          @click="selectAllVisible()"
        >
          Select all visible
        </button>
        <button
          type="button"
          class="runtime-action runtime-action--secondary"
          :disabled="!selectedRowIds.length && !hasStagedActions"
          @click="clearSelectionAndActions()"
        >
          Clear selection
        </button>
        <button
          type="button"
          class="runtime-action runtime-action--secondary"
          :disabled="consistencyStore.isLoadingRemediation || !consistencyStore.catalogReport"
          @click="void refreshPanel()"
        >
          {{
            consistencyStore.isLoadingRemediation
              ? "Refreshing..."
              : "Refresh detailed findings"
          }}
        </button>
      </div>

      <div class="runtime-actions">
        <button
          v-for="action in bulkActions"
          :key="action.id"
          type="button"
          class="runtime-action"
          :disabled="action.count === 0"
          :title="action.helpText"
          @click="applyBulkAction(action.id)"
        >
          {{ action.label }} ({{ action.count }})
        </button>
      </div>
    </section>

    <section class="catalog-remediation-stage" v-if="stagedActionEntries.length">
      <div class="settings-section__header">
        <div>
          <h4>Staged actions</h4>
          <p>These actions are selected intentionally but not executed from this page.</p>
        </div>
      </div>
      <div class="catalog-remediation-stage__chips">
        <span
          v-for="entry in stagedActionEntries"
          :key="entry.label"
          class="consistency-chip consistency-chip--finding-found_with_hash_match"
        >
          {{ entry.label }}: {{ entry.count }}
        </span>
      </div>
    </section>

    <EmptyState
      v-if="!findingGroups.length"
      title="No grouped findings available"
      message="Load or refresh a catalog consistency snapshot to review grouped findings here."
    />

    <article
      v-for="group in findingGroups"
      :key="group.key"
      class="catalog-remediation-group"
    >
      <div class="settings-section__header">
        <div>
          <h4>{{ group.title }}</h4>
          <p>{{ group.description }}</p>
        </div>
        <div class="catalog-remediation-group__meta">
          <StatusTag :status="group.status" />
          <span class="catalog-remediation-group__count">{{ group.rows.length }}</span>
        </div>
      </div>

      <div class="catalog-remediation-table-wrapper">
        <table class="catalog-table">
          <thead>
            <tr>
              <th class="catalog-remediation-table__select">Select</th>
              <th>Finding</th>
              <th>Classification</th>
              <th>Paths / context</th>
              <th>Status</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in group.rows"
              :key="row.id"
              :class="{ 'catalog-remediation-row--staged': Boolean(stagedActionByRowId[row.id]) }"
            >
              <td class="catalog-remediation-table__select">
                <input
                  type="checkbox"
                  :checked="selectedRowIds.includes(row.id)"
                  :disabled="!row.selectionEligible"
                  :aria-label="`Select finding ${row.id}`"
                  @change="toggleSelection(row.id, ($event.target as HTMLInputElement).checked)"
                />
              </td>
              <td>
                <div class="catalog-remediation-cell">
                  <strong>{{ row.title }}</strong>
                  <small class="catalog-remediation-muted">{{ row.subtitle }}</small>
                </div>
              </td>
              <td>
                <div class="catalog-remediation-cell">
                  <span :class="row.badgeClass" class="consistency-chip">
                    {{ row.badgeLabel }}
                  </span>
                  <small class="catalog-remediation-muted">{{ row.message }}</small>
                </div>
              </td>
              <td class="catalog-remediation-mono">
                <div class="catalog-remediation-cell">
                  <span v-for="detail in row.pathDetails" :key="detail">{{ detail }}</span>
                </div>
              </td>
              <td>
                <div class="catalog-remediation-cell">
                  <span v-if="row.blockedReason" class="catalog-remediation-blocked">
                    {{ row.blockedReason }}
                  </span>
                  <span v-else>{{ row.statusReason }}</span>
                  <small
                    v-if="stagedActionByRowId[row.id]"
                    class="catalog-remediation-muted"
                  >
                    Staged: {{ bulkActionLabel(stagedActionByRowId[row.id]) }}
                  </small>
                </div>
              </td>
              <td>
                <div class="runtime-actions catalog-remediation-row-actions">
                  <button
                    v-for="action in row.actions"
                    :key="`${row.id}:${action.id}`"
                    type="button"
                    class="runtime-action runtime-action--secondary"
                    :disabled="Boolean(action.disabledReason)"
                    :title="action.disabledReason ?? action.helpText"
                    @click="stageRowAction(row.id, action)"
                  >
                    {{ action.label }}
                  </button>
                  <span
                    v-if="!row.actions.length"
                    class="catalog-remediation-muted"
                  >
                    No explicit action available
                  </span>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </article>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import EmptyState from "@/components/common/EmptyState.vue";
import StatusTag from "@/components/common/StatusTag.vue";
import { useConsistencyStore } from "@/stores/consistency";
import type { CatalogValidationReport } from "@/api/types/catalog";
import type {
  BrokenDbOriginalFinding,
  FuseHiddenOrphanFinding,
  ZeroByteFinding,
} from "@/api/types/consistency";

type HealthTag = "ok" | "warning" | "error" | "unknown";
type BulkActionId = "repair" | "delete" | "quarantine" | "ignore";
type RowActionId =
  | "inspect"
  | "mark_removed"
  | "repair_path"
  | "delete"
  | "quarantine"
  | "ignore";

interface RowActionModel {
  id: RowActionId;
  label: string;
  helpText: string;
  bulkActionId: BulkActionId | null;
  disabledReason: string | null;
}

interface FindingRowModel {
  id: string;
  groupKey: string;
  title: string;
  subtitle: string;
  badgeLabel: string;
  badgeClass: string;
  message: string;
  pathDetails: string[];
  statusReason: string;
  blockedReason: string | null;
  actions: RowActionModel[];
  selectionEligible: boolean;
}

interface FindingGroupModel {
  key: string;
  title: string;
  description: string;
  status: HealthTag;
  rows: FindingRowModel[];
}

interface BulkActionViewModel {
  id: BulkActionId;
  label: string;
  count: number;
  helpText: string;
}

const consistencyStore = useConsistencyStore();
const selectedRowIds = ref<string[]>([]);
const stagedActionByRowId = ref<Record<string, BulkActionId>>({});

function sectionRows(
  report: CatalogValidationReport | null,
  sectionName: string,
): Array<Record<string, unknown>> {
  const section = report?.sections.find((candidate) => candidate.name === sectionName);
  return section ? (section.rows as Array<Record<string, unknown>>) : [];
}

function badgeClass(value: string): string {
  return `consistency-chip--finding-${value}`;
}

function toTitleCase(value: string): string {
  return value.replace(/_/g, " ");
}

function pathLine(label: string, value: string | null | undefined): string {
  return value ? `${label}: ${value}` : `${label}: Unavailable`;
}

function bulkActionLabel(actionId: BulkActionId): string {
  switch (actionId) {
    case "repair":
      return "Repair";
    case "delete":
      return "Delete";
    case "quarantine":
      return "Quarantine";
    case "ignore":
      return "Ignore";
  }
}

function makeRowAction(
  id: RowActionId,
  label: string,
  helpText: string,
  bulkActionId: BulkActionId | null,
  disabledReason: string | null = null,
): RowActionModel {
  return { id, label, helpText, bulkActionId, disabledReason };
}

function brokenDbRow(finding: BrokenDbOriginalFinding): FindingRowModel {
  const blockedReason = finding.action_eligible ? null : finding.action_reason;
  const actions: RowActionModel[] = [makeRowAction("inspect", "Inspect", "Review expected and found paths.", null)];
  if (finding.classification === "missing_confirmed") {
    actions.push(
      makeRowAction(
        "mark_removed",
        "Mark removed",
        "Stage DB cleanup for a confirmed missing original reference.",
        "repair",
      ),
    );
  }
  if (finding.classification === "found_with_hash_match") {
    actions.push(
      makeRowAction(
        "repair_path",
        "Repair path",
        "Stage an explicit DB path correction for a verified relocated original.",
        "repair",
      ),
    );
  }
  return {
    id: finding.finding_id,
    groupKey: "broken-db",
    title: finding.asset_name ?? finding.asset_id,
    subtitle: finding.asset_id,
    badgeLabel: toTitleCase(finding.classification),
    badgeClass: badgeClass(finding.classification),
    message: finding.message,
    pathDetails: [
      pathLine("Expected", finding.expected_database_path),
      pathLine("Found", finding.found_absolute_path),
    ],
    statusReason: finding.action_reason,
    blockedReason,
    actions,
    selectionEligible: actions.some((action) => action.bulkActionId !== null),
  };
}

function fallbackBrokenDbRow(row: Record<string, unknown>): FindingRowModel {
  const assetId = String(row.asset_id ?? "unknown");
  const databasePath = String(row.database_path ?? "Unavailable");
  return {
    id: `fallback-broken:${assetId}`,
    groupKey: "broken-db",
    title: String(row.asset_name ?? assetId),
    subtitle: assetId,
    badgeLabel: "Missing in snapshot",
    badgeClass: badgeClass("missing_confirmed"),
    message: "Detailed remediation classification is unavailable right now.",
    pathDetails: [
      pathLine("Expected", databasePath),
      pathLine("Resolved path", String(row.relative_path ?? "Unavailable")),
    ],
    statusReason: "Inspect only until remediation enrichment loads.",
    blockedReason: "Detailed remediation classification is not loaded.",
    actions: [makeRowAction("inspect", "Inspect", "Review the raw snapshot finding.", null)],
    selectionEligible: false,
  };
}

function storageMissingRow(row: Record<string, unknown>): FindingRowModel {
  const relativePath = String(row.relative_path ?? "Unavailable");
  return {
    id: `storage-missing:${relativePath}`,
    groupKey: "storage-missing",
    title: String(row.file_name ?? relativePath),
    subtitle: String(row.root_slug ?? "uploads"),
    badgeLabel: "Storage orphan",
    badgeClass: badgeClass("found_elsewhere"),
    message: "A storage original exists without a matching DB original reference.",
    pathDetails: [
      pathLine("Relative path", relativePath),
      pathLine("Size", String(row.size_bytes ?? "Unavailable")),
    ],
    statusReason: "Delete, quarantine, or ignore can be staged explicitly.",
    blockedReason: null,
    actions: [
      makeRowAction("delete", "Delete", "Stage deletion for the orphan storage file.", "delete"),
      makeRowAction(
        "quarantine",
        "Quarantine",
        "Stage quarantine review for the orphan storage file.",
        "quarantine",
      ),
      makeRowAction("ignore", "Ignore", "Stage an explicit ignore decision.", "ignore"),
    ],
    selectionEligible: true,
  };
}

function orphanDerivativeRow(row: Record<string, unknown>): FindingRowModel {
  const relativePath = String(row.relative_path ?? "Unavailable");
  return {
    id: `orphan-derivative:${relativePath}`,
    groupKey: "orphan-derivative",
    title: String(row.derivative_type ?? "orphan"),
    subtitle: String(row.asset_id ?? "No asset"),
    badgeLabel: "Orphan derivative",
    badgeClass: badgeClass("deletable_orphan"),
    message: "A derivative file exists without the original file.",
    pathDetails: [
      pathLine("Relative path", relativePath),
      pathLine("Original", String(row.original_relative_path ?? "Unavailable")),
    ],
    statusReason: "Delete, quarantine, or ignore can be staged explicitly.",
    blockedReason: null,
    actions: [
      makeRowAction("delete", "Delete", "Stage deletion for the orphan derivative.", "delete"),
      makeRowAction(
        "quarantine",
        "Quarantine",
        "Stage quarantine review for the orphan derivative.",
        "quarantine",
      ),
      makeRowAction("ignore", "Ignore", "Stage an explicit ignore decision.", "ignore"),
    ],
    selectionEligible: true,
  };
}

function zeroByteRow(finding: ZeroByteFinding): FindingRowModel {
  const canDelete =
    finding.classification === "zero_byte_upload_orphan" ||
    finding.classification === "zero_byte_video_derivative" ||
    finding.classification === "zero_byte_thumb_derivative";
  return {
    id: finding.finding_id,
    groupKey: "zero-byte",
    title: finding.file_name,
    subtitle: finding.asset_name ?? finding.asset_id ?? finding.root_slug,
    badgeLabel: toTitleCase(finding.classification),
    badgeClass: badgeClass(finding.classification),
    message: finding.message,
    pathDetails: [
      pathLine("Path", finding.absolute_path),
      pathLine("Size", `${finding.size_bytes} B`),
    ],
    statusReason: finding.action_reason,
    blockedReason: canDelete ? null : finding.action_reason,
    actions: canDelete
      ? [makeRowAction("delete", "Delete", "Stage deletion for the zero-byte file.", "delete")]
      : [],
    selectionEligible: canDelete,
  };
}

function fuseHiddenRow(finding: FuseHiddenOrphanFinding): FindingRowModel {
  const actions: RowActionModel[] = [];
  if (finding.classification === "deletable_orphan") {
    actions.push(
      makeRowAction("delete", "Delete", "Stage deletion for the orphan `.fuse_hidden*` file.", "delete"),
    );
  } else if (finding.classification === "blocked_in_use") {
    actions.push(
      makeRowAction("ignore", "Ignore", "Stage an explicit ignore decision for the in-use file.", "ignore"),
    );
  }

  return {
    id: finding.finding_id,
    groupKey: "fuse-hidden",
    title: finding.file_name,
    subtitle: finding.root_slug,
    badgeLabel: toTitleCase(finding.classification),
    badgeClass: badgeClass(finding.classification),
    message: finding.message,
    pathDetails: [
      pathLine("Path", finding.absolute_path),
      pathLine("Check", finding.in_use_check_reason),
    ],
    statusReason: finding.action_reason,
    blockedReason:
      finding.classification === "check_failed" ? finding.action_reason : null,
    actions,
    selectionEligible: actions.some((action) => action.bulkActionId !== null),
  };
}

function unmappedRow(row: Record<string, unknown>): FindingRowModel {
  return {
    id: `unmapped:${String(row.asset_id ?? "unknown")}`,
    groupKey: "path-warning",
    title: String(row.asset_name ?? row.asset_id ?? "Unknown asset"),
    subtitle: String(row.asset_id ?? "unknown"),
    badgeLabel: toTitleCase(String(row.mapping_status ?? "unexpected_root")),
    badgeClass: badgeClass(String(row.mapping_status ?? "unexpected_root")),
    message: "This DB path needs manual inspection before any action is chosen.",
    pathDetails: [
      pathLine("Database path", String(row.database_path ?? "Unavailable")),
      pathLine("Path kind", String(row.path_kind ?? "original")),
    ],
    statusReason: "Inspect only.",
    blockedReason: "No safe action is available from the catalog-only model.",
    actions: [makeRowAction("inspect", "Inspect", "Review the unmapped DB path.", null)],
    selectionEligible: false,
  };
}

const report = computed(() => consistencyStore.catalogReport);
const brokenRows = computed<FindingRowModel[]>(() => {
  if (consistencyStore.brokenDbOriginals.length) {
    return consistencyStore.brokenDbOriginals.map(brokenDbRow);
  }
  return sectionRows(report.value, "DB_ORIGINALS_MISSING_ON_STORAGE").map(fallbackBrokenDbRow);
});
const storageMissingRows = computed<FindingRowModel[]>(() =>
  consistencyStore.storageOriginalsMissingInDb.map(storageMissingRow),
);
const orphanDerivativeRows = computed<FindingRowModel[]>(() =>
  consistencyStore.orphanDerivatives.map(orphanDerivativeRow),
);
const zeroByteRows = computed<FindingRowModel[]>(() =>
  consistencyStore.zeroByteFindings.map(zeroByteRow),
);
const fuseHiddenRows = computed<FindingRowModel[]>(() =>
  consistencyStore.fuseHiddenOrphans.map(fuseHiddenRow),
);
const unmappedRows = computed<FindingRowModel[]>(() =>
  consistencyStore.unmappedDatabasePaths.map(unmappedRow),
);

const findingGroups = computed<FindingGroupModel[]>(() => {
  const groups: FindingGroupModel[] = [
    {
      key: "broken-db",
      title: "DB originals missing in storage",
      description:
        "Broken original references, relocations, and hash-verified path mismatches from the current snapshot.",
      status: brokenRows.value.length ? "warning" : "ok",
      rows: brokenRows.value,
    },
    {
      key: "storage-missing",
      title: "Storage originals missing in DB",
      description:
        "Snapshot files that exist on storage without a matching original DB row.",
      status: storageMissingRows.value.length ? "warning" : "ok",
      rows: storageMissingRows.value,
    },
    {
      key: "orphan-derivative",
      title: "Orphan derivatives",
      description: "Derivative files that remain after the original disappeared.",
      status: orphanDerivativeRows.value.length ? "warning" : "ok",
      rows: orphanDerivativeRows.value,
    },
    {
      key: "zero-byte",
      title: "Zero-byte files",
      description:
        "Zero-byte originals and derivatives split by eligibility and blocked reasons.",
      status: zeroByteRows.value.length ? "warning" : "ok",
      rows: zeroByteRows.value,
    },
    {
      key: "fuse-hidden",
      title: "`.fuse_hidden*` artifacts",
      description:
        "FUSE/Unraid orphan artifacts with explicit delete or ignore decisions.",
      status: fuseHiddenRows.value.length ? "warning" : "ok",
      rows: fuseHiddenRows.value,
    },
    {
      key: "path-warning",
      title: "Path warnings",
      description:
        "DB paths that mapped unclearly and therefore remain inspect-only from the snapshot model.",
      status: unmappedRows.value.length ? "warning" : "ok",
      rows: unmappedRows.value,
    },
  ];
  return groups.filter((group) => group.rows.length > 0);
});

const allRows = computed(() => findingGroups.value.flatMap((group) => group.rows));
const selectableRows = computed(() => allRows.value.filter((row) => row.selectionEligible));
const selectedRows = computed(() =>
  allRows.value.filter((row) => selectedRowIds.value.includes(row.id)),
);
const hasStagedActions = computed(
  () => Object.keys(stagedActionByRowId.value).length > 0,
);
const stagedActionEntries = computed(() => {
  const counts = new Map<BulkActionId, number>();
  for (const actionId of Object.values(stagedActionByRowId.value)) {
    counts.set(actionId, (counts.get(actionId) ?? 0) + 1);
  }
  return Array.from(counts.entries()).map(([actionId, count]) => ({
    label: bulkActionLabel(actionId),
    count,
  }));
});
const bulkActions = computed<BulkActionViewModel[]>(() =>
  (["repair", "delete", "quarantine", "ignore"] as BulkActionId[]).map((actionId) => {
    const count = selectedRows.value.filter((row) =>
      row.actions.some((action) => action.bulkActionId === actionId),
    ).length;
    return {
      id: actionId,
      label: `${bulkActionLabel(actionId)} selected`,
      count,
      helpText:
        count > 0
          ? `Stage ${bulkActionLabel(actionId).toLowerCase()} for ${count} selected rows.`
          : `No selected rows support ${bulkActionLabel(actionId).toLowerCase()}.`,
    };
  }),
);
const workspaceSummary = computed(() => {
  if (consistencyStore.remediationScanResult?.summary) {
    return consistencyStore.remediationScanResult.summary;
  }
  if (report.value?.summary) {
    return report.value.summary;
  }
  return "No catalog-backed findings are loaded yet.";
});
const remediationSupportMessage = computed(() => {
  if (consistencyStore.isLoadingRemediation) {
    return "Detailed remediation classification is loading in the background.";
  }
  if (consistencyStore.remediationError && report.value) {
    return "Detailed remediation classification could not be refreshed. Snapshot findings remain visible without staged execution.";
  }
  return consistencyStore.remediationError;
});
const panelStatus = computed<HealthTag>(() => {
  if (!report.value && !findingGroups.value.length) {
    return "unknown";
  }
  if (consistencyStore.remediationError && !report.value) {
    return "error";
  }
  return findingGroups.value.length ? "warning" : "ok";
});

function toggleSelection(rowId: string, checked: boolean): void {
  selectedRowIds.value = checked
    ? [...new Set([...selectedRowIds.value, rowId])]
    : selectedRowIds.value.filter((value) => value !== rowId);
}

function selectAllVisible(): void {
  selectedRowIds.value = selectableRows.value.map((row) => row.id);
}

function clearSelectionAndActions(): void {
  selectedRowIds.value = [];
  stagedActionByRowId.value = {};
}

function stageRowAction(rowId: string, action: RowActionModel): void {
  if (action.bulkActionId === null || action.disabledReason) {
    return;
  }
  stagedActionByRowId.value = {
    ...stagedActionByRowId.value,
    [rowId]: action.bulkActionId,
  };
}

function applyBulkAction(actionId: BulkActionId): void {
  const next = { ...stagedActionByRowId.value };
  for (const row of selectedRows.value) {
    if (row.actions.some((action) => action.bulkActionId === actionId)) {
      next[row.id] = actionId;
    }
  }
  stagedActionByRowId.value = next;
}

async function refreshPanel(): Promise<void> {
  await consistencyStore.loadRemediation(true);
}
</script>

<style scoped>
.catalog-remediation-panel,
.catalog-remediation-group,
.catalog-remediation-stage {
  display: grid;
  gap: 1rem;
}

.catalog-remediation-toolbar {
  display: grid;
  gap: 0.85rem;
}

.catalog-remediation-table-wrapper {
  overflow-x: auto;
}

.catalog-remediation-table__select {
  width: 4rem;
}

.catalog-remediation-cell {
  display: grid;
  gap: 0.2rem;
}

.catalog-remediation-muted {
  color: #5c6b77;
}

.catalog-remediation-mono {
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
}

.catalog-remediation-row-actions {
  justify-content: start;
}

.catalog-remediation-group__meta {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.catalog-remediation-group__count {
  color: #5c6b77;
  font-weight: 700;
}

.catalog-remediation-blocked {
  color: #8b5b00;
  font-weight: 600;
}

.catalog-remediation-row--staged {
  background: #f8fbfd;
}

.catalog-remediation-stage__chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}
</style>
