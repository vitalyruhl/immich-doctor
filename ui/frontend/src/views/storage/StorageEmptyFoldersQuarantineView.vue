<template>
  <section class="page">
    <PageHeader
      eyebrow="Storage / Quarantine"
      title="Empty-Folder Quarantine"
      summary="Restore quarantined empty directories back to their original locations or delete them permanently once you're sure they are no longer needed."
    />
    <DisclaimerBanner />

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

    <section class="panel catalog-panel">
      <div class="settings-section__header">
        <div>
          <h3>Quarantine sessions</h3>
          <p>Each session preserves the original path, root, and directory metadata so the folder can be restored before final deletion.</p>
        </div>
      </div>

      <EmptyState
        v-if="!storageEmptyFoldersStore.groupedSessions.length"
        title="Quarantine is empty"
        message="Quarantined empty folders will appear here after a quarantine action."
      />
      <div v-else class="quarantine-sessions">
        <article
          v-for="session in storageEmptyFoldersStore.groupedSessions"
          :key="session.sessionId"
          class="runtime-actor-card"
        >
          <div class="runtime-actor-card__header">
            <div>
              <p class="runtime-actor-card__eyebrow">Session</p>
              <h4>{{ session.sessionId }}</h4>
            </div>
            <div class="catalog-table__actions">
              <button
                type="button"
                class="runtime-action runtime-action--secondary"
                :disabled="storageEmptyFoldersStore.isApplyingAction"
                @click="void storageEmptyFoldersStore.restoreAll(session.sessionId)"
              >
                Restore all
              </button>
              <button
                type="button"
                class="runtime-action runtime-action--secondary"
                :disabled="storageEmptyFoldersStore.isApplyingAction"
                @click="void storageEmptyFoldersStore.deleteAll(session.sessionId)"
              >
                Delete all
              </button>
            </div>
          </div>

          <div class="catalog-table-wrapper">
            <table class="catalog-table">
              <thead>
                <tr>
                  <th>Root</th>
                  <th>Relative path</th>
                  <th>Original path</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="item in session.items"
                  :key="item.quarantine_item_id"
                >
                  <td>{{ item.root_slug }}</td>
                  <td>{{ item.relative_path }}</td>
                  <td>{{ item.original_path }}</td>
                  <td class="catalog-table__actions">
                    <button
                      type="button"
                      class="runtime-action runtime-action--secondary"
                      :disabled="storageEmptyFoldersStore.isApplyingAction"
                      @click="void storageEmptyFoldersStore.restoreItem(item, false)"
                    >
                      Restore
                    </button>
                    <button
                      type="button"
                      class="runtime-action runtime-action--secondary"
                      :disabled="storageEmptyFoldersStore.isApplyingAction"
                      @click="void storageEmptyFoldersStore.deleteItem(item, false)"
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </article>
      </div>
    </section>
  </section>
</template>

<script setup lang="ts">
import { onMounted } from "vue";
import DisclaimerBanner from "@/components/safety/DisclaimerBanner.vue";
import EmptyState from "@/components/common/EmptyState.vue";
import PageHeader from "@/components/common/PageHeader.vue";
import { useStorageEmptyFoldersStore } from "@/stores/storageEmptyFolders";

const storageEmptyFoldersStore = useStorageEmptyFoldersStore();

onMounted(async () => {
  await storageEmptyFoldersStore.load();
});
</script>

<style scoped>
.catalog-panel {
  display: grid;
  gap: 0.85rem;
}

.quarantine-sessions {
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
  justify-content: space-between;
  gap: 0.75rem;
  align-items: start;
}

.runtime-actor-card__eyebrow {
  margin: 0;
  color: #5c6b77;
  font-size: 0.8rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.runtime-actor-card__header h4 {
  margin: 0.1rem 0 0;
}
</style>
