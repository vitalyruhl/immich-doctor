<template>
  <section class="panel catalog-consistency-panel">
    <div class="settings-section__header">
      <div>
        <h3>Catalog-backed storage compare</h3>
        <p>
          Cached storage inventory, zero-byte detection, DB-vs-storage mismatches, and orphan
          derivatives run as a locked background workflow.
        </p>
      </div>
      <StatusTag :status="panelStatus" />
    </div>

    <section class="runtime-actions">
      <button
        type="button"
        class="runtime-action"
        :disabled="consistencyStore.isCatalogStarting || flowActive"
        @click="void startValidation(true)"
      >
        {{ flowActive ? "Consistency running..." : report ? "Rescan consistency" : "Start consistency" }}
      </button>
      <button
        type="button"
        class="runtime-action runtime-action--secondary"
        :disabled="consistencyStore.isCatalogLoading"
        @click="void refreshJob()"
      >
        Refresh state
      </button>
    </section>

    <p class="health-card__summary">
      {{ report?.summary ?? currentSummary }}
    </p>
    <p v-if="progressMessage" class="health-card__details">{{ progressMessage }}</p>
    <p v-if="progressStats" class="health-card__details">{{ progressStats }}</p>
    <p v-if="blockedSummary" class="runtime-blocking-message">{{ blockedSummary }}</p>
    <p v-if="consistencyStore.catalogJobError" class="runtime-blocking-message">
      {{ consistencyStore.catalogJobError }}
    </p>

    <section v-if="progressPercent !== null" class="catalog-consistency-progress">
      <progress :value="progressPercent" max="100" />
      <strong>{{ progressPercent.toFixed(1) }}%</strong>
    </section>

    <dl class="runtime-detail__grid catalog-consistency-metadata">
      <dt>Storage scan basis</dt>
      <dd>{{ scanTimestampLabel }}</dd>
      <dt>Compare built at</dt>
      <dd>{{ compareTimestampLabel }}</dd>
    </dl>

    <p v-if="staleSummary" class="runtime-blocking-message">{{ staleSummary }}</p>

    <section v-if="report" class="health-grid catalog-consistency-grid">
      <article
        v-for="card in summaryCards"
        :key="card.label"
        class="catalog-consistency-card"
      >
        <div class="health-card__header">
          <h4>{{ card.label }}</h4>
          <StatusTag :status="card.status" />
        </div>
        <p class="health-card__summary">{{ card.count }}</p>
        <p class="health-card__details">{{ card.message }}</p>
      </article>
    </section>

    <EmptyState
      v-if="!report"
      :title="emptyStateTitle"
      :message="emptyStateMessage"
    />

    <template v-else>
      <article
        v-for="section in reportSections"
        :key="section.name"
        class="catalog-consistency-section"
      >
        <div class="settings-section__header">
          <div>
            <h4>{{ section.title }}</h4>
            <p>{{ section.description }}</p>
          </div>
          <StatusTag :status="section.status" />
        </div>
        <p v-if="section.truncated" class="health-card__details">
          Sample output is truncated in the UI. Use the report metadata and logs for the full
          count.
        </p>
        <EmptyState
          v-if="!section.rows.length"
          :title="`No findings for ${section.title}`"
          message="No rows were returned for this category in the latest cached report."
        />
        <div v-else class="catalog-consistency-table-wrapper">
          <table class="catalog-table">
            <thead>
              <tr>
                <th v-for="column in section.columns" :key="column">{{ column }}</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="(row, index) in section.rows"
                :key="`${section.name}:${index}`"
              >
                <td v-for="column in section.columns" :key="`${section.name}:${index}:${column}`">
                  {{ displayValue(row[column]) }}
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
import { computed, onMounted, onUnmounted, watch } from "vue";
import EmptyState from "@/components/common/EmptyState.vue";
import StatusTag from "@/components/common/StatusTag.vue";
import { useConsistencyStore } from "@/stores/consistency";
import type {
  CatalogJobProgress,
  CatalogValidationReport,
  CatalogValidationSection,
  CatalogWorkflowJobRecord,
} from "@/api/types/catalog";

type HealthTag = "ok" | "warning" | "error" | "unknown";

interface ReportSectionDescriptor {
  name: string;
  title: string;
  description: string;
  columns: string[];
}

