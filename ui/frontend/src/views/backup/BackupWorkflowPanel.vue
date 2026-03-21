<template>
  <section class="backup-workflow">
    <article class="panel backup-card">
      <div class="settings-section__header">
        <div>
          <h3>Check / sync / verify / selective restore</h3>
          <p>
            Compare source assets against the current path-like backup mirror first, sync only missing files, and keep restore as an explicit reviewed action.
          </p>
        </div>
        <span :class="statusBadgeClass(workflowStatusLabel)">
          {{ formatStatusLabel(workflowStatusLabel) }}
        </span>
      </div>

      <p class="health-card__summary">
        {{ backupStore.workflowOverview?.summary ?? "Asset-aware backup review is pending." }}
      </p>
      <dl v-if="backupStore.workflowOverview" class="runtime-detail__grid">
        <dt>Source root</dt>
        <dd>{{ backupStore.workflowOverview.sourceRoot ?? "Unavailable" }}</dd>
        <dt>Backup mirror</dt>
        <dd>{{ backupStore.workflowOverview.backupRoot ?? "Unavailable" }}</dd>
        <dt>Compared items</dt>
        <dd>{{ backupStore.workflowOverview.comparison.totalItems }}</dd>
        <dt>Suspicious folders</dt>
        <dd>{{ backupStore.workflowOverview.folders.suspiciousCount }}</dd>
      </dl>
      <p
        v-for="warning in backupStore.workflowOverview?.warnings ?? []"
        :key="warning"
        class="health-card__details"
      >
        {{ warning }}
      </p>
      <p
        v-for="limitation in backupStore.workflowOverview?.limitations ?? []"
        :key="limitation"
        class="health-card__details"
      >
        {{ limitation }}
      </p>
      <section class="runtime-actions">
        <button
          class="runtime-action"
          type="button"
          :disabled="!selectedTargetSupportsPathWorkflow || backupStore.isLoadingWorkflow"
          @click="void refreshOverview()"
        >
          {{ backupStore.isLoadingWorkflow ? "Checking" : "Refresh Check" }}
        </button>
        <button
          class="runtime-action"
          type="button"
          :disabled="!selectedTargetSupportsPathWorkflow || backupStore.isExecuting || backupStore.isExecutionRunning"
          @click="void backupStore.startExecution(backupStore.selectedTargetId!)"
        >
          {{ backupStore.isExecutionRunning ? "Sync Running" : "Sync Missing" }}
        </button>
        <button
          class="runtime-action"
          type="button"
          :disabled="!selectedTargetSupportsPathWorkflow || backupStore.isRunningTestCopy"
          @click="void startTestCopy()"
        >
          {{ backupStore.isRunningTestCopy ? "Testing" : "Test Copy" }}
        </button>
      </section>
      <p v-if="backupStore.workflowError" class="runtime-blocking-message">
        {{ backupStore.workflowError }}
      </p>
    </article>

    <article class="panel backup-card">
      <div class="settings-section__header">
        <div>
          <h3>Folder heuristics</h3>
          <p>
            Count and total-size differences are early warning signals only, but they make suspicious backup gaps visible before restore decisions.
          </p>
        </div>
      </div>
      <div v-if="backupStore.workflowOverview?.folders.items.length" class="backup-folder-list">
        <article
          v-for="folder in backupStore.workflowOverview.folders.items"
          :key="folder.folder"
          class="backup-folder-card"
          :class="{ 'backup-folder-card--warning': folder.suspicious }"
        >
          <div class="backup-card__header">
            <strong>{{ folder.folder }}</strong>
            <span :class="statusBadgeClass(folder.suspicious ? 'mismatch' : 'identical')">
              {{ folder.suspicious ? "Suspicious" : "Aligned" }}
            </span>
          </div>
          <dl class="runtime-detail__grid">
            <dt>Source files</dt>
            <dd>{{ folder.sourceFileCount }}</dd>
            <dt>Backup files</dt>
            <dd>{{ folder.backupFileCount }}</dd>
            <dt>Source size</dt>
            <dd>{{ formatBytes(folder.sourceTotalBytes) }}</dd>
            <dt>Backup size</dt>
            <dd>{{ formatBytes(folder.backupTotalBytes) }}</dd>
          </dl>
          <p v-if="folder.suspicious" class="health-card__details">
            Reasons: {{ folder.reasons.join(", ") }}
          </p>
        </article>
      </div>
      <p v-else class="health-card__details">
        No folder comparison is available yet.
      </p>
    </article>

    <article class="panel backup-card">
      <div class="settings-section__header">
        <div>
          <h3>Reviewed item list</h3>
          <p>
            Only reviewed eligible items can be restored. Bulk restore stays dry-run preview first and then requires explicit confirmation.
          </p>
        </div>
      </div>

      <div class="runtime-actions">
        <button
          class="runtime-action"
          type="button"
          :disabled="backupStore.restorableItems.length === 0"
          @click="selectAllRestorable()"
        >
          Select All Eligible
        </button>
        <button
          class="runtime-action"
          type="button"
          :disabled="backupStore.selectedAssetIds.length === 0"
          @click="backupStore.clearAssetSelection()"
        >
          Clear Selection
        </button>
        <button
          class="runtime-action runtime-action--danger"
          type="button"
          :disabled="backupStore.selectedWorkflowItems.length === 0 || backupStore.isRunningRestore"
          @click="void previewSelectedRestore()"
        >
          {{ backupStore.isRunningRestore ? "Preparing Review" : "Review Selected Restore" }}
        </button>
      </div>

      <p v-if="backupStore.restoreError" class="runtime-blocking-message">
        {{ backupStore.restoreError }}
      </p>
      <p v-if="backupStore.lastTestCopy" class="health-card__details">
        {{ backupStore.lastTestCopy.summary }}
      </p>
      <p v-if="backupStore.lastRestoreResult" class="health-card__details">
        {{ backupStore.lastRestoreResult.summary }}
      </p>

      <div v-if="backupStore.workflowItems.length" class="backup-review-list">
        <article
          v-for="item in backupStore.workflowItems"
          :key="item.assetId"
          class="backup-review-item"
          :class="statusPanelClass(item.status)"
        >
          <div class="backup-review-item__header">
            <label class="backup-review-item__select">
              <input
                :checked="backupStore.selectedAssetIds.includes(item.assetId)"
                :disabled="!item.restoreEligible"
                type="checkbox"
                @change="backupStore.toggleAssetSelection(item.assetId)"
              />
              <span>{{ item.assetId }}</span>
            </label>
            <span :class="statusBadgeClass(item.status)">
              {{ formatStatusLabel(item.status) }}
            </span>
          </div>

          <div class="backup-review-item__content">
            <section class="backup-preview-card">
              <h4>Source</h4>
              <img
                v-if="item.source.exists && item.source.previewKind === 'image' && backupStore.selectedTargetId"
                class="backup-preview-card__media"
                :src="previewUrl('source', item.assetId)"
                alt="Source preview"
              />
              <video
                v-else-if="item.source.exists && item.source.previewKind === 'video' && backupStore.selectedTargetId"
                class="backup-preview-card__media"
                :src="previewUrl('source', item.assetId)"
                muted
                controls
                preload="metadata"
              />
              <p v-else class="health-card__details">Preview unavailable. Metadata only.</p>
              <dl class="runtime-detail__grid">
                <dt>Path</dt>
                <dd>{{ item.source.absolutePath ?? "Missing" }}</dd>
                <dt>Size</dt>
                <dd>{{ formatBytes(item.source.size) }}</dd>
                <dt>Modified</dt>
                <dd>{{ formatDate(item.source.modifiedAt) }}</dd>
              </dl>
            </section>

            <section class="backup-preview-card">
              <h4>Backup</h4>
              <img
                v-if="item.backup.exists && item.backup.previewKind === 'image' && backupStore.selectedTargetId"
                class="backup-preview-card__media"
                :src="previewUrl('backup', item.assetId)"
                alt="Backup preview"
              />
              <video
                v-else-if="item.backup.exists && item.backup.previewKind === 'video' && backupStore.selectedTargetId"
                class="backup-preview-card__media"
                :src="previewUrl('backup', item.assetId)"
                muted
                controls
                preload="metadata"
              />
              <p v-else class="health-card__details">Preview unavailable. Metadata only.</p>
              <dl class="runtime-detail__grid">
                <dt>Path</dt>
                <dd>{{ item.backup.absolutePath ?? "Missing" }}</dd>
                <dt>Size</dt>
                <dd>{{ formatBytes(item.backup.size) }}</dd>
                <dt>Modified</dt>
                <dd>{{ formatDate(item.backup.modifiedAt) }}</dd>
              </dl>
            </section>
          </div>

          <dl class="runtime-detail__grid">
            <dt>Comparison</dt>
            <dd>{{ item.comparison.method }} / {{ item.comparison.decision }}</dd>
            <dt>Source hash</dt>
            <dd>{{ item.comparison.sourceHash ?? "Not computed" }}</dd>
            <dt>Backup hash</dt>
            <dd>{{ item.comparison.backupHash ?? "Not computed" }}</dd>
          </dl>

          <section class="runtime-actions">
            <button
              class="runtime-action runtime-action--danger"
              type="button"
              :disabled="!item.restoreEligible || backupStore.isRunningRestore"
              @click="void previewSingleRestore(item.assetId)"
            >
              Restore / Overwrite From Backup
            </button>
          </section>
        </article>
      </div>
      <p v-else class="health-card__details">
        No reviewed item list is available yet.
      </p>
    </article>

    <ConfirmOperationDialog
      :visible="Boolean(backupStore.restorePreview)"
      title="Apply selective restore"
      summary="This will overwrite source-side files from backup copies after moving current source files into quarantine first."
      :items="restorePreviewItems"
      :notes="restorePreviewNotes"
      confirm-label="Apply Restore / Overwrite"
      cancel-label="Keep Dry-Run"
      :confirm-disabled="backupStore.isRunningRestore"
      @cancel="backupStore.restorePreview = null"
      @confirm="void confirmRestore()"
    />
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import ConfirmOperationDialog from "@/components/safety/ConfirmOperationDialog.vue";
import { useBackupStore } from "@/stores/backup";

