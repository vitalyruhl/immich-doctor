<template>
  <section class="page">
    <PageHeader
      eyebrow="Storage / Catalog"
      title="Persistent Catalog"
      summary="Cached storage scan, persisted status, and reusable inventory for consistency validation."
    />
    <RiskNotice
      title="Read-only storage inventory"
      message="Catalog scans index the mounted storage roots and persist metadata under the manifests path. They do not mutate library files."
    />

    <LoadingState
      v-if="catalogStore.isLoading && !catalogStore.statusReport"
      title="Loading catalog state"
      message="Collecting configured roots, latest snapshots, and current scan state."
    />
    <ErrorState
      v-else-if="catalogStore.error && !catalogStore.statusReport"
      title="Catalog state unavailable"
      :message="catalogStore.error"
    />
    <template v-else>
      <p
        v-if="catalogStore.error && catalogStore.statusReport"
        class="runtime-blocking-message"
      >
        {{ catalogStore.error }}
      </p>
      <section class="settings-grid">
        <article class="panel catalog-panel">
          <div class="settings-section__header">
            <div>
              <h3>Storage index scan</h3>
              <p>Scan all configured storage roots once, cache the inventory, and reuse it until a rescan is requested.</p>
            </div>
            <StatusTag :status="scanPanelStatus" />
          </div>

          <label class="backup-form__field">
            <span>Filter status by root</span>
            <select :value="selectedRootValue" @change="onRootChange">
              <option value="">All configured roots</option>
              <option
                v-for="root in catalogStore.roots"
                :key="root.slug"
                :value="root.slug"
              >
                {{ root.slug }} ({{ root.root_type }})
              </option>
            </select>
          </label>

          <section class="runtime-actions">
            <button
              type="button"
              class="runtime-action"
              :disabled="scanDisabled"
              @click="void runScan()"
            >
              {{ scanButtonLabel }}
            </button>
            <button
              type="button"
              class="runtime-action runtime-action--secondary"
              :disabled="pauseDisabled"
              @click="void pauseScan()"
            >
              Pause
            </button>
            <button
              type="button"
              class="runtime-action runtime-action--secondary"
              :disabled="resumeDisabled"
              @click="void resumeScan()"
            >
              Resume
            </button>
            <button
              type="button"
              class="runtime-action runtime-action--secondary"
              :disabled="stopDisabled"
              @click="void stopScan()"
            >
              Stop
            </button>
            <button
              type="button"
              class="runtime-action runtime-action--secondary"
              :disabled="catalogStore.isLoading"
              @click="void refresh()"
            >
              Refresh status
            </button>
          </section>

          <p class="health-card__summary">{{ scanSummary }}</p>
          <p v-if="scanMessage" class="health-card__details">{{ scanMessage }}</p>
          <p v-if="scanStats" class="health-card__details">{{ scanStats }}</p>
          <p class="health-card__details">
            Scan state: <strong>{{ scanRuntimeState }}</strong>
            · Configured workers: <strong>{{ configuredWorkerCount }}</strong>
            · Active workers: <strong>{{ activeWorkerCount }}</strong>
          </p>
          <p class="health-card__details">{{ workerResizeMessage }}</p>
          <section class="runtime-actors">
            <div class="settings-section__header runtime-actors__header">
              <div>
                <h4>Runtime actors</h4>
                <p>Collector and workers are controlled individually. Each actor can be paused, resumed, or stopped without affecting the global scan controls above.</p>
              </div>
            </div>
            <div v-if="scanActors.length" class="runtime-actors__grid">
              <article
                v-for="actor in scanActors"
                :key="actor.actorId"
                class="runtime-actor-card"
              >
                <div class="runtime-actor-card__header">
                  <div>
                    <p class="runtime-actor-card__eyebrow">{{ actor.role }}</p>
                    <h5>{{ actorLabel(actor) }}</h5>
                  </div>
                  <span class="scan-actor-state" :class="`scan-actor-state--${actorStateTone(actor.state)}`">
                    {{ actor.state }}
                  </span>
                </div>
                <dl class="runtime-actor-card__details">
                  <dt>Current path</dt>
                  <dd>{{ actor.currentRelativePath ?? actorPathLabel(actor) }}</dd>
                </dl>
                <section class="runtime-actions runtime-actions--compact">
                  <button
                    type="button"
                    class="runtime-action runtime-action--secondary"
                    :disabled="pauseActorDisabled(actor)"
                    @click="void pauseActor(actor.actorId)"
                  >
                    Pause
                  </button>
                  <button
                    type="button"
                    class="runtime-action runtime-action--secondary"
                    :disabled="resumeActorDisabled(actor)"
                    @click="void resumeActor(actor.actorId)"
                  >
                    Resume
                  </button>
                  <button
                    type="button"
                    class="runtime-action runtime-action--secondary"
                    :disabled="stopActorDisabled(actor)"
                    @click="void stopActor(actor.actorId)"
                  >
                    Stop
                  </button>
                </section>
              </article>
            </div>
            <p v-else class="health-card__details">No runtime actors are currently reported.</p>
          </section>
          <p v-if="catalogStore.scanError" class="runtime-blocking-message">{{ catalogStore.scanError }}</p>

          <section v-if="scanProgressPercent !== null" class="catalog-progress">
            <progress :value="scanProgressPercent" max="100" />
            <strong>{{ scanProgressPercent.toFixed(1) }}%</strong>
          </section>
        </article>

        <article class="panel catalog-panel">
          <div class="settings-section__header">
            <div>
              <h3>Status summary</h3>
              <p>Latest committed snapshot and latest scan session for the current filter.</p>
            </div>
            <StatusTag :status="latestSessionStatus" />
          </div>

          <dl class="runtime-detail__grid">
            <dt>Scope</dt>
            <dd>{{ selectedRootLabel }}</dd>
            <dt>Latest snapshot</dt>
            <dd>{{ latestSnapshotLabel }}</dd>
            <dt>Files indexed</dt>
            <dd>{{ latestSnapshot?.item_count ?? 0 }}</dd>
            <dt>Latest session</dt>
            <dd>{{ latestSession?.status ?? "No session recorded" }}</dd>
            <dt>Directories completed</dt>
            <dd>{{ latestSession?.directories_completed ?? 0 }}</dd>
          </dl>
        </article>
      </section>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, watch } from "vue";
