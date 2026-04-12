<template>
  <section class="catalog-remediation-panel">
    <section class="panel catalog-remediation-workspace">
      <div class="settings-section__header">
        <div>
          <h3>Catalog findings workspace</h3>
          <p>
            Review findings in smaller server-backed pages, stage explicit operator actions,
            and open `...more info` only for the exact item you want to inspect.
          </p>
        </div>
        <StatusTag :status="panelStatus" />
      </div>

      <section v-if="mode === 'findings'" class="runtime-actions">
        <button
          type="button"
          class="runtime-action"
          :disabled="consistencyStore.isLoadingRemediation || consistencyStore.isRefreshingRemediation"
          @click="void refreshPanel()"
        >
          {{
            consistencyStore.isLoadingRemediation || consistencyStore.isRefreshingRemediation
              ? "Refreshing..."
              : "Refresh detailed findings"
          }}
        </button>
      </section>

      <p class="health-card__summary">{{ workspaceSummary }}</p>
      <p v-if="workspaceDetails" class="health-card__details">{{ workspaceDetails }}</p>
      <p v-if="consistencyStore.lastActionSummary" class="health-card__details">
        {{ consistencyStore.lastActionSummary }}
      </p>
      <p v-if="consistencyStore.actionError" class="runtime-blocking-message">
        {{ consistencyStore.actionError }}
      </p>
      <p v-if="consistencyStore.remediationError" class="runtime-blocking-message">
        {{ consistencyStore.remediationError }}
      </p>
      <p v-if="consistencyStore.ignoredError" class="runtime-blocking-message">
        {{ consistencyStore.ignoredError }}
      </p>
      <p v-if="consistencyStore.quarantineError" class="runtime-blocking-message">
        {{ consistencyStore.quarantineError }}
      </p>
    </section>

    <template v-if="mode === 'findings'">
      <EmptyState
        v-if="!findingGroups.length && !consistencyStore.isLoadingRemediation"
        title="No grouped findings available"
        message="No active catalog findings are currently visible."
      />

      <article
        v-for="group in findingGroups"
        :key="group.key"
        class="panel catalog-remediation-group"
      >
        <div class="settings-section__header">
          <div>
            <h4>{{ group.title }}</h4>
            <p>{{ group.description }}</p>
          </div>
          <div class="catalog-remediation-group__meta">
            <StatusTag :status="group.status" />
            <span class="catalog-remediation-group__count">{{ group.totalCount }}</span>
          </div>
        </div>

        <section class="catalog-remediation-pagination">
          <label class="catalog-remediation-pagination__size">
            <span>Rows</span>
            <select
              :value="pageSizeValue(group.limit)"
              @change="onPageSizeChange(group, ($event.target as HTMLSelectElement).value)"
            >
              <option
                v-for="option in pageSizeOptions"
                :key="option.value"
                :value="String(option.value)"
              >
                {{ option.label }}
              </option>
            </select>
          </label>
          <div class="catalog-remediation-pagination__controls">
            <button
              type="button"
              class="runtime-action runtime-action--secondary"
              :disabled="group.offset === 0 || group.isLoading"
              @click="void changePage(group, 'prev')"
            >
              Previous
            </button>
            <span>{{ pageLabel(group) }}</span>
            <button
              type="button"
              class="runtime-action runtime-action--secondary"
              :disabled="!canGoNext(group) || group.isLoading"
              @click="void changePage(group, 'next')"
            >
              Next
            </button>
          </div>
        </section>

        <section v-if="group.actionableRows.length" class="runtime-actions catalog-remediation-group__actions">
          <button
            v-if="group.supportedActions.includes('delete')"
            type="button"
            class="runtime-action runtime-action--secondary"
            @click="stageGroupAction(group.key, 'delete')"
          >
            Delete visible
          </button>
          <button
            v-if="group.supportedActions.includes('quarantine')"
            type="button"
            class="runtime-action runtime-action--secondary"
            @click="stageGroupAction(group.key, 'quarantine')"
          >
            Quarantine visible
          </button>
          <button
            v-if="group.supportedActions.includes('ignore')"
            type="button"
            class="runtime-action runtime-action--secondary"
            @click="stageGroupAction(group.key, 'ignore')"
          >
            Ignore visible
          </button>
          <button
            v-if="group.supportedActions.includes('ignore')"
            type="button"
            class="runtime-action runtime-action--secondary"
            @click="stageUnstagedIgnore(group.key)"
          >
            Ignore unstaged visible
          </button>
          <button
            type="button"
            class="runtime-action runtime-action--secondary"
            :disabled="!group.stagedCount"
            @click="clearGroupStage(group.key)"
          >
            Clear staged
          </button>
          <button
            type="button"
            class="runtime-action"
            :disabled="!group.stagedCount || consistencyStore.isApplyingAction"
            @click="void performGroupActions(group)"
          >
            Perform staged actions ({{ group.stagedCount }})
          </button>
        </section>

        <p v-if="group.error" class="runtime-blocking-message">{{ group.error }}</p>
        <p v-if="group.isLoading && !group.rows.length" class="health-card__details">
          Loading this card...
        </p>

        <div v-else-if="group.rows.length" class="catalog-remediation-table-wrapper">
          <table class="catalog-table">
            <thead>
              <tr>
                <th>Finding</th>
                <th>Owner</th>
                <th>Classification</th>
                <th>Paths / context</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              <template v-for="row in group.rows" :key="row.id">
                <tr :class="{ 'catalog-remediation-row--staged': Boolean(stagedActionByRowId[row.id]) }">
                  <td>
                    <div class="catalog-remediation-cell">
                      <strong>{{ row.title }}</strong>
                      <small class="catalog-remediation-muted">{{ row.subtitle }}</small>
                    </div>
                  </td>
                  <td>
                    <div class="catalog-remediation-cell">
                      <span>{{ row.ownerLabel ?? "Unknown owner" }}</span>
                      <small class="catalog-remediation-muted">{{ row.ownerHint }}</small>
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
                      <span>{{ row.summaryPath ?? "Unavailable" }}</span>
                      <small class="catalog-remediation-muted">
                        {{ row.summaryContext ?? "No extra context" }}
                      </small>
                    </div>
                  </td>
                  <td>
                    <div class="catalog-remediation-cell">
                      <span v-if="row.blockedReason" class="catalog-remediation-blocked">
                        {{ row.blockedReason }}
                      </span>
                      <span v-else>{{ row.statusReason }}</span>
                      <small v-if="stagedActionByRowId[row.id]" class="catalog-remediation-muted">
                        Staged: {{ stagedLabel(stagedActionByRowId[row.id]) }}
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
                        @click="stageRowAction(row.id, action.id)"
                      >
                        {{ action.label }}
                      </button>
                      <button
                        type="button"
                        class="runtime-action runtime-action--secondary"
                        @click="void toggleMoreInfo(row)"
                      >
                        {{ expandedRowIds[row.id] ? "Less info" : "...more info" }}
                      </button>
                      <span v-if="!row.actions.length" class="catalog-remediation-muted">
                        No explicit action available
                      </span>
                    </div>
                  </td>
                </tr>
                <tr v-if="expandedRowIds[row.id]" class="catalog-remediation-detail-row">
                  <td colspan="6">
                    <div v-if="isDetailLoading(row)" class="health-card__details">
                      Loading item details...
                    </div>
                    <div v-else-if="detailError(row)" class="runtime-blocking-message">
                      {{ detailError(row) }}
                    </div>
                    <div v-else class="catalog-remediation-detail-grid">
                      <div
                        v-for="detail in detailLines(row)"
                        :key="`${row.id}:${detail.label}:${detail.value}`"
                        class="catalog-remediation-detail-item"
                      >
                        <strong>{{ detail.label }}</strong>
                        <span class="catalog-remediation-mono">{{ detail.value }}</span>
                      </div>
                    </div>
                  </td>
                </tr>
              </template>
            </tbody>
          </table>
        </div>

        <EmptyState
          v-else
          title="No findings in this card"
          message="Nothing is currently visible in this category."
        />
      </article>
    </template>

    <template v-else-if="mode === 'quarantine'">
      <article class="panel catalog-remediation-group">
        <div class="settings-section__header">
          <div>
            <h4>Quarantine</h4>
            <p>Quarantined findings remain reversible until they are deleted permanently here.</p>
          </div>
          <div class="catalog-remediation-group__meta">
            <StatusTag :status="consistencyStore.quarantinedItems.length ? 'warning' : 'ok'" />
            <span class="catalog-remediation-group__count">{{ consistencyStore.quarantinedItems.length }}</span>
          </div>
        </div>

        <EmptyState
          v-if="!consistencyStore.quarantinedItems.length"
          title="Quarantine is empty"
          message="No consistency findings are currently quarantined."
        />

        <div v-else class="catalog-remediation-table-wrapper">
          <table class="catalog-table">
            <thead>
              <tr>
                <th>Category</th>
                <th>Owner</th>
                <th>Source / original path</th>
                <th>Quarantine path</th>
                <th>Reason</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in consistencyStore.quarantinedItems" :key="item.quarantine_item_id">
                <td>{{ item.category_key ?? "unknown" }}</td>
                <td>{{ item.owner_label ?? item.owner_id ?? "Unknown owner" }}</td>
                <td class="catalog-remediation-mono">
                  <div class="catalog-remediation-cell">
                    <span>{{ item.source_path }}</span>
                    <small class="catalog-remediation-muted">
                      {{ item.original_relative_path ?? "No original path recorded" }}
                    </small>
                  </div>
                </td>
                <td class="catalog-remediation-mono">{{ item.quarantine_path }}</td>
                <td>{{ item.reason }}</td>
                <td>
                  <div class="runtime-actions catalog-remediation-row-actions">
                    <button
                      type="button"
                      class="runtime-action runtime-action--secondary"
                      :disabled="consistencyStore.isApplyingAction"
                      @click="void consistencyStore.restoreQuarantineItems([item.quarantine_item_id])"
                    >
                      Restore
                    </button>
                    <button
                      type="button"
                      class="runtime-action"
                      :disabled="consistencyStore.isApplyingAction"
                      @click="void consistencyStore.deleteQuarantineItemsPermanently([item.quarantine_item_id])"
                    >
                      Delete permanently
                    </button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </article>
    </template>

    <template v-else>
      <article class="panel catalog-remediation-group">
        <div class="settings-section__header">
          <div>
            <h4>Ignored findings</h4>
            <p>Ignored findings stay out of the active findings view until you release them here.</p>
          </div>
          <div class="catalog-remediation-group__meta">
            <StatusTag :status="consistencyStore.ignoredFindings.length ? 'warning' : 'ok'" />
            <span class="catalog-remediation-group__count">{{ consistencyStore.ignoredFindings.length }}</span>
          </div>
        </div>

        <EmptyState
          v-if="!consistencyStore.ignoredFindings.length"
          title="Ignored findings are empty"
          message="No active ignore decisions are currently recorded."
        />

        <div v-else class="catalog-remediation-table-wrapper">
          <table class="catalog-table">
            <thead>
              <tr>
                <th>Category</th>
                <th>Owner</th>
                <th>Reason</th>
                <th>Source / time</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in consistencyStore.ignoredFindings" :key="item.ignored_item_id">
                <td>{{ item.category_key }}</td>
                <td>{{ item.owner_label ?? item.owner_id ?? "Unknown owner" }}</td>
                <td>{{ item.reason }}</td>
                <td class="catalog-remediation-mono">
                  <div class="catalog-remediation-cell">
                    <span>{{ item.source_path ?? "No source path recorded" }}</span>
                    <small class="catalog-remediation-muted">{{ item.created_at }}</small>
                  </div>
                </td>
                <td>
                  <button
                    type="button"
                    class="runtime-action runtime-action--secondary"
                    :disabled="consistencyStore.isApplyingAction"
                    @click="void consistencyStore.releaseIgnoredItems([item.ignored_item_id])"
                  >
                    Release ignore
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </article>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import EmptyState from "@/components/common/EmptyState.vue";
import StatusTag from "@/components/common/StatusTag.vue";
import { useConsistencyStore } from "@/stores/consistency";
import type { CatalogValidationReport } from "@/api/types/catalog";
import type {
  CatalogRemediationFindingDetailLine,
  CatalogRemediationGroupKey,
  CatalogRemediationListItem,
  CatalogRemediationRowActionId,
  CatalogRemediationStateItemPayload,
} from "@/api/types/consistency";

