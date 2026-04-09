<template>
  <section class="page">
    <PageHeader
      eyebrow="Storage / Catalog"
      title="Persistent Catalog"
      summary="Cached storage scan, persisted status, zero-byte detection, and reusable inventory for consistency validation."
    />
    <RiskNotice
      title="Read-only storage inventory"
      message="Catalog scans index the mounted storage roots and persist metadata under the manifests path. They do not mutate library files."
    />

    <LoadingState
      v-if="catalogStore.isLoading && !catalogStore.statusReport"
      title="Loading catalog state"
      message="Collecting configured roots, latest snapshots, zero-byte findings, and current scan state."
    />
    <ErrorState
      v-else-if="catalogStore.error"
      title="Catalog state unavailable"
      :message="catalogStore.error"
    />
    <template v-else>
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
              :disabled="catalogStore.isLoading"
              @click="void refresh()"
            >
              Refresh status
            </button>
          </section>

          <p class="health-card__summary">{{ scanSummary }}</p>
          <p v-if="scanMessage" class="health-card__details">{{ scanMessage }}</p>
          <p v-if="scanStats" class="health-card__details">{{ scanStats }}</p>
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
            <dt>Configured roots</dt>
            <dd>{{ catalogStore.rootCount }}</dd>
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

        <article class="panel catalog-panel">
          <div class="settings-section__header">
            <div>
              <h3>Zero-byte summary</h3>
              <p>Obvious defects from the latest committed catalog snapshots.</p>
            </div>
            <StatusTag :status="zeroByteStatus" />
          </div>

          <p class="health-card__summary">{{ zeroByteRows.length }} zero-byte sample rows</p>
          <p class="health-card__details">
            {{ catalogStore.zeroByteReport?.summary ?? "No zero-byte report loaded." }}
          </p>
        </article>
      </section>

      <article class="panel catalog-panel">
        <div class="settings-section__header">
          <div>
            <h3>Configured roots</h3>
            <p>Root registration comes from the runtime container paths, not guessed host paths.</p>
          </div>
        </div>
        <section v-if="catalogStore.roots.length" class="runtime-findings">
          <article
            v-for="root in catalogStore.roots"
            :key="root.slug"
            class="runtime-finding"
            :class="{ 'catalog-root--selected': root.slug === catalogStore.selectedRoot }"
          >
            <div class="runtime-finding__header">
              <strong>{{ root.slug }}</strong>
              <StatusTag :status="root.slug === catalogStore.selectedRoot ? 'ok' : 'unknown'" />
            </div>
            <span>{{ root.absolute_path }}</span>
            <small>{{ root.root_type }} via {{ root.setting_name }}</small>
          </article>
        </section>
        <EmptyState
          v-else
          title="No catalog roots configured"
          message="Set at least one Immich storage path in the runtime environment before using the persistent catalog."
        />
      </article>

      <article class="panel catalog-panel">
        <div class="settings-section__header">
          <div>
            <h3>Zero-byte files</h3>
            <p>Read-only findings from the latest committed snapshot for the selected scope.</p>
          </div>
        </div>

        <EmptyState
          v-if="!zeroByteRows.length"
          title="No zero-byte files found"
          message="Run a catalog scan to populate the persisted inventory, then review findings here."
        />
        <div v-else class="catalog-table-wrapper">
          <table class="catalog-table">
            <thead>
              <tr>
                <th>Root</th>
                <th>Relative path</th>
                <th>Size</th>
                <th>Snapshot</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in zeroByteRows" :key="`${row.root_slug}:${row.relative_path}`">
                <td>{{ row.root_slug }}</td>
                <td>{{ row.relative_path }}</td>
                <td>{{ row.size_bytes }} bytes</td>
                <td>#{{ row.generation }}</td>
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
  CatalogValidationReport,
  CatalogZeroByteRow,
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
  if (["pending", "running", "paused", "WARN", "warn", "partial"].includes(value)) {
    return "warning";
  }
  if (["failed", "FAIL", "fail", "canceled"].includes(value)) {
    return "error";
  }
  return "unknown";
}

const zeroByteRows = computed<CatalogZeroByteRow[]>(() =>
  getSectionRows<CatalogZeroByteRow>(catalogStore.zeroByteReport, "ZERO_BYTE_FILES"),
);
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
    scanProgress.value.phase === "prepare"
    && typeof scanProgress.value.directoriesDiscovered === "number"
  ) {
    return `Counting directories: ${scanProgress.value.directoriesDiscovered}`;
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
const scanDisabled = computed(() => !catalogStore.roots.length || catalogStore.isScanning || catalogStore.scanJobActive);
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
const zeroByteStatus = computed(() => (zeroByteRows.value.length ? "error" : "ok"));

async function runScan(): Promise<void> {
  await catalogStore.startScan(true);
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
  }, 1500);
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
</style>