import EmptyState from "@/components/common/EmptyState.vue";
import ErrorState from "@/components/common/ErrorState.vue";
import LoadingState from "@/components/common/LoadingState.vue";
import PageHeader from "@/components/common/PageHeader.vue";
import StatusTag from "@/components/common/StatusTag.vue";
import RiskNotice from "@/components/safety/RiskNotice.vue";
import { useCatalogStore } from "@/stores/catalog";
import type {
  CatalogJobProgress,
  CatalogSessionRow,
  CatalogSnapshotRow,
  CatalogScanRuntimeActor,
  CatalogValidationReport,
} from "@/api/types/catalog";

const catalogStore = useCatalogStore();
let pollHandle: number | null = null;

function getSectionRows<T>(
  report: CatalogValidationReport | null,
  sectionName: string,
): T[] {
  const section = report?.sections.find((candidate) => candidate.name === sectionName);
  return section ? (section.rows as T[]) : [];
}

function toUiStatus(value: string | null | undefined): "ok" | "warning" | "error" | "unknown" {
  if (!value) {
    return "unknown";
  }
  if (["completed", "committed", "PASS", "pass"].includes(value)) {
    return "ok";
  }
  if (
    ["pending", "running", "pausing", "paused", "resuming", "stopping", "WARN", "warn", "partial"].includes(value)
  ) {
    return "warning";
  }
  if (["failed", "FAIL", "fail", "canceled", "stopped"].includes(value)) {
    return "error";
  }
  return "unknown";
}