type HealthTag = "ok" | "warning" | "error" | "unknown";
type PanelMode = "findings" | "quarantine" | "ignored";
type RowActionId = CatalogRemediationRowActionId;

interface RowActionModel {
  id: RowActionId;
  label: string;
  helpText: string;
  disabledReason: string | null;
}

interface FindingRowModel {
  id: string;
  groupKey: string;
  title: string;
  subtitle: string;
  ownerLabel: string | null;
  ownerHint: string | null;
  badgeLabel: string;
  badgeClass: string;
  message: string;
  summaryPath: string | null;
  summaryContext: string | null;
  statusReason: string;
  blockedReason: string | null;
  actions: RowActionModel[];
  payload: CatalogRemediationStateItemPayload;
  detailLines: CatalogRemediationFindingDetailLine[];
  detailGroupKey: CatalogRemediationGroupKey | null;
}

interface FindingGroupModel {
  key: string;
  title: string;
  description: string;
  status: HealthTag;
  rows: FindingRowModel[];
  actionableRows: FindingRowModel[];
  supportedActions: RowActionId[];
  stagedCount: number;
  totalCount: number;
  limit: number | null;
  offset: number;
  isLoading: boolean;
  error: string | null;
  serverGroupKey: CatalogRemediationGroupKey | null;
}

