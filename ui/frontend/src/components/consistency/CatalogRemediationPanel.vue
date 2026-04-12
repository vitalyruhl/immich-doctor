<template>
  <section class="catalog-remediation-panel">
    <section class="panel catalog-remediation-workspace">
      <div class="settings-section__header">
        <div>
          <h3>Catalog findings workspace</h3>
          <p>
            Review cached findings, stage explicit operator actions on the right side,
            and separate active findings from quarantine and ignored state.
          </p>
        </div>
        <StatusTag :status="panelStatus" />
      </div>

      <section class="runtime-actions">
        <button
          v-if="mode === 'findings'"
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
      <section v-if="!consistencyStore.remediationLoaded" class="panel catalog-remediation-group">
        <div class="settings-section__header">
          <div>
            <h4>Cached findings</h4>
            <p>Detailed findings load on demand to keep the consistency page responsive on large datasets.</p>
          </div>
          <StatusTag status="unknown" />
        </div>

        <p class="health-card__summary">The cached findings view is not loaded yet.</p>
        <p class="health-card__details">
          Load the cached findings when needed, or rebuild them explicitly after a finished storage scan.
        </p>

        <section class="runtime-actions">
          <button
            type="button"
            class="runtime-action runtime-action--secondary"
            :disabled="consistencyStore.isLoadingRemediation || consistencyStore.isRefreshingRemediation"
            @click="void loadCachedFindings()"
          >
            {{
              consistencyStore.isLoadingRemediation
                ? "Loading cached findings..."
                : "Load cached findings"
            }}
          </button>
          <button
            type="button"
            class="runtime-action"
            :disabled="consistencyStore.isRefreshingRemediation"
            @click="void refreshPanel()"
          >
            {{
              consistencyStore.isRefreshingRemediation
                ? "Refreshing..."
                : "Refresh detailed findings"
            }}
          </button>
        </section>
      </section>

      <EmptyState
        v-else-if="!findingGroups.length"
        title="No grouped findings available"
        message="Load the cached findings or run an explicit refresh to review operator actions here."
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
            <span class="catalog-remediation-group__count">{{ group.rows.length }}</span>
          </div>
        </div>

        <section v-if="group.actionableRows.length" class="runtime-actions catalog-remediation-group__actions">
          <button
            v-if="group.supportedActions.includes('delete')"
            type="button"
            class="runtime-action runtime-action--secondary"
            @click="stageGroupAction(group.key, 'delete')"
          >
            {{ group.key === 'fuse-hidden' ? "Try delete all" : "Delete all" }}
          </button>
          <button
            v-if="group.supportedActions.includes('quarantine')"
            type="button"
            class="runtime-action runtime-action--secondary"
            @click="stageGroupAction(group.key, 'quarantine')"
          >
            {{ group.key === 'fuse-hidden' ? "Quarantine all artifacts" : "Quarantine all" }}
          </button>
          <button
            v-if="group.supportedActions.includes('ignore')"
            type="button"
            class="runtime-action runtime-action--secondary"
            @click="stageGroupAction(group.key, 'ignore')"
          >
            Ignore all
          </button>
          <button
            v-if="group.supportedActions.includes('ignore')"
            type="button"
            class="runtime-action runtime-action--secondary"
            @click="stageUnstagedIgnore(group.key)"
          >
            Ignore unselected
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

        <div class="catalog-remediation-table-wrapper">
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
              <tr
                v-for="row in group.rows"
                :key="row.id"
                :class="{ 'catalog-remediation-row--staged': Boolean(stagedActionByRowId[row.id]) }"
              >
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
                    <span v-for="detail in row.pathDetails" :key="detail">{{ detail }}</span>
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
                    <span v-if="!row.actions.length" class="catalog-remediation-muted">
                      No explicit action available
                    </span>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
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
import { computed, ref } from "vue";
import EmptyState from "@/components/common/EmptyState.vue";
import StatusTag from "@/components/common/StatusTag.vue";
import { useConsistencyStore } from "@/stores/consistency";
import type { CatalogValidationReport } from "@/api/types/catalog";
import type {
  BrokenDbOriginalFinding,
  CatalogRemediationStateItemPayload,
  FuseHiddenOrphanFinding,
  ZeroByteFinding,
} from "@/api/types/consistency";

type HealthTag = "ok" | "warning" | "error" | "unknown";
type PanelMode = "findings" | "quarantine" | "ignored";
type RowActionId =
  | "inspect"
  | "ignore"
  | "quarantine"
  | "delete"
  | "mark_removed"
  | "repair_path";

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
  pathDetails: string[];
  statusReason: string;
  blockedReason: string | null;
  actions: RowActionModel[];
  payload: CatalogRemediationStateItemPayload;
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
}

const consistencyStore = useConsistencyStore();
const stagedActionByRowId = ref<Record<string, RowActionId>>({});

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

function pathLine(label: string, value: string | null | undefined): string {
  return value ? `${label}: ${value}` : `${label}: Unavailable`;
}