function actorStateTone(value: string | null | undefined): "ok" | "warning" | "error" | "unknown" {
  if (!value) {
    return "unknown";
  }
  if (["running", "waiting", "completed"].includes(value)) {
    return "ok";
  }
  if (["pausing", "paused", "resuming", "stopping"].includes(value)) {
    return "warning";
  }
  if (["failed", "stopped"].includes(value)) {
    return "error";
  }
  return "unknown";
}

const latestSnapshots = computed<CatalogSnapshotRow[]>(() =>
  getSectionRows<CatalogSnapshotRow>(catalogStore.statusReport, "LATEST_SNAPSHOTS"),
);
const latestSessions = computed<CatalogSessionRow[]>(() =>
  getSectionRows<CatalogSessionRow>(catalogStore.statusReport, "SCAN_SESSIONS"),
);
const latestSnapshot = computed<CatalogSnapshotRow | null>(() => {
  if (catalogStore.selectedRoot) {
    return (
      latestSnapshots.value.find((row) => row.root_slug === catalogStore.selectedRoot) ?? null
    );
  }
  return latestSnapshots.value.find((row) => row.snapshot_id !== null) ?? latestSnapshots.value[0] ?? null;
});
const latestSession = computed<CatalogSessionRow | null>(() => {
  if (catalogStore.selectedRoot) {
    return (
      latestSessions.value.find((row) => row.root_slug === catalogStore.selectedRoot) ?? null
    );
  }
  return latestSessions.value[0] ?? null;
});
const latestSnapshotLabel = computed(() => {
  if (!latestSnapshot.value?.snapshot_id) {
    return "No committed snapshot";
  }
  return `generation ${latestSnapshot.value.generation ?? "?"} (${latestSnapshot.value.status ?? "unknown"})`;
});
const selectedRootLabel = computed(() => catalogStore.selectedRoot ?? "All configured roots");
const selectedRootValue = computed(() => catalogStore.selectedRoot ?? "");
const scanProgress = computed<CatalogJobProgress | null>(() => {
  const candidate = catalogStore.scanJob?.result?.progress;
  return candidate && typeof candidate === "object" ? (candidate as CatalogJobProgress) : null;
});
const scanRuntimeState = computed(() => catalogStore.scanRuntime?.scanState ?? "idle");
const configuredWorkerCount = computed(() => catalogStore.scanRuntime?.configuredWorkerCount ?? 0);
const activeWorkerCount = computed(() => catalogStore.scanRuntime?.activeWorkerCount ?? 0);
const scanActors = computed<CatalogScanRuntimeActor[]>(() => {
  const actors = catalogStore.scanRuntime?.actors;
  if (!Array.isArray(actors)) {
    return [];
  }
  return [...actors].sort((left, right) => {
    if (left.role !== right.role) {
      return left.role === "collector" ? -1 : 1;
    }
    return left.actorId.localeCompare(right.actorId, undefined, { numeric: true });
  });
});
const workerResizeMessage = computed(() => {
  const resize = catalogStore.scanRuntime?.workerResize;
  if (!resize || resize.supported) {
    return "Runtime worker resize support: available.";
  }
  return resize.message ?? "Runtime worker resize support: next-run-only.";
});
const scanProgressPercent = computed<number | null>(() => {
  const value = scanProgress.value?.percent;
  return typeof value === "number" ? value : null;
});
const scanMessage = computed(() => scanProgress.value?.message ?? null);
const scanStats = computed(() => {
  if (!scanProgress.value) {
    return null;
  }
  if (
    scanProgress.value.phase === "collect"
    && typeof scanProgress.value.directoriesDiscovered === "number"
  ) {
    return `Collecting directories: ${scanProgress.value.directoriesDiscovered}`;
  }
  if (
    typeof scanProgress.value.directoriesTotal === "number"
    && typeof scanProgress.value.directoriesCompleted === "number"
  ) {
    return `Directories: ${scanProgress.value.directoriesCompleted} / ${scanProgress.value.directoriesTotal}`;
  }
  if (
    typeof scanProgress.value.directoriesCompleted === "number"
    && typeof scanProgress.value.pendingDirectories === "number"
  ) {
    const total = scanProgress.value.directoriesCompleted + scanProgress.value.pendingDirectories;
    return `Directories: ${scanProgress.value.directoriesCompleted} / ${total}`;
  }
  if (typeof scanProgress.value.current === "number" && typeof scanProgress.value.total === "number") {
    return `${scanProgress.value.current} of ${scanProgress.value.total}`;
  }
  return null;
});
const scanSummary = computed(() => {
  if (catalogStore.scanJob?.jobId || catalogStore.scanJobActive) {
    return catalogStore.scanJob?.summary ?? "Catalog scan is active.";
  }
  if (
    catalogStore.scanCoverage?.requiresScan
    && Array.isArray(catalogStore.scanCoverage.missingRootSlugs)
    && catalogStore.scanCoverage.missingRootSlugs.length
  ) {
    return `Catalog scan is required for: ${catalogStore.scanCoverage.missingRootSlugs.join(", ")}.`;
  }
  return (
    catalogStore.scanJob?.summary
    ?? catalogStore.statusReport?.summary
    ?? "No catalog activity has been loaded yet."
  );
});
const scanButtonLabel = computed(() => {
  if (catalogStore.scanJobActive) {
    return "Storage scan running...";
  }
  if (catalogStore.hasCommittedSnapshot) {
    return "Rescan storage index";
  }
  return "Start storage index";
});
const scanDisabled = computed(
  () => !catalogStore.roots.length || catalogStore.isScanning || catalogStore.scanJobActive,
);
const pauseDisabled = computed(
  () => !["running", "resuming"].includes(scanRuntimeState.value) || catalogStore.isLifecycleTransitioning,
);
const resumeDisabled = computed(
  () => !["paused", "stopped", "pausing"].includes(scanRuntimeState.value) || catalogStore.isLifecycleTransitioning,
);
const stopDisabled = computed(
  () => !["running", "pausing", "resuming"].includes(scanRuntimeState.value) || catalogStore.isLifecycleTransitioning,
);
const scanPanelStatus = computed(() => {
  if (catalogStore.scanError) {
    return "error";
  }
  if (catalogStore.scanJobActive) {
    return "warning";
  }
  return toUiStatus(catalogStore.scanJob?.state ?? latestSession.value?.status);
});
const latestSessionStatus = computed(() => toUiStatus(latestSession.value?.status));
function actorLabel(actor: CatalogScanRuntimeActor): string {
  if (actor.role === "collector") {
    return "Collector";
  }
  const workerMatch = actor.actorId.match(/^worker-(\d+)$/);
  if (workerMatch) {
    return `Worker ${workerMatch[1]}`;
  }
  return actor.actorId;
}