const pageSizeOptions = [
  { label: "20", value: 20 },
  { label: "100", value: 100 },
  { label: "200", value: 200 },
  { label: "All", value: -1 },
];

const consistencyStore = useConsistencyStore();
const stagedActionByRowId = ref<Record<string, RowActionId>>({});
const expandedRowIds = ref<Record<string, boolean>>({});
const localPagination = ref<Record<string, { limit: number | null; offset: number }>>({});

const props = withDefaults(
  defineProps<{
    mode?: PanelMode;
  }>(),
  {
    mode: "findings",
  },
);

function sectionRows(
  report: CatalogValidationReport | null,
  sectionName: string,
): Array<Record<string, unknown>> {
  const normalizedSectionName = sectionName.trim().toUpperCase();
  const section = report?.sections.find(
    (candidate) => String(candidate.name ?? "").trim().toUpperCase() === normalizedSectionName,
  );
  return section ? (section.rows as Array<Record<string, unknown>>) : [];
}

function badgeClass(value: string): string {
  return `consistency-chip--finding-${value}`;
}

function toTitleCase(value: string): string {
  return value.replace(/_/g, " ");
}

function makeRowAction(
  id: RowActionId,
  label: string,
  helpText: string,
  disabledReason: string | null = null,
): RowActionModel {
  return { id, label, helpText, disabledReason };
}

