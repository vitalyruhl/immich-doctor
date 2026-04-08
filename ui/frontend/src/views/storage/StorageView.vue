<template>
  <section class="page">
    <PageHeader
      eyebrow="Storage / Catalog"
      title="Persistent Catalog"
      summary="Phase 1 inventory scan, persisted status, and zero-byte findings against mounted Immich storage."
    />
    <RiskNotice
      title="Phase 1 is inventory-only"
      message="Catalog scans write metadata under the mounted manifests path and do not quarantine, repair, or mutate library files."
    />

    <LoadingState
      v-if="catalogStore.isLoading && !catalogStore.statusReport"
      title="Loading catalog state"
      message="Collecting configured roots, latest snapshots, and zero-byte findings from the persistent catalog."
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
              <h3>Catalog scan</h3>
              <p>Start a non-destructive inventory pass for one configured storage root.</p>
            </div>
            <StatusTag :status="scanPanelStatus" />
          </div>

          <label class="backup-form__field">
            <span>Storage root</span>
            <select :value="selectedRootValue" @change="onRootChange">
              <option value="">All roots for status view</option>
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
              @click="runScan"
            >
              {{ catalogStore.isScanning ? "Running scan..." : "Run catalog scan" }}
            </button>
            <button
              type="button"
              class="runtime-action runtime-action--secondary"
              :disabled="catalogStore.isLoading"
              @click="refresh"
            >
              Refresh status
            </button>
          </section>

          <p v-if="scanBlockedMessage" class="runtime-blocking-message">{{ scanBlockedMessage }}</p>
          <p v-if="catalogStore.scanError" class="runtime-blocking-message">{{ catalogStore.scanError }}</p>
          <p class="health-card__details">
            {{ catalogStore.scanReport?.summary ?? catalogStore.statusReport?.summary ?? "No catalog activity has been loaded yet." }}
          </p>
        </article>

        <article class="panel catalog-panel">
          <div class="settings-section__header">
            <div>
              <h3>Status summary</h3>
              <p>Latest snapshot and scan-session visibility for the current scope.</p>
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
              <p>Immediate Phase 1 defects surfaced from the latest committed snapshots.</p>
            </div>
            <StatusTag :status="zeroByteStatus" />
          </div>

          <p class="health-card__summary">{{ zeroByteRows.length }} zero-byte files</p>
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
import { computed, onMounted } from "vue";
import EmptyState from "@/components/common/EmptyState.vue";
import ErrorState from "@/components/common/ErrorState.vue";
import LoadingState from "@/components/common/LoadingState.vue";
import PageHeader from "@/components/common/PageHeader.vue";
import StatusTag from "@/components/common/StatusTag.vue";
import RiskNotice from "@/components/safety/RiskNotice.vue";
import { useCatalogStore } from "@/stores/catalog";
import type {
  CatalogSessionRow,
  CatalogSnapshotRow,
  CatalogValidationReport,
  CatalogZeroByteRow,
} from "@/api/types/catalog";

const catalogStore = useCatalogStore();

function getSectionRows<T>(
  report: CatalogValidationReport | null,
  sectionName: string,
): T[] {
  const section = report?.sections.find((candidate) => candidate.name === sectionName);
  if (!section) {
    return [];
  }
  return section.rows as T[];
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
      latestSnapshots.value.find((row) => row.root_slug === catalogStore.selectedRoot)
      ?? null
    );
  }
  return latestSnapshots.value.find((row) => row.snapshot_id !== null) ?? latestSnapshots.value[0] ?? null;
});

const latestSession = computed<CatalogSessionRow | null>(() => {
  if (catalogStore.selectedRoot) {
    return (
      latestSessions.value.find((row) => row.root_slug === catalogStore.selectedRoot)
      ?? null
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

const scanBlockedMessage = computed(() => {
  if (!catalogStore.roots.length) {
    return "No configured storage roots are available for catalog scanning.";
  }
  if (!catalogStore.selectedRoot && catalogStore.roots.length > 1) {
    return "Select a single storage root before starting a catalog scan.";
  }
  return null;
});

const scanDisabled = computed(() => Boolean(scanBlockedMessage.value) || catalogStore.isScanning);

function toUiStatus(value: string | null | undefined): "ok" | "warning" | "error" | "unknown" {
  if (!value) {
    return "unknown";
  }
  if (value === "completed" || value === "committed" || value === "PASS") {
    return "ok";
  }
  if (value === "running" || value === "paused" || value === "WARN") {
    return "warning";
  }
  if (value === "failed" || value === "FAIL" || value === "fail") {
    return "error";
  }
  return "unknown";
}

const scanPanelStatus = computed(() => toUiStatus(catalogStore.scanReport?.status));
const latestSessionStatus = computed(() => toUiStatus(latestSession.value?.status));
const zeroByteStatus = computed(() => (zeroByteRows.value.length ? "error" : "ok"));

async function runScan(): Promise<void> {
  await catalogStore.scan(catalogStore.selectedRoot);
}

async function refresh(): Promise<void> {
  await catalogStore.refresh();
}

async function onRootChange(event: Event): Promise<void> {
  const target = event.target as HTMLSelectElement;
  catalogStore.setSelectedRoot(target.value || null);
  await catalogStore.refresh();
}

onMounted(async () => {
  await catalogStore.load();
});
</script>

<style scoped>
.catalog-panel {
  display: grid;
  gap: 0.85rem;
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