const backupStore = useBackupStore();
const restorePlanAssetIds = ref<string[]>([]);
const selectedTargetSupportsPathWorkflow = computed(() => {
  const target = backupStore.selectedTarget;
  if (!target) {
    return false;
  }
  return (
    target.targetType === "local" ||
    (target.targetType === "smb" &&
      target.transport.mountStrategy === "pre_mounted_path" &&
      Boolean(target.transport.mountedPath))
  );
});

const workflowStatusLabel = computed(() => {
  const counts = backupStore.workflowOverview?.comparison.statusCounts ?? {};
  if ((counts.failed ?? 0) > 0 || (counts.conflict ?? 0) > 0) {
    return "conflict";
  }
  if ((counts.mismatch ?? 0) > 0 || (counts.restore_candidate ?? 0) > 0) {
    return "mismatch";
  }
  if ((counts.missing_in_backup ?? 0) > 0) {
    return "missing_in_backup";
  }
  if (backupStore.workflowOverview?.supported === false) {
    return "failed";
  }
  if (!backupStore.workflowOverview) {
    return "pending";
  }
  return "identical";
});

const restorePreviewItems = computed(() =>
  backupStore.restorePreview?.results.map((item) => `${item.assetId}: ${item.reason}`) ?? [],
);

const restorePreviewNotes = computed(() => [
  "Current source files are quarantined before overwrite.",
  "Only the selected reviewed items are applied.",
  "Bulk restore stays high-risk and is limited to path-like targets.",
]);