function actorPathLabel(actor: CatalogScanRuntimeActor): string {
  if (actor.state === "waiting") {
    return actor.role === "collector"
      ? "Waiting for the next directory batch"
      : "Waiting for the next directory";
  }
  if (actor.state === "completed") {
    return "Completed";
  }
  if (actor.state === "paused") {
    return "Paused";
  }
  if (actor.state === "stopped") {
    return "Stopped";
  }
  return "No active path";
}

function pauseActorDisabled(actor: CatalogScanRuntimeActor): boolean {
  return (
    catalogStore.isLifecycleTransitioning
    || catalogStore.isActorTransitioning(actor.actorId)
    || ["paused", "stopped", "stopping", "completed", "failed"].includes(actor.state)
  );
}

function resumeActorDisabled(actor: CatalogScanRuntimeActor): boolean {
  return (
    catalogStore.isLifecycleTransitioning
    || catalogStore.isActorTransitioning(actor.actorId)
    || !["paused", "pausing"].includes(actor.state)
  );
}

function stopActorDisabled(actor: CatalogScanRuntimeActor): boolean {
  return (
    catalogStore.isLifecycleTransitioning
    || catalogStore.isActorTransitioning(actor.actorId)
    || ["stopped", "stopping", "completed"].includes(actor.state)
  );
}
async function runScan(): Promise<void> {
  await catalogStore.startScan(true);
}

