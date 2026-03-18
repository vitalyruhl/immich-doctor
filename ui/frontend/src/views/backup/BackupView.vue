<template>
  <section class="page">
    <PageHeader
      eyebrow="Backup"
      title="Backup"
      summary="Manual backup targets, non-blocking size visibility, validation, and execution status all come from backend state."
    />
    <RiskNotice
      title="Restore readiness is not implied"
      message="Current manual backup execution is files-only. Verification level is reported explicitly, and restore execution remains not implemented."
    />

    <LoadingState
      v-if="backupStore.isLoading && !backupStore.targetsOverview"
      title="Loading backup control surface"
      message="Collecting backup targets, size estimation state, current execution status, and snapshot history."
    />
    <ErrorState
      v-else-if="backupStore.error"
      title="Backup data unavailable"
      :message="backupStore.error"
    />
    <template v-else>
      <section class="settings-grid">
        <article class="panel backup-card">
          <div class="backup-card__header">
            <div>
              <h3>Source size estimate</h3>
              <p class="health-card__details">
                {{ backupStore.sizeEstimate?.summary ?? "Collecting backup size data..." }}
              </p>
            </div>
            <StatusTag :status="jobStateTag(backupStore.sizeEstimate?.state ?? 'pending')" />
          </div>
          <p
            v-if="backupStore.isSizeCollectionRunning"
            class="health-card__summary"
          >
            {{ backupStore.sizeEstimate?.progress?.message ?? "Collecting backup size data..." }}
          </p>
          <dl v-if="backupStore.storageEstimate || backupStore.databaseEstimate" class="runtime-detail__grid">
            <template v-if="backupStore.storageEstimate">
              <dt>Storage scope</dt>
              <dd>{{ formatBytes(backupStore.storageEstimate.bytes) }} for {{ backupStore.storageEstimate.sourceScope }}</dd>
              <dt>Storage state</dt>
              <dd>{{ backupStore.storageEstimate.state }}</dd>
            </template>
            <template v-if="backupStore.databaseEstimate">
              <dt>Database proxy</dt>
              <dd>{{ formatBytes(backupStore.databaseEstimate.bytes) }} using {{ backupStore.databaseEstimate.representation }}</dd>
              <dt>Database state</dt>
              <dd>{{ backupStore.databaseEstimate.state }}</dd>
            </template>
          </dl>
          <p
            v-for="warning in backupStore.sizeEstimate?.warnings ?? []"
            :key="warning"
            class="health-card__details"
          >
            {{ warning }}
          </p>
        </article>

        <article class="panel backup-card">
          <div class="backup-card__header">
            <div>
              <h3>Manual backup execution</h3>
              <p class="health-card__details">
                Files-only coverage. Verification level and warnings are shown after each run.
              </p>
            </div>
            <StatusTag :status="jobStateTag(backupStore.currentExecution?.state ?? 'pending')" />
          </div>
          <p class="health-card__summary">
            {{ backupStore.currentExecution?.summary ?? "No manual backup execution has started yet." }}
          </p>
          <dl v-if="backupStore.currentExecution?.report" class="runtime-detail__grid">
            <dt>Target</dt>
            <dd>{{ backupStore.currentExecution.targetType ?? "Unavailable" }}</dd>
            <dt>Verification</dt>
            <dd>{{ backupStore.currentExecution.report.verificationLevel ?? "none" }}</dd>
            <dt>Planned bytes</dt>
            <dd>{{ formatBytes(backupStore.currentExecution.report.bytesPlanned ?? null) }}</dd>
            <dt>Transferred bytes</dt>
            <dd>{{ formatBytes(backupStore.currentExecution.report.bytesTransferred ?? null) }}</dd>
          </dl>
          <p
            v-for="warning in backupStore.currentExecution?.warnings ?? []"
            :key="warning"
            class="health-card__details"
          >
            {{ warning }}
          </p>
          <section class="runtime-actions">
            <button
              class="runtime-action"
              type="button"
              :disabled="!backupStore.selectedTarget || backupStore.isExecuting || backupStore.isExecutionRunning"
              @click="void backupStore.startExecution(backupStore.selectedTarget!.targetId)"
            >
              {{ backupStore.isExecutionRunning ? "Backup Running" : "Start Manual Backup" }}
            </button>
            <button
              class="runtime-action"
              type="button"
              :disabled="!backupStore.selectedTarget || backupStore.isExecuting || backupStore.isExecutionRunning"
              @click="void backupStore.startExecution(backupStore.selectedTarget!.targetId, 'pre_repair')"
            >
              Create Pre-Repair Snapshot
            </button>
            <button
              class="runtime-action runtime-action--danger"
              type="button"
              :disabled="!backupStore.isExecutionRunning"
              @click="void backupStore.cancelExecution()"
            >
              Cancel Running Backup
            </button>
          </section>
          <p v-if="backupStore.executionError" class="runtime-blocking-message">
            {{ backupStore.executionError }}
          </p>
        </article>
      </section>

      <section class="settings-grid">
        <article class="panel backup-card">
          <div class="settings-section__header">
            <div>
              <h3>{{ editingTargetId ? "Edit backup target" : "Add backup target" }}</h3>
              <p>Secrets are only stored as local references. API and UI never return raw secret material.</p>
            </div>
          </div>
          <form class="backup-form" @submit.prevent="void submitTarget()">
            <label class="backup-form__field">
              <span>Name</span>
              <input v-model="draft.targetName" type="text" required />
            </label>
            <label class="backup-form__field">
              <span>Type</span>
              <select v-model="draft.targetType">
                <option value="local">Local folder</option>
                <option value="smb">SMB share</option>
                <option value="ssh">SSH target</option>
                <option value="rsync">rsync-capable Linux target</option>
              </select>
            </label>
            <label class="backup-form__field backup-form__field--toggle">
              <input v-model="draft.enabled" type="checkbox" />
              <span>Enabled target</span>
            </label>

            <template v-if="draft.targetType === 'local'">
              <label class="backup-form__field">
                <span>Absolute destination path</span>
                <input v-model="draft.path" type="text" placeholder="/backups/immich" required />
              </label>
            </template>

            <template v-else-if="draft.targetType === 'smb'">
              <label class="backup-form__field">
                <span>Host</span>
                <input v-model="draft.host" type="text" required />
              </label>
              <label class="backup-form__field">
                <span>Share</span>
                <input v-model="draft.share" type="text" required />
              </label>
              <label class="backup-form__field">
                <span>Remote path</span>
                <input v-model="draft.remotePath" type="text" required />
              </label>
              <label class="backup-form__field">
                <span>Mount strategy</span>
                <select v-model="draft.mountStrategy">
                  <option value="system_mount">System mount</option>
                  <option value="pre_mounted_path">Pre-mounted path</option>
                </select>
              </label>
              <label v-if="draft.mountStrategy === 'pre_mounted_path'" class="backup-form__field">
                <span>Mounted path</span>
                <input v-model="draft.mountedPath" type="text" placeholder="/mnt/immich-backup" />
              </label>
            </template>

            <template v-else>
              <label class="backup-form__field">
                <span>Host</span>
                <input v-model="draft.host" type="text" required />
              </label>
              <label class="backup-form__field">
                <span>Port</span>
                <input v-model.number="draft.port" type="number" min="1" />
              </label>
              <label class="backup-form__field">
                <span>Username</span>
                <input v-model="draft.username" type="text" required />
              </label>
              <label class="backup-form__field">
                <span>Remote path</span>
                <input v-model="draft.remotePath" type="text" required />
              </label>
              <label class="backup-form__field">
                <span>Auth mode</span>
                <select v-model="draft.authMode">
                  <option value="private_key">Private key</option>
                  <option value="password">Password</option>
                </select>
              </label>
              <label class="backup-form__field">
                <span>Host key verification</span>
                <select v-model="draft.hostKeyVerification">
                  <option value="known_hosts">Known hosts</option>
                  <option value="pinned_fingerprint">Pinned fingerprint</option>
                  <option value="insecure_accept_any">Insecure accept any</option>
                </select>
              </label>
              <label class="backup-form__field">
                <span>Host key reference</span>
                <input
                  v-model="draft.hostKeyReference"
                  type="text"
                  placeholder="Known hosts path or fingerprint reference"
                />
              </label>
              <label v-if="draft.authMode === 'password'" class="backup-form__field">
                <span>Password label</span>
                <input v-model="draft.passwordSecret!.label" type="text" placeholder="SSH Password" />
              </label>
              <label v-if="draft.authMode === 'password'" class="backup-form__field">
                <span>Password</span>
                <input v-model="draft.passwordSecret!.material" type="password" />
              </label>
              <template v-else>
                <label class="backup-form__field">
                  <span>Private key label</span>
                  <input
                    v-model="draft.privateKeySecret!.label"
                    type="text"
                    placeholder="Primary SSH Key"
                  />
                </label>
                <label class="backup-form__field">
                  <span>Private key</span>
                  <textarea v-model="draft.privateKeySecret!.material" rows="5" />
                </label>
              </template>
            </template>

            <div class="runtime-actions">
              <button class="runtime-action" type="submit" :disabled="backupStore.isSavingTarget">
                {{ backupStore.isSavingTarget ? "Saving" : editingTargetId ? "Save Target" : "Add Target" }}
              </button>
              <button class="runtime-action" type="button" @click="resetDraft()">
                Reset Form
              </button>
            </div>
          </form>
          <p v-if="backupStore.targetError" class="runtime-blocking-message">
            {{ backupStore.targetError }}
          </p>
        </article>

        <article class="panel backup-card">
          <div class="settings-section__header">
            <div>
              <h3>Configured targets</h3>
              <p>Select one target for manual backup, validation, or editing.</p>
            </div>
          </div>
          <EmptyState
            v-if="!backupStore.hasTargets"
            title="No targets configured"
            message="Create a local, SSH, rsync, or SMB target before starting a manual backup."
          />
          <section v-else class="backup-grid">
            <article
              v-for="target in backupStore.targets"
              :key="target.targetId"
              class="panel backup-card backup-target-card"
              :class="{ 'backup-target-card--selected': backupStore.selectedTargetId === target.targetId }"
            >
              <div class="backup-card__header">
                <div>
                  <h3>{{ target.targetName }}</h3>
                  <p class="health-card__details">{{ target.targetType }}</p>
                </div>
                <StatusTag :status="verificationTag(target.verificationStatus)" />
              </div>
              <dl class="runtime-detail__grid">
                <dt>Enabled</dt>
                <dd>{{ target.enabled ? "Yes" : "No" }}</dd>
                <dt>Restore readiness</dt>
                <dd>{{ target.restoreReadiness }}</dd>
                <dt>Coverage</dt>
                <dd>{{ target.sourceScope }}</dd>
                <dt>Last test</dt>
                <dd>{{ target.lastTestResult?.summary ?? "Not validated yet" }}</dd>
              </dl>
              <p
                v-for="warning in target.warnings"
                :key="`${target.targetId}-${warning}`"
                class="health-card__details"
              >
                {{ warning }}
              </p>
              <section class="runtime-actions">
                <button class="runtime-action" type="button" @click="selectTarget(target.targetId)">
                  {{ backupStore.selectedTargetId === target.targetId ? "Selected" : "Select Target" }}
                </button>
                <button
                  class="runtime-action"
                  type="button"
                  :disabled="backupStore.isValidatingTarget"
                  @click="void backupStore.validateTarget(target.targetId)"
                >
                  {{ backupStore.isValidatingTarget && backupStore.selectedTargetId === target.targetId ? "Validating" : "Validate Target" }}
                </button>
                <button class="runtime-action" type="button" @click="loadTargetIntoDraft(target)">
                  Edit
                </button>
                <button
                  class="runtime-action runtime-action--danger"
                  type="button"
                  :disabled="backupStore.isSavingTarget"
                  @click="void backupStore.removeTarget(target.targetId)"
                >
                  Delete
                </button>
              </section>
            </article>
          </section>
          <p v-if="backupStore.validationError" class="runtime-blocking-message">
            {{ backupStore.validationError }}
          </p>
        </article>
      </section>

      <section class="settings-grid">
        <article class="panel backup-card">
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

        <article class="panel backup-card">
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
          </dl>
        </article>
      </section>

      <section v-if="backupStore.snapshotItems.length" class="backup-grid">
        <article
          v-for="snapshot in backupStore.snapshotItems"
          :key="snapshot.snapshotId"
          class="panel backup-card"
        >
          <div class="backup-card__header">
            <div>
              <h3>{{ snapshot.snapshotId }}</h3>
              <p class="health-card__details">{{ formatDate(snapshot.createdAt) }}</p>
            </div>
            <StatusTag :status="snapshot.basicValidity === 'valid' ? 'ok' : 'error'" />
          </div>
          <dl class="runtime-detail__grid">
            <dt>Kind</dt>
            <dd>{{ snapshot.kind }}</dd>
            <dt>Coverage</dt>
            <dd>{{ snapshot.coverage }}</dd>
            <dt>Manifest</dt>
            <dd>{{ snapshot.manifestPath }}</dd>
          </dl>
          <p class="health-card__details">{{ snapshot.validityMessage }}</p>
        </article>
      </section>
    </template>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import EmptyState from "@/components/common/EmptyState.vue";