interface ReportSectionViewModel extends ReportSectionDescriptor {
  rows: Array<Record<string, unknown>>;
  status: HealthTag;
  truncated: boolean;
}

interface SummaryCardViewModel {
  label: string;
  count: number;
  status: HealthTag;
  message: string;
}

interface CatalogConsistencyJobState {
  stale?: boolean;
  staleReason?: string | null;
  requiresScan?: boolean;
  previousCompareGeneratedAt?: string | null;
  latestScanCommittedAt?: string | null;
  staleRootSlugs?: string[];
  missingRootSlugs?: string[];
}

const consistencyStore = useConsistencyStore();
let pollHandle: number | null = null;

const sectionDescriptors: ReportSectionDescriptor[] = [
  {
    name: "DB_ORIGINALS_MISSING_ON_STORAGE",
    title: "DB originals not found in current storage snapshot",
    description:
      "Rows that resolve safely into the uploads root but are absent from the current cached storage snapshot.",
    columns: [
      "asset_id",
      "asset_name",
      "asset_type",
      "mapping_mode",
      "database_path",
    ],
  },
  {
    name: "STORAGE_ORIGINALS_MISSING_IN_DB",
    title: "Storage originals missing in DB",
    description: "Files indexed on storage that do not have a matching original DB row.",
    columns: ["root_slug", "relative_path", "file_name", "size_bytes", "generation"],
  },
  {
    name: "ORPHAN_DERIVATIVES_WITHOUT_ORIGINAL",
    title: "Orphan derivatives",
    description: "Preview, thumbnail, video, or sidecar files that remain without the original.",
    columns: [
      "asset_id",
      "derivative_type",
      "root_slug",
      "relative_path",
      "original_relative_path",
    ],
  },
  {
    name: "ZERO_BYTE_FILES",
    title: "Zero-byte files",
    description: "Files found during the cached storage scan that have a size of zero bytes.",
    columns: ["root_slug", "relative_path", "file_name", "size_bytes", "generation"],
  },
  {
    name: "UNMAPPED_DATABASE_PATHS",
    title: "Unmapped DB paths",
    description:
      "DB paths that could not be resolved safely into the configured runtime roots and therefore are not counted as confirmed missing files.",
    columns: ["asset_id", "asset_name", "path_kind", "mapping_status", "database_path"],
  },
];

function toTag(state: string | null | undefined): HealthTag {
  if (!state) {
    return "unknown";
  }
  if (["completed", "pass", "PASS"].includes(state)) {
    return "ok";
  }
  if (["pending", "running", "partial", "warn", "WARN"].includes(state)) {
    return "warning";
  }
  if (["failed", "fail", "FAIL", "canceled"].includes(state)) {
    return "error";
  }
  return "unknown";
}

function isFlowActive(job: CatalogWorkflowJobRecord | null): boolean {
  if (!job) {
    return false;
  }
  if (job.jobId && ["pending", "running", "cancel_requested"].includes(job.state)) {
    return true;
  }
  return Boolean(job.result?.blockedBy);
}

function getSectionRows(
  report: CatalogValidationReport | null,
  sectionName: string,
): Array<Record<string, unknown>> {
  const section = report?.sections.find((candidate) => candidate.name === sectionName);
  return section ? (section.rows as Array<Record<string, unknown>>) : [];
}

function displayValue(value: unknown): string {
  if (value === null || value === undefined || value === "") {
    return "Unavailable";
  }
  return String(value);
}