function pageSizeValue(limit: number | null): string {
  return limit === null ? "-1" : String(limit);
}

function isStorageNoiseRow(row: Record<string, unknown>): boolean {
  const fileName = String(row.file_name ?? "");
  const relativePath = String(row.relative_path ?? "");
  return fileName === ".immich" || fileName.startsWith(".fuse_hidden") || relativePath.includes("/.fuse_hidden");
}

function stagedLabel(actionId: RowActionId): string {
  switch (actionId) {
    case "ignore":
      return "Ignore";
    case "quarantine":
      return "Quarantine";
    case "delete":
      return "Try delete";
    case "mark_removed":
      return "Mark removed";
    case "repair_path":
      return "Repair path";
  }
}

function localGroupPage(key: string): { limit: number | null; offset: number } {
  return localPagination.value[key] ?? { limit: 20, offset: 0 };
}

function updateLocalGroupPage(
  key: string,
  updater: (current: { limit: number | null; offset: number }) => { limit: number | null; offset: number },
): void {
  const current = localGroupPage(key);
  localPagination.value = {
    ...localPagination.value,
    [key]: updater(current),
  };
}

function serverItemActions(item: CatalogRemediationListItem): RowActionModel[] {
  return item.actions.map((actionId) => {
    switch (actionId) {
      case "ignore":
        return makeRowAction("ignore", "Ignore", "Hide this row from active findings.");
      case "quarantine":
        return makeRowAction("quarantine", "Quarantine", "Move the file into quarantine.");
      case "delete":
        return makeRowAction("delete", "Try delete", "Try deleting the artifact directly from storage.");
      case "mark_removed":
        return makeRowAction("mark_removed", "Mark removed", "Apply DB cleanup for a confirmed missing original.");
      case "repair_path":
        return makeRowAction("repair_path", "Repair path", "Apply a DB path correction for the verified relocation.");
    }
  });
}

function serverFindingRow(item: CatalogRemediationListItem): FindingRowModel {
  return {
    id: item.finding_id,
    groupKey: item.group_key,
    title: item.title,
    subtitle: item.subtitle,
    ownerLabel: item.owner_label,
    ownerHint: item.owner_hint,
    badgeLabel: toTitleCase(item.classification),
    badgeClass: badgeClass(item.classification),
    message: item.message,
    summaryPath: item.summary_path,
    summaryContext: item.summary_context,
    statusReason: item.status_reason,
    blockedReason: item.blocked_reason,
    actions: serverItemActions(item),
    payload: item.payload,
    detailLines: [],
    detailGroupKey: item.group_key,
  };
}