import ErrorState from "@/components/common/ErrorState.vue";
import LoadingState from "@/components/common/LoadingState.vue";
import PageHeader from "@/components/common/PageHeader.vue";
import StatusTag from "@/components/common/StatusTag.vue";
import RiskNotice from "@/components/safety/RiskNotice.vue";
import { useBackupStore } from "@/stores/backup";
import type { BackupTargetConfig, BackupTargetDraft, BackupTargetVerificationStatus } from "@/api/types/backup";

const backupStore = useBackupStore();
const editingTargetId = ref<string | null>(null);

function defaultDraft(): BackupTargetDraft {
  return {
    targetName: "",
    targetType: "local",
    enabled: true,
    path: "",
    port: 22,
    authMode: "private_key",
    mountStrategy: "system_mount",
    hostKeyVerification: "known_hosts",
    passwordSecret: { label: "", material: "" },
    privateKeySecret: { label: "", material: "" },
    retentionPolicy: { mode: "keep_all", pruneAutomatically: false },
  };
}

const draft = ref<BackupTargetDraft>(defaultDraft());

function resetDraft(): void {
  editingTargetId.value = null;
  draft.value = defaultDraft();
}

function selectTarget(targetId: string): void {
  backupStore.selectTarget(targetId);
}

function loadTargetIntoDraft(target: BackupTargetConfig): void {
  editingTargetId.value = target.targetId;
  backupStore.selectTarget(target.targetId);
  draft.value = {
    targetName: target.targetName,
    targetType: target.targetType,
    enabled: target.enabled,
    path: target.transport.path ?? "",
    host: target.transport.host ?? "",
    port: target.transport.port ?? 22,
    share: target.transport.share ?? "",
    remotePath: target.transport.remotePath ?? "",
    username: target.transport.username ?? "",
    authMode: target.transport.authMode ?? "private_key",
    mountStrategy: target.transport.mountStrategy ?? "system_mount",
    mountedPath: target.transport.mountedPath ?? "",
    hostKeyVerification: target.transport.hostKeyVerification ?? "known_hosts",
    hostKeyReference: target.transport.hostKeyReference ?? "",
    passwordSecret: { label: "", material: "" },
    privateKeySecret: { label: "", material: "" },
    retentionPolicy: target.retentionPolicy,
  };
}

async function submitTarget(): Promise<void> {
  await backupStore.saveTarget(draft.value, editingTargetId.value ?? undefined);
  if (!backupStore.targetError) {
    resetDraft();
  }
}

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

function verificationTag(status: BackupTargetVerificationStatus): "ok" | "warning" | "error" | "unknown" {
  if (status === "ready") {
    return "ok";
  }
  if (status === "warning" || status === "running") {
    return "warning";
  }
  if (status === "failed") {
    return "error";
  }
  return "unknown";
}

function jobStateTag(state: string): "ok" | "warning" | "error" | "unknown" {
  if (state === "completed") {
    return "ok";
  }
  if (state === "running" || state === "pending" || state === "partial") {
    return "warning";
  }
  if (state === "failed" || state === "canceled") {
    return "error";
  }
  return "unknown";
}

onMounted(async () => {
  await backupStore.load();
});
</script>