function ownerHint(value: string | null | undefined): string | null {
  return value ? `Source owner key: ${value}` : null;
}

function makeRowAction(
  id: RowActionId,
  label: string,
  helpText: string,
  disabledReason: string | null = null,
): RowActionModel {
  return { id, label, helpText, disabledReason };
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
    default:
      return "Inspect";
  }
}

function brokenDbRow(finding: BrokenDbOriginalFinding): FindingRowModel {
  const actions: RowActionModel[] = [makeRowAction("ignore", "Ignore", "Hide this row from active findings.")];
  if (finding.classification === "missing_confirmed") {
    actions.unshift(
      makeRowAction(
        "mark_removed",
        "Mark removed",
        "Apply DB cleanup for a confirmed missing original.",
      ),
    );
  }
  if (finding.classification === "found_with_hash_match") {
    actions.unshift(
      makeRowAction(
        "repair_path",
        "Repair path",
        "Apply a DB path correction for the verified relocation.",
      ),
    );
  }
  return {
    id: finding.finding_id,
    groupKey: "broken-db",
    title: finding.asset_name ?? finding.asset_id,
    subtitle: finding.asset_id,
    ownerLabel: finding.owner_label,
    ownerHint: ownerHint(finding.owner_id),
    badgeLabel: toTitleCase(finding.classification),
    badgeClass: badgeClass(finding.classification),
    message: finding.message,
    pathDetails: [
      pathLine("Expected", finding.expected_database_path),
      pathLine("Found", finding.found_absolute_path),
    ],
    statusReason: finding.action_reason,
    blockedReason: null,
    actions,
    payload: {
      finding_id: finding.finding_id,
      category_key: "broken-db",
      title: finding.asset_name ?? finding.asset_id,
      asset_id: finding.asset_id,
      owner_id: finding.owner_id,
      owner_label: finding.owner_label,
      source_path: finding.expected_absolute_path,
      relative_path: finding.expected_relative_path,
    },
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
    pathDetails: [
      pathLine("Path", String(row.absolute_path ?? relativePath)),
      pathLine("Size", String(row.size_bytes ?? "Unavailable")),
    ],
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
    pathDetails: [
      pathLine("Path", String(row.absolute_path ?? relativePath)),
      pathLine("Original", originalRelativePath || "Unavailable"),
    ],
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
  };
}

function zeroByteRow(finding: ZeroByteFinding): FindingRowModel {
  return {
    id: finding.finding_id,
    groupKey: "zero-byte",
    title: finding.file_name,
    subtitle: finding.asset_name ?? finding.asset_id ?? finding.root_slug,
    ownerLabel: finding.owner_label,
    ownerHint: ownerHint(finding.owner_id ?? finding.db_reference_kind),
    badgeLabel: toTitleCase(finding.classification),
    badgeClass: badgeClass(finding.classification),
    message: finding.message,
    pathDetails: [
      pathLine("Path", finding.absolute_path),
      pathLine("DB wiring", finding.db_reference_kind),
      pathLine("Original", finding.original_relative_path),
    ],
    statusReason: finding.action_reason,
    blockedReason: null,
    actions: [
      makeRowAction("quarantine", "Quarantine", "Move the zero-byte file into quarantine."),
      makeRowAction("ignore", "Ignore", "Hide this row from active findings."),
    ],
    payload: {
      finding_id: finding.finding_id,
      category_key: "zero-byte",
      title: finding.file_name,
      asset_id: finding.asset_id,
      owner_id: finding.owner_id,
      owner_label: finding.owner_label,
      source_path: finding.absolute_path,
      root_slug: finding.root_slug,
      relative_path: finding.relative_path,
      original_relative_path: finding.original_relative_path,
      db_reference_kind: finding.db_reference_kind,
      size_bytes: finding.size_bytes,
    },
  };
}

function fuseHiddenRow(finding: FuseHiddenOrphanFinding): FindingRowModel {
  const actions =
    finding.classification === "blocked_in_use"
      ? [makeRowAction("ignore", "Ignore", "Keep this in-use artifact out of the active list.")]
      : [
          makeRowAction("delete", "Try delete", "Try deleting the artifact directly from storage."),
          makeRowAction("ignore", "Ignore", "Hide this row from active findings."),
        ];
  return {
    id: finding.finding_id,
    groupKey: "fuse-hidden",
    title: finding.file_name,
    subtitle: finding.root_slug,
    ownerLabel: finding.owner_label,
    ownerHint: ownerHint(finding.owner_id),
    badgeLabel: toTitleCase(finding.classification),
    badgeClass: badgeClass(finding.classification),
    message: finding.message,
    pathDetails: [
      pathLine("Path", finding.absolute_path),
      pathLine("Check", finding.in_use_check_reason),
    ],
    statusReason: finding.action_reason,
    blockedReason: null,
    actions,
    payload: {
      finding_id: finding.finding_id,
      category_key: "fuse-hidden",
      title: finding.file_name,
      owner_id: finding.owner_id,
      owner_label: finding.owner_label,
      source_path: finding.absolute_path,
      root_slug: finding.root_slug,
      relative_path: finding.relative_path,
      size_bytes: finding.size_bytes,
    },
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
    pathDetails: [
      pathLine("Database path", String(row.database_path ?? "Unavailable")),
      pathLine("Path kind", String(row.path_kind ?? "original")),
    ],
    statusReason: "Inspect only.",
    blockedReason: "No safe action is available from the catalog-only model.",
    actions: [],
    payload: {
      finding_id: `unmapped:${String(row.asset_id ?? "unknown")}`,
      category_key: "path-warning",
      title: String(row.asset_name ?? row.asset_id ?? "Unknown asset"),
    },
  };
}