function storageMissingRow(row: Record<string, unknown>): FindingRowModel {
  const relativePath = String(row.relative_path ?? "Unavailable");
  const ownerLabel = relativePath.split("/")[0] ?? "Unknown owner";
  return {
    id: `storage-missing:${relativePath}`,
    groupKey: "storage-missing",
    title: String(row.file_name ?? relativePath),
    subtitle: String(row.root_slug ?? "uploads"),
    ownerLabel,
    ownerHint: "Derived from upload path",
    badgeLabel: "Storage orphan",
    badgeClass: badgeClass("found_elsewhere"),
    message: "A storage original exists without a matching DB original reference.",
    summaryPath: String(row.absolute_path ?? relativePath),
    summaryContext: `Size: ${String(row.size_bytes ?? "Unavailable")}`,
    statusReason: "Quarantine or ignore can be staged explicitly.",
    blockedReason: null,
    actions: [
      makeRowAction("quarantine", "Quarantine", "Move the orphan file into quarantine."),
      makeRowAction("ignore", "Ignore", "Hide this row from active findings."),
    ],
    payload: {
      finding_id: `storage-missing:${relativePath}`,
      category_key: "storage-missing",
      title: String(row.file_name ?? relativePath),
      owner_label: ownerLabel,
      source_path: String(row.absolute_path ?? ""),
      root_slug: String(row.root_slug ?? "uploads"),
      relative_path: relativePath,
      size_bytes: Number(row.size_bytes ?? 0),
    },
    detailLines: [
      { label: "Path", value: String(row.absolute_path ?? relativePath) },
      { label: "Root", value: String(row.root_slug ?? "uploads") },
      { label: "Size", value: String(row.size_bytes ?? "Unavailable") },
    ],
    detailGroupKey: null,
  };
}

function orphanDerivativeRow(row: Record<string, unknown>): FindingRowModel {
  const relativePath = String(row.relative_path ?? "Unavailable");
  const originalRelativePath = String(row.original_relative_path ?? "");
  const ownerLabel = (originalRelativePath || relativePath).split("/")[0] ?? "Unknown owner";
  return {
    id: `orphan-derivative:${relativePath}`,
    groupKey: "orphan-derivative",
    title: String(row.derivative_type ?? "orphan"),
    subtitle: String(row.asset_id ?? "No asset"),
    ownerLabel,
    ownerHint: "Derived from original path",
    badgeLabel: "Orphan derivative",
    badgeClass: badgeClass("deletable_orphan"),
    message: "A derivative file exists without the original file.",
    summaryPath: String(row.absolute_path ?? relativePath),
    summaryContext: originalRelativePath || "Original unavailable",
    statusReason: "Quarantine or ignore can be staged explicitly.",
    blockedReason: null,
    actions: [
      makeRowAction("quarantine", "Quarantine", "Move the orphan derivative into quarantine."),
      makeRowAction("ignore", "Ignore", "Hide this row from active findings."),
    ],
    payload: {
      finding_id: `orphan-derivative:${relativePath}`,
      category_key: "orphan-derivative",
      title: String(row.derivative_type ?? relativePath),
      asset_id: String(row.asset_id ?? ""),
      owner_label: ownerLabel,
      source_path: String(row.absolute_path ?? ""),
      root_slug: String(row.root_slug ?? ""),
      relative_path: relativePath,
      original_relative_path: originalRelativePath,
    },
    detailLines: [
      { label: "Path", value: String(row.absolute_path ?? relativePath) },
      { label: "Root", value: String(row.root_slug ?? "") },
      { label: "Original", value: originalRelativePath || "Unavailable" },
      { label: "Asset id", value: String(row.asset_id ?? "Unavailable") },
    ],
    detailGroupKey: null,
  };
}

