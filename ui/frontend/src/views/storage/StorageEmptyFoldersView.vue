<template>
  <section class="page">
    <PageHeader
      eyebrow="Storage / Empty Folders"
      title="Empty Folders"
      summary="Scan configured Immich storage roots for empty leaf directories, review recursive orphan parents, and quarantine findings before any permanent delete."
    />
    <RiskNotice
      title="Quarantine-first cleanup"
      message="The detection scan is read-only. Cleanup actions move empty directories into quarantine first so they can be restored before any permanent delete."
    />

    <LoadingState
      v-if="storageEmptyFoldersStore.isLoading && !storageEmptyFoldersStore.scanReport"
      title="Loading empty-folder workspace"
      message="Refreshing the latest scan status and quarantine inventory."
    />
    <ErrorState
      v-else-if="storageEmptyFoldersStore.error && !storageEmptyFoldersStore.scanReport"
      title="Empty-folder workflow unavailable"
      :message="storageEmptyFoldersStore.error"
    />
    <template v-else>
      <p
        v-if="storageEmptyFoldersStore.error && storageEmptyFoldersStore.scanReport"
        class="runtime-blocking-message"
      >
        {{ storageEmptyFoldersStore.error }}
      </p>
      <p
        v-if="storageEmptyFoldersStore.lastActionSummary"
        class="health-card__details"
      >
        {{ storageEmptyFoldersStore.lastActionSummary }}
      </p>
      <p
        v-if="storageEmptyFoldersStore.actionError"
        class="runtime-blocking-message"
      >
        {{ storageEmptyFoldersStore.actionError }}
      </p>

      <section class="settings-grid">
        <article class="panel catalog-panel">
          <div class="settings-section__header">
            <div>
              <h3>Scan controls</h3>
              <p>Run a recursive empty-folder scan and quarantine the current findings in one step when you're ready.</p>
            </div>
          </div>

          <label class="backup-form__field">
            <span>Filter scan by root</span>
            <select v-model="selectedRootValue">
              <option value="">All effective roots</option>
              <option v-for="root in rootOptions" :key="root" :value="root">
                {{ root }}
              </option>
            </select>
          </label>

          <section class="runtime-actions">
            <button
              type="button"
              class="runtime-action"
              :disabled="storageEmptyFoldersStore.isScanning || storageEmptyFoldersStore.isApplyingAction"
              @click="void storageEmptyFoldersStore.runScan()"
            >
              {{ storageEmptyFoldersStore.isScanning ? "Scanning..." : "Run scan" }}
            </button>
            <button
              type="button"
              class="runtime-action runtime-action--secondary"
              :disabled="!hasFindings || storageEmptyFoldersStore.isApplyingAction"
              @click="void storageEmptyFoldersStore.quarantineAll(true)"
            >
              Dry-run quarantine all
            </button>
            <button
              type="button"
              class="runtime-action runtime-action--secondary"
              :disabled="!hasFindings || storageEmptyFoldersStore.isApplyingAction"
              @click="void storageEmptyFoldersStore.quarantineAll(false)"
            >
              Quarantine all
            </button>
            <RouterLink class="runtime-action runtime-action--secondary" :to="{ name: 'storage-empty-folders-quarantine' }">
              Open quarantine
            </RouterLink>
          </section>

          <p class="health-card__summary">
            {{ storageEmptyFoldersStore.scanReport?.summary ?? "Run the first scan to see empty-folder findings." }}
          </p>
          <p class="health-card__details">
            Status: <strong>{{ storageEmptyFoldersStore.scanStatus?.status ?? "idle" }}</strong>
            · Progress: <strong>{{ storageEmptyFoldersStore.scanStatus?.progress ?? 0 }}</strong>
            · Quarantined items: <strong>{{ storageEmptyFoldersStore.quarantinedItems.length }}</strong>
          </p>
        </article>

        <article class="panel catalog-panel">
          <div class="settings-section__header">
            <div>
              <h3>Scan summary</h3>
              <p>Current scan totals for empty leaf directories, orphan parents, and reclaimed directory metadata size.</p>
            </div>
          </div>
          <dl class="runtime-detail__grid">
            <dt>Empty leaf dirs</dt>
            <dd>{{ storageEmptyFoldersStore.scanReport?.total_empty_dirs ?? 0 }}</dd>
            <dt>Orphan parents</dt>
            <dd>{{ storageEmptyFoldersStore.scanReport?.total_orphan_parents ?? 0 }}</dd>
            <dt>Reclaimed bytes</dt>
            <dd>{{ storageEmptyFoldersStore.scanReport?.reclaimed_space_bytes ?? 0 }}</dd>
            <dt>Roots scanned</dt>
            <dd>{{ storageEmptyFoldersStore.scanReport?.roots_scanned ?? 0 }}</dd>
          </dl>
        </article>
      </section>

      <section class="panel catalog-panel">
        <div class="settings-section__header">
          <div>
            <h3>Empty leaf directories</h3>
            <p>Only leaf-level empty directories are listed here. Parent directories that become empty afterward are reported separately below.</p>
          </div>
        </div>

        <EmptyState
          v-if="!storageEmptyFoldersStore.scanReport?.findings.length"
          title="No empty directories reported"
          message="Run a scan to populate the current empty-folder findings."
        />
        <div v-else class="catalog-table-wrapper">
          <table class="catalog-table">
            <thead>
              <tr>
                <th>Root</th>
                <th>Relative path</th>
                <th>Depth</th>
                <th>Last modified</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="finding in storageEmptyFoldersStore.scanReport.findings"
                :key="`${finding.root_slug}:${finding.relative_path}`"
              >
                <td>{{ finding.root_slug }}</td>
                <td>{{ finding.relative_path }}</td>
                <td>{{ finding.depth }}</td>
                <td>{{ finding.last_modified_at ?? "Unknown" }}</td>
                <td class="catalog-table__actions">
                  <button
                    type="button"
                    class="runtime-action runtime-action--secondary"
                    :disabled="storageEmptyFoldersStore.isApplyingAction"
                    @click="void storageEmptyFoldersStore.quarantinePath(finding, true)"
                  >
                    Dry-run
                  </button>
                  <button
                    type="button"
                    class="runtime-action runtime-action--secondary"
                    :disabled="storageEmptyFoldersStore.isApplyingAction"
                    @click="void storageEmptyFoldersStore.quarantinePath(finding, false)"
                  >
                    Quarantine
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section class="panel catalog-panel">
        <div class="settings-section__header">
          <div>
            <h3>Orphan parents</h3>
            <p>These directories are recursively empty because they only contain empty child directories. Clean them up after leaf quarantine if needed.</p>
          </div>
        </div>

        <EmptyState
          v-if="!storageEmptyFoldersStore.scanReport?.orphan_parents.length"
          title="No orphan parents reported"
          message="Recursive empty parents will appear here after a scan when they depend on empty child directories."
        />
        <div v-else class="catalog-table-wrapper">
          <table class="catalog-table">
            <thead>
              <tr>
                <th>Root</th>
                <th>Relative path</th>
                <th>Child dirs</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="finding in storageEmptyFoldersStore.scanReport.orphan_parents"
                :key="`orphan:${finding.root_slug}:${finding.relative_path}`"
              >
                <td>{{ finding.root_slug }}</td>
                <td>{{ finding.relative_path }}</td>
                <td>{{ finding.child_count_before }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted } from "vue";
import { storeToRefs } from "pinia";
import EmptyState from "@/components/common/EmptyState.vue";
import ErrorState from "@/components/common/ErrorState.vue";
import LoadingState from "@/components/common/LoadingState.vue";
import PageHeader from "@/components/common/PageHeader.vue";
import RiskNotice from "@/components/safety/RiskNotice.vue";
import { useStorageEmptyFoldersStore } from "@/stores/storageEmptyFolders";

const storageEmptyFoldersStore = useStorageEmptyFoldersStore();
const { selectedRoot } = storeToRefs(storageEmptyFoldersStore);

const rootOptions = ["uploads", "thumbs", "profile", "video", "library"];
const selectedRootValue = computed({
  get: () => selectedRoot.value ?? "",
  set: (value: string) => {
    selectedRoot.value = value || null;
  },
});
const hasFindings = computed(() => Boolean(storageEmptyFoldersStore.scanReport?.findings.length));

onMounted(async () => {
  await storageEmptyFoldersStore.load();
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

.catalog-table__actions {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}
</style>