const report = computed(() => consistencyStore.catalogReport);
const job = computed(() => consistencyStore.catalogJob);
const flowActive = computed(() => isFlowActive(job.value));
const progress = computed<CatalogJobProgress | null>(() => {
  const candidate = job.value?.result?.progress;
  return candidate && typeof candidate === "object" ? (candidate as CatalogJobProgress) : null;
});
const progressPercent = computed<number | null>(() => {
  const value = progress.value?.percent;
  return typeof value === "number" ? value : null;
});
const blockedSummary = computed(() => {
  const blockedBy = job.value?.result?.blockedBy;
  if (!blockedBy || typeof blockedBy !== "object") {
    return null;
  }
  const summary = blockedBy.summary;
  return typeof summary === "string" ? summary : "The workflow is blocked by another job.";
});
const staleState = computed(() => {
  const candidate = job.value?.result;
  return candidate && typeof candidate === "object"
    ? (candidate as CatalogConsistencyJobState)
    : null;
});
const currentSummary = computed(() => job.value?.summary ?? "No catalog consistency workflow is active.");
const progressMessage = computed(() => progress.value?.message ?? null);
const progressStats = computed(() => {
  if (!progress.value) {
    return null;
  }
  if (
    progress.value.phase === "prepare"
    && typeof progress.value.directoriesDiscovered === "number"
  ) {
    return `Counting directories: ${progress.value.directoriesDiscovered}`;
  }
  if (
    typeof progress.value.directoriesTotal === "number"
    && typeof progress.value.directoriesCompleted === "number"
  ) {
    return `Directories: ${progress.value.directoriesCompleted} / ${progress.value.directoriesTotal}`;
  }
  if (
    typeof progress.value.directoriesCompleted === "number"
    && typeof progress.value.pendingDirectories === "number"
  ) {
    const total = progress.value.directoriesCompleted + progress.value.pendingDirectories;
    return `Directories: ${progress.value.directoriesCompleted} / ${total}`;
  }
  if (typeof progress.value.current === "number" && typeof progress.value.total === "number") {
    return `${progress.value.current} of ${progress.value.total}`;
  }
  return null;
});
const panelStatus = computed<HealthTag>(() => {
  if (consistencyStore.catalogJobError) {
    return "error";
  }
  if (staleState.value?.stale) {
    return "warning";
  }
  if (flowActive.value) {
    return "warning";
  }
  return toTag(report.value?.status ?? job.value?.state);
});
const totals = computed<Record<string, number>>(() => {
  const candidate = report.value?.metadata?.totals;
  return candidate && typeof candidate === "object" ? (candidate as Record<string, number>) : {};
});
const truncated = computed<Record<string, boolean>>(() => {
  const candidate = report.value?.metadata?.truncated;
  return candidate && typeof candidate === "object" ? (candidate as Record<string, boolean>) : {};
});
const summaryCards = computed<SummaryCardViewModel[]>(() => [
  {
    label: "DB not found in snapshot",
    count: totals.value.dbOriginalsMissingOnStorage ?? 0,
    status: (totals.value.dbOriginalsMissingOnStorage ?? 0) > 0 ? "warning" : "ok",
    message: "Sicher gemappte DB-Originale ohne Treffer im aktuellen Storage-Snapshot.",
  },
  {
    label: "Storage missing in DB",
    count: totals.value.storageOriginalsMissingInDb ?? 0,
    status: (totals.value.storageOriginalsMissingInDb ?? 0) > 0 ? "warning" : "ok",
    message: "Dateien auf Storage ohne passende Original-Referenz in der DB.",
  },
  {
    label: "Orphan derivatives",
    count: totals.value.orphanDerivativesWithoutOriginal ?? 0,
    status: (totals.value.orphanDerivativesWithoutOriginal ?? 0) > 0 ? "warning" : "ok",
    message: "Thumbnails, Sidecars oder Video-Derivate ohne Originaldatei.",
  },
  {
    label: "Zero-byte files",
    count: totals.value.zeroByteFiles ?? 0,
    status: (totals.value.zeroByteFiles ?? 0) > 0 ? "error" : "ok",
    message: "Offensichtlich defekte Dateien aus dem letzten Storage-Scan.",
  },
  {
    label: "Unmapped DB paths",
    count: totals.value.unmappedDatabasePaths ?? 0,
    status: (totals.value.unmappedDatabasePaths ?? 0) > 0 ? "warning" : "ok",
    message: "Legacy-DB-Pfade konnten nicht in die aktuelle Runtime gemappt werden.",
  },
]);
const scanTimestampLabel = computed(() => {
  const value =
    (report.value?.metadata?.latestScanCommittedAt as string | undefined)
    ?? (staleState.value?.latestScanCommittedAt as string | undefined)
    ?? null;
  return displayValue(value);
});
const compareTimestampLabel = computed(() => {
  const value =
    report.value?.generated_at
    ?? (staleState.value?.previousCompareGeneratedAt as string | undefined)
    ?? null;
  return displayValue(value);
});
const staleSummary = computed(() => {
  if (!staleState.value?.stale) {
    return null;
  }
  const staleRoots = Array.isArray(staleState.value.staleRootSlugs)
    ? staleState.value.staleRootSlugs.join(", ")
    : "";
  const missingRoots = Array.isArray(staleState.value.missingRootSlugs)
    ? staleState.value.missingRootSlugs.join(", ")
    : "";
  const scopeText = [staleRoots, missingRoots].filter(Boolean).join(", ");
  if (staleState.value.requiresScan) {
    return scopeText
      ? `Der letzte Compare ist veraltet. Ein frischer Storage-Scan ist für folgende Roots nötig: ${scopeText}.`
      : "Der letzte Compare ist veraltet. Ein frischer Storage-Scan ist nötig.";
  }
  return "Der letzte Compare ist veraltet, weil sich der Storage-Index geändert hat. Ein neuer Compare wird automatisch vorbereitet.";
});
const emptyStateTitle = computed(() => {
  if (flowActive.value) {
    return "Catalog compare is running";
  }
  if (staleState.value?.stale) {
    return staleState.value.requiresScan
      ? "Catalog compare is waiting for a fresh storage scan"
      : "Catalog compare is rebuilding";
  }
  return "No catalog consistency report yet";
});
const emptyStateMessage = computed(() => {
  if (flowActive.value) {
    return "The workflow is currently rebuilding the catalog-backed compare.";
  }
  if (staleSummary.value) {
    return staleSummary.value;
  }
  return "The first validation run starts automatically when this page opens. If no catalog scan exists yet, the storage index is queued first.";
});
const reportSections = computed<ReportSectionViewModel[]>(() =>
  sectionDescriptors.map((descriptor) => {
    const section = report.value?.sections.find(
      (candidate) => candidate.name === descriptor.name,
    ) as CatalogValidationSection | undefined;
    return {
      ...descriptor,
      rows: getSectionRows(report.value, descriptor.name),
      status: toTag(section?.status ?? "unknown"),
      truncated: Boolean(truncated.value[descriptor.name]),
    };
  }),
);
const shouldAutoStart = computed(() => {
  if (consistencyStore.isCatalogStarting || flowActive.value) {
    return false;
  }
  return Boolean(job.value && job.value.jobId == null && !report.value);
});