function unmappedRow(row: Record<string, unknown>): FindingRowModel {
  return {
    id: `unmapped:${String(row.asset_id ?? "unknown")}`,
    groupKey: "path-warning",
    title: String(row.asset_name ?? row.asset_id ?? "Unknown asset"),
    subtitle: String(row.asset_id ?? "unknown"),
    ownerLabel: null,
    ownerHint: null,
    badgeLabel: toTitleCase(String(row.mapping_status ?? "unexpected_root")),
    badgeClass: badgeClass(String(row.mapping_status ?? "unexpected_root")),
    message: "This DB path needs manual inspection before any action is chosen.",
    summaryPath: String(row.database_path ?? "Unavailable"),
    summaryContext: String(row.path_kind ?? "original"),
    statusReason: "Inspect only.",
    blockedReason: "No safe action is available from the catalog-only model.",
    actions: [],
    payload: {
      finding_id: `unmapped:${String(row.asset_id ?? "unknown")}`,
      category_key: "path-warning",
      title: String(row.asset_name ?? row.asset_id ?? "Unknown asset"),
    },
    detailLines: [
      { label: "Database path", value: String(row.database_path ?? "Unavailable") },
      { label: "Path kind", value: String(row.path_kind ?? "original") },
      { label: "Mapping status", value: String(row.mapping_status ?? "unexpected_root") },
    ],
    detailGroupKey: null,
  };
}

function paginateRows(rows: FindingRowModel[], key: string): {
  rows: FindingRowModel[];
  totalCount: number;
  limit: number | null;
  offset: number;
} {
  const { limit, offset } = localGroupPage(key);
  if (limit === null) {
    return {
      rows: rows.slice(offset),
      totalCount: rows.length,
      limit,
      offset,
    };
  }
  return {
    rows: rows.slice(offset, offset + limit),
    totalCount: rows.length,
    limit,
    offset,
  };
}

const report = computed(() => consistencyStore.catalogReport);
const hiddenFindingIds = computed<Set<string>>(
  () => consistencyStore.hiddenFindingIds ?? new Set<string>(),
);

const localGroups = computed(() => {
  const storageMissingRows = consistencyStore.storageOriginalsMissingInDb
    .filter((row) => !isStorageNoiseRow(row))
    .map(storageMissingRow)
    .filter((row) => !hiddenFindingIds.value.has(row.id));
  const orphanRows = consistencyStore.orphanDerivatives
    .map(orphanDerivativeRow)
    .filter((row) => !hiddenFindingIds.value.has(row.id));
  const unmappedRows = sectionRows(report.value, "UNMAPPED_DATABASE_PATHS")
    .map(unmappedRow)
    .filter((row) => !hiddenFindingIds.value.has(row.id));

  return [
    {
      key: "storage-missing",
      title: "Storage originals missing in DB",
      description: "Files on storage without a matching original DB row.",
      rows: storageMissingRows,
    },
    {
      key: "orphan-derivative",
      title: "Orphan derivatives",
      description: "Derivative files that remain after the original disappeared.",
      rows: orphanRows,
    },
    {
      key: "path-warning",
      title: "Path warnings",
      description: "DB paths that mapped unclearly and remain inspect-only.",
      rows: unmappedRows,
    },
  ];
});

const findingGroups = computed<FindingGroupModel[]>(() => {
  const serverGroups = consistencyStore.remediationGroups
    .filter((group) => group.count > 0)
    .map((group) => {
      const pageState = consistencyStore.getGroupPageState(group.key);
      const rows = pageState.items.map(serverFindingRow);
      const actionableRows = rows.filter((row) => row.actions.length > 0);
      const supportedActions = [
        ...new Set(actionableRows.flatMap((row) => row.actions.map((action) => action.id))),
      ];
      const stagedCount = rows.filter((row) => Boolean(stagedActionByRowId.value[row.id])).length;
      return {
        key: group.key,
        title: group.title,
        description: group.description,
        status: actionableRows.length ? "warning" : "ok",
        rows,
        actionableRows,
        supportedActions,
        stagedCount,
        totalCount: group.count,
        limit: pageState.limit,
        offset: pageState.offset,
        isLoading: pageState.isLoading,
        error: pageState.error,
        serverGroupKey: group.key,
      } satisfies FindingGroupModel;
    });

  const paginatedLocalGroups = localGroups.value
    .map((group) => {
      const page = paginateRows(group.rows, group.key);
      const actionableRows = page.rows.filter((row) => row.actions.length > 0);
      const supportedActions = [
        ...new Set(actionableRows.flatMap((row) => row.actions.map((action) => action.id))),
      ];
      const stagedCount = page.rows.filter((row) => Boolean(stagedActionByRowId.value[row.id])).length;
      return {
        key: group.key,
        title: group.title,
        description: group.description,
        status: actionableRows.length ? "warning" : "ok",
        rows: page.rows,
        actionableRows,
        supportedActions,
        stagedCount,
        totalCount: page.totalCount,
        limit: page.limit,
        offset: page.offset,
        isLoading: false,
        error: null,
        serverGroupKey: null,
      } satisfies FindingGroupModel;
    })
    .filter((group) => group.totalCount > 0);

  return [...serverGroups, ...paginatedLocalGroups];
});

