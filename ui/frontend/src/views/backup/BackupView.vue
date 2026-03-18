<template>
  <section class="page">
    <PageHeader
      eyebrow="Backup"
      title="Backup"
      summary="Backend state drives manual target visibility, conservative validation, and files-only execution status."
    />
    <RiskNotice
      title="Restore readiness is not implied"
      message="Manual execution currently covers files-only scope on local and safe-subset SSH/rsync targets. SMB stays configuration, validation, and mount-planning only, verification stays conservative, and restore execution is not implemented."
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
                {{ backupStore.sizeEstimate?.summary ?? "Backup size collection is pending." }}
              </p>
            </div>
            <StatusTag :status="jobStateTag(backupStore.sizeEstimate?.state ?? 'pending')" />
          </div>
          <p
            v-if="backupStore.isSizeCollectionRunning"
            class="health-card__summary"
          >
            {{ backupStore.sizeEstimate?.progress?.message ?? "Backup size collection is running." }}
          </p>
          <p v-if="backupStore.sizeEstimate?.stale" class="health-card__details">
            Stale cached backup size data is shown until a fresh collection completes.
          </p>
          <p class="health-card__details">
            Storage values describe the current files-only source scope. Database values are proxy estimates only and do not mean that a DB backup artifact exists.
          </p>
          <dl v-if="backupStore.storageEstimate || backupStore.databaseEstimate" class="runtime-detail__grid">
            <template v-if="backupStore.storageEstimate">
              <dt>Storage scope</dt>
              <dd>{{ formatBytes(backupStore.storageEstimate.bytes) }} for {{ backupStore.storageEstimate.sourceScope }}</dd>
              <dt>Storage state</dt>
              <dd>{{ formatJobState(backupStore.storageEstimate.state) }}</dd>
            </template>
            <template v-if="backupStore.databaseEstimate">
              <dt>Database proxy</dt>
              <dd>{{ formatBytes(backupStore.databaseEstimate.bytes) }} using {{ formatRepresentation(backupStore.databaseEstimate.representation) }}</dd>
              <dt>Database state</dt>
              <dd>{{ formatJobState(backupStore.databaseEstimate.state) }}</dd>
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
                Files-only transfer scope. Verification levels show transport or destination checks only, not end-to-end restore proof.
              </p>
            </div>
            <StatusTag :status="jobStateTag(backupStore.currentExecution?.state ?? 'pending')" />
          </div>
          <p class="health-card__summary">
            {{ backupStore.currentExecution?.summary ?? "Manual files-only backup has not run yet." }}
          </p>
          <dl v-if="backupStore.currentExecution?.report" class="runtime-detail__grid">
            <dt>Target</dt>
            <dd>{{ formatTargetType(backupStore.currentExecution.targetType) }}</dd>
            <dt>Verification</dt>
            <dd>{{ formatVerificationLevel(backupStore.currentExecution.report.verificationLevel) }}</dd>
            <dt>Restore capability</dt>
            <dd>{{ formatRestoreReadiness(backupStore.currentExecution.restoreReadiness) }}</dd>
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
          <p v-if="selectedExecutionBlocker" class="health-card__details">
            {{ selectedExecutionBlocker }}
          </p>
          <section class="runtime-actions">
            <button
              class="runtime-action"
              type="button"
              :disabled="!backupStore.selectedTarget || backupStore.isExecuting || backupStore.isExecutionRunning || Boolean(selectedExecutionBlocker)"
              @click="void backupStore.startExecution(backupStore.selectedTarget!.targetId)"
            >
              {{ backupStore.isExecutionRunning ? "Backup In Progress" : "Start Files-Only Backup" }}
            </button>
            <button
              class="runtime-action"
              type="button"
              :disabled="!backupStore.selectedTarget || backupStore.isExecuting || backupStore.isExecutionRunning || Boolean(selectedExecutionBlocker)"
              @click="void backupStore.startExecution(backupStore.selectedTarget!.targetId, 'pre_repair')"
            >
              Create Files-Only Pre-Repair Snapshot
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
            <p v-if="draft.targetType === 'smb'" class="health-card__details">
              SMB targets are planning and validation only in this phase. Productive SMB backup execution is intentionally disabled.
            </p>
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
              <p v-if="draft.authMode === 'password'" class="health-card__details">
                Password material can be stored as a secret reference, but remote execution currently supports private-key auth only.
              </p>
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
              <p>Select one target for conservative validation, editing, or supported manual execution.</p>
            </div>
          </div>
          <EmptyState
            v-if="!backupStore.hasTargets"
            title="No targets configured"
            message="Create a target first. Only local and safe-subset SSH/rsync targets can run manual backups in this phase; SMB stays configuration, validation, and mount-planning only."
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
                  <p class="health-card__details">{{ formatTargetType(target.targetType) }}</p>
                </div>
                <StatusTag :status="verificationTag(target.verificationStatus)" />
              </div>
              <dl class="runtime-detail__grid">
                <dt>Enabled</dt>
                <dd>{{ target.enabled ? "Yes" : "No" }}</dd>
                <dt>Execution support</dt>
                <dd>{{ targetExecutionSupport(target) }}</dd>
                <dt>Restore capability</dt>
                <dd>{{ formatRestoreReadiness(target.restoreReadiness) }}</dd>
                <dt>Validation state</dt>
                <dd>{{ formatVerificationStatus(target.verificationStatus) }}</dd>
                <dt>Coverage</dt>
                <dd>{{ formatCoverage(target.sourceScope) }}</dd>
                <dt>Last test</dt>
                <dd>{{ target.lastTestResult?.summary ?? "Target validation has not run yet." }}</dd>
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
              <p>Persisted snapshot manifests and conservative coverage visibility. Structural checks do not prove artifact integrity or restore success.</p>
            </div>
          </div>
          <p class="health-card__summary">{{ backupStore.snapshotItems.length }} snapshot records visible</p>
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
            <StatusTag :status="snapshot.basicValidity === 'valid' ? 'warning' : 'error'" />
          </div>
          <dl class="runtime-detail__grid">
            <dt>Kind</dt>
            <dd>{{ snapshot.kind }}</dd>
            <dt>Coverage</dt>
            <dd>{{ formatCoverage(snapshot.coverage) }}</dd>
            <dt>Manifest check</dt>
            <dd>{{ formatBasicValidity(snapshot.basicValidity) }}</dd>
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
import { computed, onMounted, ref } from "vue";
import EmptyState from "@/components/common/EmptyState.vue";
import ErrorState from "@/components/common/ErrorState.vue";
import LoadingState from "@/components/common/LoadingState.vue";
import PageHeader from "@/components/common/PageHeader.vue";
import StatusTag from "@/components/common/StatusTag.vue";
import RiskNotice from "@/components/safety/RiskNotice.vue";
import { useBackupStore } from "@/stores/backup";
import type {
  BackupJobState,
  BackupRestoreReadiness,
  BackupSnapshotBasicValidity,
  BackupTargetConfig,
  BackupTargetDraft,
  BackupTargetType,
  BackupTargetVerificationStatus,
  BackupVerificationLevel,
} from "@/api/types/backup";

