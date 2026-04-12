<template>
  <section class="panel catalog-consistency-panel">
    <div class="settings-section__header">
      <div>
        <h3>Catalog-backed consistency snapshot</h3>
        <p>
          This page reads the latest cached storage-vs-database compare and only
          polls while a background consistency run is active.
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
        {{
          flowActive
            ? "Consistency running..."
            : report
              ? "Run new compare"
              : "Start consistency"
        }}
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
      <dt>Last snapshot</dt>
      <dd>{{ scanTimestampLabel }}</dd>
      <dt>Compare built at</dt>
      <dd>{{ compareTimestampLabel }}</dd>
      <dt>Result source</dt>
      <dd>{{ resultSourceLabel }}</dd>
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
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, watch } from "vue";
import EmptyState from "@/components/common/EmptyState.vue";
import StatusTag from "@/components/common/StatusTag.vue";
import { useConsistencyStore } from "@/stores/consistency";
import type { CatalogJobProgress, CatalogWorkflowJobRecord } from "@/api/types/catalog";

type HealthTag = "ok" | "warning" | "error" | "unknown";

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
const currentSummary = computed(
  () => job.value?.summary ?? "No cached catalog consistency snapshot is available yet.",
);
const progressMessage = computed(() => progress.value?.message ?? null);
const progressStats = computed(() => {
  if (!progress.value) {
    return null;
  }
  if (
    progress.value.phase === "prepare" &&
    typeof progress.value.directoriesDiscovered === "number"
  ) {
    return `Counting directories: ${progress.value.directoriesDiscovered}`;
  }
  if (
    typeof progress.value.directoriesTotal === "number" &&
    typeof progress.value.directoriesCompleted === "number"
  ) {
    return `Directories: ${progress.value.directoriesCompleted} / ${progress.value.directoriesTotal}`;
  }
  if (
    typeof progress.value.directoriesCompleted === "number" &&
    typeof progress.value.pendingDirectories === "number"
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
const summaryCards = computed<SummaryCardViewModel[]>(() => [
  {
    label: "DB missing in storage",
    count: totals.value.dbOriginalsMissingOnStorage ?? 0,
    status: (totals.value.dbOriginalsMissingOnStorage ?? 0) > 0 ? "warning" : "ok",
    message: "Assets whose DB original path does not match the current uploads snapshot.",
  },
  {
    label: "Storage missing in DB",
    count: totals.value.storageOriginalsMissingInDb ?? 0,
    status: (totals.value.storageOriginalsMissingInDb ?? 0) > 0 ? "warning" : "ok",
    message: "Files on storage without a matching original DB reference.",
  },
  {
    label: "Orphan derivatives",
    count: totals.value.orphanDerivativesWithoutOriginal ?? 0,
    status: (totals.value.orphanDerivativesWithoutOriginal ?? 0) > 0 ? "warning" : "ok",
    message: "Preview, thumbnail, sidecar, or video derivatives without the original.",
  },
  {
    label: "Zero-byte files",
    count: totals.value.zeroByteFiles ?? 0,
    status: (totals.value.zeroByteFiles ?? 0) > 0 ? "warning" : "ok",
    message: "Snapshot findings whose size is zero bytes.",
  },
  {
    label: "Path warnings",
    count: totals.value.unmappedDatabasePaths ?? 0,
    status: (totals.value.unmappedDatabasePaths ?? 0) > 0 ? "warning" : "ok",
    message: "Database paths that could not be mapped cleanly into runtime roots.",
  },
]);
const scanTimestampLabel = computed(() => {
  const value =
    (report.value?.metadata?.latestScanCommittedAt as string | undefined) ??
    (staleState.value?.latestScanCommittedAt as string | undefined) ??
    null;
  return displayValue(value);
});
const compareTimestampLabel = computed(() => {
  const value =
    report.value?.generated_at ??
    (staleState.value?.previousCompareGeneratedAt as string | undefined) ??
    null;
  return displayValue(value);
});
const resultSourceLabel = computed(() => {
  if (flowActive.value) {
    return "Cached snapshot with active refresh";
  }
  if (report.value) {
    return "Latest completed snapshot";
  }
  return "No snapshot available yet";
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
      ? `The last compare is stale. A fresh storage scan is required for: ${scopeText}.`
      : "The last compare is stale. A fresh storage scan is required.";
  }
  return "The last compare is stale because the storage index changed. A new compare must be started explicitly.";
});
const emptyStateTitle = computed(() => {
  if (flowActive.value) {
    return "Catalog compare is running";
  }
  if (staleState.value?.stale) {
    return staleState.value.requiresScan
      ? "Catalog compare is waiting for a fresh storage scan"
      : "Catalog compare is stale";
  }
  return "No snapshot available yet";
});
const emptyStateMessage = computed(() => {
  if (flowActive.value) {
    return "A background consistency run is active. The page will poll until it completes.";
  }
  if (staleSummary.value) {
    return staleSummary.value;
  }
  return "No completed catalog-backed consistency snapshot has been recorded yet. Start a run explicitly when you want to refresh the compare.";
});

async function refreshJob(): Promise<void> {
  await consistencyStore.loadCatalogJob();
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
  }, 3000);
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

onMounted(async () => {
  await refreshJob();
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
</style>