watch(
  () => ({
    mode: props.mode,
    groups: consistencyStore.remediationGroups.map((group) => `${group.key}:${group.count}`).join("|"),
  }),
  ({ mode }) => {
    if (mode !== "findings") {
      return;
    }
    for (const group of consistencyStore.remediationGroups) {
      if (group.count <= 0) {
        continue;
      }
      const state = consistencyStore.getGroupPageState(group.key);
      if (!state.loaded && !state.isLoading) {
        void consistencyStore.loadRemediationGroupPage(group.key);
      }
    }
  },
  { immediate: true },
);

const workspaceSummary = computed(() => {
  if (props.mode === "quarantine") {
    return consistencyStore.quarantineState?.summary ?? "Active quarantine items are listed here.";
  }
  if (props.mode === "ignored") {
    return consistencyStore.ignoredState?.summary ?? "Active ignore decisions are listed here.";
  }
  if (consistencyStore.remediationOverview?.summary) {
    return consistencyStore.remediationOverview.summary;
  }
  if (report.value?.summary) {
    return report.value.summary;
  }
  return "No catalog-backed findings are loaded yet.";
});

const workspaceDetails = computed(() => {
  if (props.mode === "findings") {
    return "Each card now loads only the requested page. Extra detail is fetched per item only when you open `...more info`.";
  }
  if (props.mode === "quarantine") {
    return "Final deletion is only available from this quarantine view.";
  }
  return "Ignored findings show category, reason, and timestamp until they are released.";
});

const panelStatus = computed<HealthTag>(() => {
  if (consistencyStore.actionError || consistencyStore.catalogJobError) {
    return "error";
  }
  if (
    findingGroups.value.length ||
    consistencyStore.quarantinedItems.length ||
    consistencyStore.ignoredFindings.length
  ) {
    return "warning";
  }
  return "ok";
});

function stageRowAction(rowId: string, actionId: RowActionId): void {
  stagedActionByRowId.value = {
    ...stagedActionByRowId.value,
    [rowId]: actionId,
  };
}

function stageGroupAction(groupKey: string, actionId: RowActionId): void {
  const next = { ...stagedActionByRowId.value };
  const group = findingGroups.value.find((candidate) => candidate.key === groupKey);
  if (!group) {
    return;
  }
  for (const row of group.rows) {
    if (row.actions.some((action) => action.id === actionId)) {
      next[row.id] = actionId;
    }
  }
  stagedActionByRowId.value = next;
}

function stageUnstagedIgnore(groupKey: string): void {
  const next = { ...stagedActionByRowId.value };
  const group = findingGroups.value.find((candidate) => candidate.key === groupKey);
  if (!group) {
    return;
  }
  for (const row of group.rows) {
    if (!next[row.id] && row.actions.some((action) => action.id === "ignore")) {
      next[row.id] = "ignore";
    }
  }
  stagedActionByRowId.value = next;
}

function clearGroupStage(groupKey: string): void {
  const next = { ...stagedActionByRowId.value };
  for (const row of findingGroups.value.find((candidate) => candidate.key === groupKey)?.rows ?? []) {
    delete next[row.id];
  }
  stagedActionByRowId.value = next;
}

async function performGroupActions(group: FindingGroupModel): Promise<void> {
  const rows = group.rows.filter((row) => stagedActionByRowId.value[row.id]);
  const ignoreItems = rows
    .filter((row) => stagedActionByRowId.value[row.id] === "ignore")
    .map((row) => row.payload);
  const quarantineItems = rows
    .filter((row) => stagedActionByRowId.value[row.id] === "quarantine")
    .map((row) => row.payload);
  const deleteFindingIds = rows
    .filter((row) => stagedActionByRowId.value[row.id] === "delete")
    .map((row) => row.id);
  const markRemovedAssetIds = rows
    .filter((row) => stagedActionByRowId.value[row.id] === "mark_removed" && row.payload.asset_id)
    .map((row) => String(row.payload.asset_id));
  const repairPathAssetIds = rows
    .filter((row) => stagedActionByRowId.value[row.id] === "repair_path" && row.payload.asset_id)
    .map((row) => String(row.payload.asset_id));

  if (markRemovedAssetIds.length) {
    await consistencyStore.applyBrokenDbAction(markRemovedAssetIds, "broken_db_cleanup");
  }
  if (repairPathAssetIds.length) {
    await consistencyStore.applyBrokenDbAction(repairPathAssetIds, "broken_db_path_fix");
  }
  if (quarantineItems.length) {
    await consistencyStore.quarantineItems(quarantineItems);
  }
  if (deleteFindingIds.length && group.key === "fuse-hidden") {
    await consistencyStore.applyFindingAction(deleteFindingIds, "fuse_hidden_delete");
  }
  if (ignoreItems.length) {
    await consistencyStore.ignoreItems(ignoreItems);
  }
  clearGroupStage(group.key);
}