async function refreshJob(): Promise<void> {
  const latest = await consistencyStore.loadCatalogJob();
  if (!latest || consistencyStore.isCatalogStarting) {
    return;
  }
  if (latest.jobId == null && !isFlowActive(latest) && !consistencyStore.catalogReport) {
    await startValidation(false);
  }
}

async function startValidation(force: boolean): Promise<void> {
  await consistencyStore.startCatalog(force);
}

function startPolling(): void {
  if (pollHandle !== null) {
    return;
  }
  pollHandle = window.setInterval(() => {
    void refreshJob();
  }, 1500);
}

function stopPolling(): void {
  if (pollHandle === null) {
    return;
  }
  window.clearInterval(pollHandle);
  pollHandle = null;
}

watch(flowActive, (active) => {
  if (active) {
    startPolling();
    return;
  }
  stopPolling();
});

watch(shouldAutoStart, (active) => {
  if (active) {
    void startValidation(false);
  }
});

onMounted(async () => {
  await refreshJob();
  if (shouldAutoStart.value) {
    await startValidation(false);
  }
  if (flowActive.value) {
    startPolling();
  }
});

onUnmounted(() => {
  stopPolling();
});
</script>

<style scoped>
.catalog-consistency-panel {
  display: grid;
  gap: 1rem;
}

.catalog-consistency-progress {
  display: grid;
  gap: 0.5rem;
}

.catalog-consistency-progress progress {
  width: 100%;
  height: 0.9rem;
}

.catalog-consistency-grid {
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
}

.catalog-consistency-metadata {
  margin: 0;
}

.catalog-consistency-card {
  display: grid;
  gap: 0.45rem;
  padding: 0.9rem 1rem;
  border: 1px solid #dbe2e8;
  border-radius: 1rem;
  background: #f8fbfd;
}

.catalog-consistency-section {
  display: grid;
  gap: 0.85rem;
}

.catalog-consistency-table-wrapper {
  overflow-x: auto;
}

.catalog-table {
  width: 100%;
  border-collapse: collapse;
}

.catalog-table th,
.catalog-table td {
  padding: 0.75rem;
  border-bottom: 1px solid #dbe2e8;
  text-align: left;
  vertical-align: top;
}

.catalog-table th {
  color: #5c6b77;
  font-size: 0.85rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
</style>