const backupStore = useBackupStore();
const editingTargetId = ref<string | null>(null);
const selectedExecutionBlocker = computed(() => executionBlockerForTarget(backupStore.selectedTarget));

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

function formatJobState(state: BackupJobState | string | null | undefined): string {
  switch (state) {
    case "pending":
      return "Pending";
    case "running":
      return "Running";
    case "partial":
      return "Partial";
    case "completed":
      return "Completed";
    case "failed":
      return "Failed";
    case "unsupported":
      return "Unsupported";
    case "cancel_requested":
      return "Cancel requested";
    case "canceled":
      return "Canceled";
    default:
      return "Unknown";
  }
}

function formatRepresentation(representation: string | null | undefined): string {
  if (representation === "physical_db_size_proxy") {
    return "physical DB size proxy";
  }
  if (representation === "filesystem_usage") {
    return "filesystem usage";
  }
  return representation ?? "Unavailable";
}

function formatVerificationLevel(level: BackupVerificationLevel | null | undefined): string {
  switch (level) {
    case "transport_success_only":
      return "Transport success only";
    case "destination_exists":
      return "Destination path exists";
    case "basic_manifest_verified":
      return "Basic manifest structure verified";
    case "none":
    default:
      return "No verification";
  }
}

function formatRestoreReadiness(readiness: BackupRestoreReadiness | null | undefined): string {
  if (readiness === "partial") {
    return "Partially modeled only";
  }
  return "Not implemented";
}

function formatTargetType(targetType: BackupTargetType | null | undefined): string {
  switch (targetType) {
    case "local":
      return "Local folder";
    case "smb":
      return "SMB share";
    case "ssh":
      return "SSH target";
    case "rsync":
      return "rsync-capable Linux target";
    default:
      return "Unavailable";
  }
}

function formatCoverage(coverage: string | null | undefined): string {
  if (coverage === "files_only") {
    return "Files only";
  }
  if (coverage === "db_only") {
    return "DB only";
  }
  if (coverage === "paired") {
    return "Paired DB + files";
  }
  return coverage ?? "Unavailable";
}

function formatBasicValidity(validity: BackupSnapshotBasicValidity): string {
  return validity === "valid" ? "Manifest structure valid only" : "Manifest structure invalid";
}

function formatVerificationStatus(status: BackupTargetVerificationStatus): string {
  switch (status) {
    case "ready":
      return "Validated for currently implemented checks";
    case "warning":
      return "Validated with warnings";
    case "failed":
      return "Validation failed";
    case "running":
      return "Validation running";
    case "unsupported":
      return "Validation partially unsupported";
    default:
      return "Not validated";
  }
}

function executionBlockerForTarget(target: BackupTargetConfig | null): string | null {
  if (!target) {
    return null;
  }
  if (target.targetType === "smb") {
    return "SMB execution is not implemented in this phase. SMB targets remain configuration, validation, and mount-planning only.";
  }
  if ((target.targetType === "ssh" || target.targetType === "rsync") && target.transport.authMode === "password") {
    return "Password-based SSH/rsync execution is not implemented in this phase.";
  }
  return null;
}

function targetExecutionSupport(target: BackupTargetConfig): string {
  return executionBlockerForTarget(target) ?? "Manual files-only execution is supported";
}

function verificationTag(status: BackupTargetVerificationStatus): "ok" | "warning" | "error" | "unknown" {
  if (status === "ready") {
    return "warning";
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