function canGoNext(group: FindingGroupModel): boolean {
  if (group.limit === null) {
    return false;
  }
  return group.offset + group.limit < group.totalCount;
}

async function changePage(group: FindingGroupModel, direction: "prev" | "next"): Promise<void> {
  const pageSize = group.limit;
  if (pageSize === null) {
    return;
  }
  const delta = direction === "next" ? pageSize : -pageSize;
  const nextOffset = Math.max(0, group.offset + delta);
  if (group.serverGroupKey) {
    await consistencyStore.loadRemediationGroupPage(group.serverGroupKey, {
      limit: pageSize,
      offset: nextOffset,
    });
    return;
  }
  updateLocalGroupPage(group.key, (current) => ({
    ...current,
    offset: nextOffset,
  }));
}

function onPageSizeChange(group: FindingGroupModel, rawValue: string): void {
  const parsed = Number(rawValue);
  const nextLimit = parsed < 0 ? null : parsed;
  if (group.serverGroupKey) {
    void consistencyStore.loadRemediationGroupPage(group.serverGroupKey, {
      limit: nextLimit,
      offset: 0,
    });
    return;
  }
  updateLocalGroupPage(group.key, () => ({
    limit: nextLimit,
    offset: 0,
  }));
}

function pageLabel(group: FindingGroupModel): string {
  if (!group.totalCount) {
    return "0-0";
  }
  const start = group.offset + 1;
  const end = group.limit === null ? group.totalCount : Math.min(group.totalCount, group.offset + group.limit);
  return `${start}-${end} of ${group.totalCount}`;
}

function detailState(row: FindingRowModel) {
  if (!row.detailGroupKey) {
    return null;
  }
  return consistencyStore.remediationFindingDetails[`${row.detailGroupKey}:${row.id}`] ?? null;
}

function detailLines(row: FindingRowModel): CatalogRemediationFindingDetailLine[] {
  if (!row.detailGroupKey) {
    return row.detailLines;
  }
  return detailState(row)?.data?.details ?? [];
}

function isDetailLoading(row: FindingRowModel): boolean {
  return Boolean(row.detailGroupKey && detailState(row)?.isLoading);
}

function detailError(row: FindingRowModel): string | null {
  return row.detailGroupKey ? detailState(row)?.error ?? null : null;
}

async function toggleMoreInfo(row: FindingRowModel): Promise<void> {
  const expanded = Boolean(expandedRowIds.value[row.id]);
  expandedRowIds.value = {
    ...expandedRowIds.value,
    [row.id]: !expanded,
  };
  if (!expanded && row.detailGroupKey) {
    await consistencyStore.loadRemediationFindingDetail(row.detailGroupKey, row.id);
  }
}

async function refreshPanel(): Promise<void> {
  await consistencyStore.refreshRemediation();
}
</script>

<style scoped>
.catalog-remediation-panel,
.catalog-remediation-workspace,
.catalog-remediation-group {
  display: grid;
  gap: 1rem;
}

.catalog-remediation-table-wrapper {
  overflow-x: auto;
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

.catalog-remediation-row-actions,
.catalog-remediation-group__actions {
  justify-content: start;
  flex-wrap: wrap;
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

.catalog-remediation-pagination {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
}

.catalog-remediation-pagination__size {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.catalog-remediation-pagination__controls {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.catalog-remediation-detail-row td {
  background: #fbfcfd;
}

.catalog-remediation-detail-grid {
  display: grid;
  gap: 0.75rem;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
}

.catalog-remediation-detail-item {
  display: grid;
  gap: 0.25rem;
}
</style>