const report = computed(() => consistencyStore.catalogReport);
const hiddenFindingIds = computed<Set<string>>(
  () => consistencyStore.hiddenFindingIds ?? new Set<string>(),
);

const brokenRows = computed(() =>
  consistencyStore.brokenDbOriginals
    .map(brokenDbRow)
    .filter((row) => !hiddenFindingIds.value.has(row.id)),
);
const storageMissingRows = computed(() =>
  consistencyStore.storageOriginalsMissingInDb
    .filter((row) => !isStorageNoiseRow(row))
    .map(storageMissingRow)
    .filter((row) => !hiddenFindingIds.value.has(row.id)),
);
const orphanDerivativeRows = computed(() =>
  consistencyStore.orphanDerivatives
    .map(orphanDerivativeRow)
    .filter((row) => !hiddenFindingIds.value.has(row.id)),
);
const zeroByteRows = computed(() =>
  consistencyStore.zeroByteFindings
    .map(zeroByteRow)
    .filter((row) => !hiddenFindingIds.value.has(row.id)),
);
const fuseHiddenRows = computed(() =>
  consistencyStore.fuseHiddenOrphans
    .map(fuseHiddenRow)
    .filter((row) => !hiddenFindingIds.value.has(row.id)),
);
const unmappedRows = computed(() =>
  sectionRows(report.value, "UNMAPPED_DATABASE_PATHS")
    .map(unmappedRow)
    .filter((row) => !hiddenFindingIds.value.has(row.id)),
);

const rawGroups = computed(() => [
  {
    key: "broken-db",
    title: "DB originals missing in storage",
    description: "Broken original references, relocations, and verified path mismatches.",
    rows: brokenRows.value,
  },
  {
    key: "storage-missing",
    title: "Storage originals missing in DB",
    description: "Files on storage without a matching original DB row.",
    rows: storageMissingRows.value,
  },
  {
    key: "orphan-derivative",
    title: "Orphan derivatives",
    description: "Derivative files that remain after the original disappeared.",
    rows: orphanDerivativeRows.value,
  },
  {
    key: "zero-byte",
    title: "Zero-byte files",
    description: "Zero-byte originals and derivatives with DB-wiring context.",
    rows: zeroByteRows.value,
  },
  {
    key: "fuse-hidden",
    title: "`.fuse_hidden*` artifacts",
    description: "FUSE/Unraid artifacts that should be deleted directly when safe.",
    rows: fuseHiddenRows.value,
  },
  {
    key: "path-warning",
    title: "Path warnings",
    description: "DB paths that mapped unclearly and remain inspect-only.",
    rows: unmappedRows.value,
  },
]);

const findingGroups = computed<FindingGroupModel[]>(() =>
  rawGroups.value
    .filter((group) => group.rows.length > 0)
    .map((group) => {
      const actionableRows = group.rows.filter((row) => row.actions.length > 0);
      const supportedActions = [
        ...new Set(actionableRows.flatMap((row) => row.actions.map((action) => action.id))),
      ];
      const stagedCount = group.rows.filter((row) => Boolean(stagedActionByRowId.value[row.id])).length;
      return {
        key: group.key,
        title: group.title,
        description: group.description,
        status: actionableRows.length ? "warning" : "ok",
        rows: group.rows,
        actionableRows,
        supportedActions,
        stagedCount,
      };
    }),
);

const workspaceSummary = computed(() => {
  if (props.mode === "quarantine") {
    return consistencyStore.quarantineState?.summary ?? "Active quarantine items are listed here.";
  }
  if (props.mode === "ignored") {
    return consistencyStore.ignoredState?.summary ?? "Active ignore decisions are listed here.";
  }
  if (consistencyStore.remediationScanResult?.summary) {
    return consistencyStore.remediationScanResult.summary;
  }
  if (report.value?.summary) {
    return report.value.summary;
  }
  return "No catalog-backed findings are loaded yet.";
});

const workspaceDetails = computed(() => {
  if (props.mode === "findings") {
    return "Nothing mutates automatically here. Detailed findings only rebuild after explicit refresh or directly after a finished storage scan.";
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

async function refreshPanel(): Promise<void> {
  await consistencyStore.refreshRemediation();
}

async function loadCachedFindings(): Promise<void> {
  await consistencyStore.loadRemediation();
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

</style>
