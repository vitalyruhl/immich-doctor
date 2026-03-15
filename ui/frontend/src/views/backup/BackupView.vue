<template>
  <section class="page">
    <PageHeader
      eyebrow="Backup"
      title="Backup"
      summary="Snapshot metadata is visible here before broader repair flows depend on it."
    />
    <RiskNotice
      title="Files-only snapshot foundation"
      message="Current snapshots are real and persisted, but they are still files-only unless a later paired DB snapshot phase is implemented."
    />

    <LoadingState
      v-if="backupStore.isLoading && !backupStore.snapshots"
      title="Loading backup safety data"
      message="Collecting persisted backup snapshots and quarantine foundation status."
    />
    <ErrorState
      v-else-if="backupStore.error"
      title="Backup safety data unavailable"
      :message="backupStore.error"
    />
    <template v-else>
      <section class="settings-grid">
        <article class="panel">
          <div class="settings-section__header">
            <div>
              <h3>Snapshot foundation</h3>
              <p>Persisted backup snapshot manifests and current coverage visibility.</p>
            </div>
          </div>
          <p class="health-card__summary">{{ backupStore.snapshotItems.length }} snapshots visible</p>
          <p class="health-card__details">
            {{ backupStore.snapshots?.limitations?.[0] ?? "No limitations reported." }}
          </p>
        </article>

        <article class="panel">
          <div class="settings-section__header">
            <div>
              <h3>Quarantine foundation</h3>
              <p>Visibility only. Move and restore workflows are not implemented yet.</p>
            </div>
            <StatusTag :status="backupStore.quarantine?.foundationState ?? 'unknown'" />
          </div>
          <dl class="runtime-detail__grid">
            <dt>Path</dt>
            <dd>{{ backupStore.quarantine?.path ?? "Unavailable" }}</dd>
            <dt>Index present</dt>
            <dd>{{ backupStore.quarantine?.indexPresent ? "Yes" : "No" }}</dd>
            <dt>Indexed items</dt>
            <dd>{{ backupStore.quarantine?.itemCount ?? 0 }}</dd>
            <dt>Workflow</dt>
            <dd>{{ backupStore.quarantine?.workflowImplemented ? "Implemented" : "Visibility only" }}</dd>
          </dl>
          <p class="health-card__details">
            {{ backupStore.quarantine?.message ?? "Quarantine visibility unavailable." }}
          </p>
        </article>
      </section>

      <EmptyState
        v-if="!backupStore.snapshotItems.length"
        title="No backup snapshots yet"
        message="A snapshot will appear here after a successful backup files run or pre-repair snapshot creation."
      />

      <section v-else class="backup-grid">
        <article
          v-for="snapshot in backupStore.snapshotItems"
          :key="snapshot.snapshotId"
          class="panel backup-card"
        >
          <div class="backup-card__header">
            <div>
              <h3>{{ snapshot.snapshotId }}</h3>
              <p class="health-card__details">{{ snapshot.createdAt }}</p>
            </div>
            <StatusTag :status="snapshot.basicValidity === 'valid' ? 'ok' : 'error'" />
          </div>
          <dl class="runtime-detail__grid">
            <dt>Kind</dt>
            <dd>{{ snapshot.kind }}</dd>
            <dt>Coverage</dt>
            <dd>{{ snapshot.coverage }}</dd>
            <dt>Linked repair run</dt>
            <dd>{{ snapshot.repairRunId ?? "Not linked" }}</dd>
            <dt>Verified</dt>
            <dd>{{ snapshot.verified ? "Yes" : "No" }}</dd>
            <dt>DB paired</dt>
            <dd>{{ snapshot.hasDbArtifact ? "Yes" : "No" }}</dd>
            <dt>Manifest</dt>
            <dd>{{ snapshot.manifestPath }}</dd>
          </dl>
          <p class="health-card__details">{{ snapshot.validityMessage }}</p>
          <p class="health-card__details">
            {{ snapshot.coverage === "files_only" ? "Current snapshot contains file artifacts only." : "Coverage includes non-file artifacts." }}
          </p>
        </article>
      </section>
    </template>
  </section>
</template>

<script setup lang="ts">
import { onMounted } from "vue";
import EmptyState from "@/components/common/EmptyState.vue";
import ErrorState from "@/components/common/ErrorState.vue";
import LoadingState from "@/components/common/LoadingState.vue";
import PageHeader from "@/components/common/PageHeader.vue";
import StatusTag from "@/components/common/StatusTag.vue";
import RiskNotice from "@/components/safety/RiskNotice.vue";
import { useBackupStore } from "@/stores/backup";

const backupStore = useBackupStore();

onMounted(async () => {
  await backupStore.load();
});
</script>