function formatBytes(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return "Unavailable";
  }
  if (value < 1024) {
    return `${value} B`;
  }
  const units = ["KB", "MB", "GB", "TB"];
  let size = value / 1024;
  let unitIndex = 0;
  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex += 1;
  }
  return `${size.toFixed(1)} ${units[unitIndex]}`;
}

function formatDate(value: string | null | undefined): string {
  if (!value) {
    return "Unavailable";
  }
  return new Date(value).toLocaleString();
}

function formatStatusLabel(status: string): string {
  return status.split("_").join(" ");
}

function statusBadgeClass(status: string): string[] {
  return ["backup-status-pill", `backup-status-pill--${status}`];
}

function statusPanelClass(status: string): Record<string, boolean> {
  return {
    "backup-review-item--pending": status === "pending",
    "backup-review-item--danger": ["mismatch", "conflict", "failed"].includes(status),
    "backup-review-item--restore": status === "restore_candidate",
  };
}

function previewUrl(side: "source" | "backup", assetId: string): string {
  const targetId = backupStore.selectedTargetId;
  return `/api/backup/targets/${targetId}/assets/preview/content?side=${side}&asset_id=${encodeURIComponent(assetId)}`;
}

async function refreshOverview(): Promise<void> {
  if (!backupStore.selectedTargetId) {
    return;
  }
  await backupStore.refreshWorkflowOverview(backupStore.selectedTargetId);
}

async function startTestCopy(): Promise<void> {
  if (!backupStore.selectedTargetId) {
    return;
  }
  await backupStore.startTestCopy(backupStore.selectedTargetId);
}

function selectAllRestorable(): void {
  backupStore.selectedAssetIds = backupStore.restorableItems.map((item) => item.assetId);
}

async function previewSelectedRestore(): Promise<void> {
  if (!backupStore.selectedTargetId || backupStore.selectedWorkflowItems.length === 0) {
    return;
  }
  restorePlanAssetIds.value = backupStore.selectedWorkflowItems.map((item) => item.assetId);
  await backupStore.previewRestore(backupStore.selectedTargetId, restorePlanAssetIds.value);
}

async function previewSingleRestore(assetId: string): Promise<void> {
  if (!backupStore.selectedTargetId) {
    return;
  }
  restorePlanAssetIds.value = [assetId];
  await backupStore.previewRestore(backupStore.selectedTargetId, restorePlanAssetIds.value);
}

async function confirmRestore(): Promise<void> {
  if (!backupStore.selectedTargetId || restorePlanAssetIds.value.length === 0) {
    return;
  }
  await backupStore.applyRestore(backupStore.selectedTargetId, restorePlanAssetIds.value);
}
</script>