async function pauseScan(): Promise<void> {
  await catalogStore.pauseScan();
}

async function resumeScan(): Promise<void> {
  await catalogStore.resumeScan();
}

async function stopScan(): Promise<void> {
  await catalogStore.stopScan();
}

async function pauseActor(actorId: string): Promise<void> {
  await catalogStore.pauseScanActor(actorId);
}

async function resumeActor(actorId: string): Promise<void> {
  await catalogStore.resumeScanActor(actorId);
}

async function stopActor(actorId: string): Promise<void> {
  await catalogStore.stopScanActor(actorId);
}

async function refresh(): Promise<void> {
  await catalogStore.refresh();
}

async function onRootChange(event: Event): Promise<void> {
  const target = event.target as HTMLSelectElement;
  catalogStore.setSelectedRoot(target.value || null);
  await catalogStore.refresh();
}

function startPolling(): void {
  if (pollHandle !== null) {
    return;
  }
  pollHandle = window.setInterval(() => {
    void catalogStore.refreshScanJob();
  }, 3000);
}

function stopPolling(): void {
  if (pollHandle === null) {
    return;
  }
  window.clearInterval(pollHandle);
  pollHandle = null;
}

watch(
  () => catalogStore.scanJobActive,
  (active) => {
    if (active) {
      startPolling();
      return;
    }
    stopPolling();
  },
);

onMounted(async () => {
  await catalogStore.load();
  if (catalogStore.shouldAutoStartScan) {
    await catalogStore.startScan(false);
  }
  if (catalogStore.scanJobActive) {
    startPolling();
  }
});

onUnmounted(() => {
  stopPolling();
});
</script>

<style scoped>
.catalog-panel {
  display: grid;
  gap: 0.85rem;
}

.catalog-progress {
  display: grid;
  gap: 0.5rem;
}

.catalog-progress progress {
  width: 100%;
  height: 0.9rem;
}

.catalog-table-wrapper {
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

.catalog-root--selected {
  border-color: #13202a;
  background: #eef5fb;
}

.runtime-actors {
  display: grid;
  gap: 0.75rem;
}

.runtime-actors__header p {
  margin: 0.25rem 0 0;
}

.runtime-actors__grid {
  display: grid;
  gap: 0.75rem;
}

.runtime-actor-card {
  display: grid;
  gap: 0.75rem;
  padding: 0.9rem;
  border: 1px solid #dbe2e8;
  border-radius: 0.75rem;
  background: #f8fbfd;
}

.runtime-actor-card__header {
  display: flex;
  align-items: start;
  justify-content: space-between;
  gap: 0.75rem;
}

.runtime-actor-card__eyebrow {
  margin: 0;
  color: #5c6b77;
  font-size: 0.8rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.runtime-actor-card__header h5 {
  margin: 0.1rem 0 0;
  font-size: 1rem;
}

.runtime-actor-card__details {
  display: grid;
  grid-template-columns: max-content minmax(0, 1fr);
  gap: 0.35rem 0.85rem;
  margin: 0;
}

.runtime-actor-card__details dt {
  color: #5c6b77;
  font-size: 0.85rem;
}

.runtime-actor-card__details dd {
  margin: 0;
  overflow-wrap: anywhere;
}

.runtime-actions--compact {
  flex-wrap: wrap;
}

.scan-actor-state {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 6.5rem;
  padding: 0.3rem 0.65rem;
  border-radius: 999px;
  font-size: 0.8rem;
  font-weight: 700;
  text-transform: uppercase;
}

.scan-actor-state--ok {
  background: #dff4e7;
  color: #155b35;
}

.scan-actor-state--warning {
  background: #fff1cf;
  color: #8b5b00;
}

.scan-actor-state--error {
  background: #fde4e1;
  color: #8f2f24;
}

.scan-actor-state--unknown {
  background: #e8eef2;
  color: #44515b;
}
</style>
