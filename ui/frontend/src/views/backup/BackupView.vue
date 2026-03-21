<template>
  <section class="page">
    <PageHeader
      eyebrow="Backup"
      title="Backup"
      summary="Check, sync, verify, and selective restore stay explicit, review-driven, and conservative."
    />
    <RiskNotice
      title="High-risk data path"
      message="Normal backup now favors check plus sync-missing on usable path-like targets instead of blunt recopy. Selective restore remains operator-confirmed, only applies where a path-like backup mirror exists, and quarantines current source files before overwrite."
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
                {{ sourceSizePrimaryMessage }}
              </p>
            </div>
            <StatusTag :status="jobStateTag(backupStore.sizeEstimate?.state ?? 'pending')" />
          </div>
          <section class="runtime-actions">
            <button
              class="runtime-action runtime-action--secondary"
              type="button"
              :disabled="backupStore.isSizeCollectionRunning"
              @click="void backupStore.refreshSizeEstimate(true)"
            >
              {{ backupStore.isSizeCollectionRunning ? "Recalculation Running" : sourceSizeActionLabel }}
            </button>
          </section>
          <p v-if="sourceSizeSecondaryMessage" class="health-card__summary">
            {{ sourceSizeSecondaryMessage }}
          </p>
          <p v-if="sourceSizeTimestampMessage" class="health-card__details">
            {{ sourceSizeTimestampMessage }}
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
              <h3>Manual check / sync execution</h3>
              <p class="health-card__details">
                Usable path-like targets run an asset-aware check plus sync-missing flow. SSH and rsync targets keep their conservative files-only snapshot behavior and do not expose asset-level restore here.
              </p>
            </div>
            <StatusTag :status="jobStateTag(backupStore.currentExecution?.state ?? 'pending')" />
          </div>
          <p class="health-card__summary">
            {{ backupStore.currentExecution?.summary ?? "Backup check/sync has not run yet." }}
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
              {{ backupStore.isExecutionRunning ? "Sync In Progress" : selectedExecutionPrimaryLabel }}
            </button>
            <button
              class="runtime-action"
              type="button"
              :disabled="!backupStore.selectedTarget || backupStore.isExecuting || backupStore.isExecutionRunning || Boolean(selectedExecutionBlocker)"
              @click="void backupStore.startExecution(backupStore.selectedTarget!.targetId, 'pre_repair')"
            >
              {{ selectedPreRepairLabel }}
            </button>
            <button
              class="runtime-action runtime-action--danger"
              type="button"
              :disabled="!backupStore.isExecutionRunning"
              @click="void backupStore.cancelExecution()"
            >
              Cancel Running Sync
            </button>
          </section>
          <p v-if="backupStore.executionError" class="runtime-blocking-message">
            {{ backupStore.executionError }}
          </p>
        </article>
      </section>

      <BackupWorkflowPanel />

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
                <option value="local">Local folder on this system</option>
                <option value="smb">SMB share</option>
                <option value="ssh">SSH target</option>
                <option value="rsync">Rsync over SSH</option>
              </select>
            </label>
            <p v-if="draft.targetType === 'smb'" class="health-card__details">
              SMB targets can either use a path that is already mounted for doctor or keep planned system-mount details for later. Only the mounted local path variant is supported today.
            </p>
            <label class="backup-form__field backup-form__field--toggle">
              <input v-model="draft.enabled" type="checkbox" />
              <span>Enabled target</span>
            </label>

            <template v-if="draft.targetType === 'local'">
              <p class="health-card__details">
                Use this for a folder path on this system. It can also be a path already mounted into the host or container.
              </p>
              <label class="backup-form__field">
                <span>Local folder on this system</span>
                <input v-model="draft.path" type="text" placeholder="/backups/immich" required />
              </label>
            </template>

            <template v-else-if="draft.targetType === 'smb'">
              <label class="backup-form__field">
                <span>Access mode</span>
                <select v-model="draft.mountStrategy">
                  <option value="pre_mounted_path">Mounted local path</option>
                  <option value="system_mount">System mount (not supported yet)</option>
                </select>
              </label>
              <template v-if="draft.mountStrategy === 'pre_mounted_path'">
                <p class="health-card__details">
                  Use this when the backup location is already mounted outside doctor. Doctor only needs the mounted local path.
                </p>
                <label class="backup-form__field">
                  <span>Mounted local path</span>
                  <input
                    v-model="draft.mountedPath"
                    type="text"
                    placeholder="/mnt/immich-backup"
                    required
                  />
                </label>
              </template>
              <template v-else>
                <p class="health-card__details">
                  Use this only to record planned SMB system-mount details. Doctor does not mount SMB shares itself yet, so this mode is not executable in the current safe subset.
                </p>
                <label class="backup-form__field">
                  <span>Server / Host</span>
                  <input v-model="draft.host" type="text" required />
                </label>
                <label class="backup-form__field">
                  <span>Share name</span>
                  <input v-model="draft.share" type="text" placeholder="backups" required />
                </label>
                <label class="backup-form__field">
                  <span>Subfolder in share</span>
                  <input v-model="draft.remotePath" type="text" placeholder="immich" />
                </label>
                <label class="backup-form__field">
                  <span>Username</span>
                  <input v-model="draft.username" type="text" required />
                </label>
                <p v-if="existingPasswordSecretRef" class="health-card__details">
                  Stored password secret reference: {{ existingPasswordSecretRef.secretId }}. Leave the password field empty to keep it.
                </p>
                <label class="backup-form__field">
                  <span>Password secret</span>
                  <input
                    v-model="draft.passwordSecret!.material"
                    type="password"
                    :required="!existingPasswordSecretRef"
                    autocomplete="new-password"
                  />
                </label>
                <label class="backup-form__field">
                  <span>Domain</span>
                  <input v-model="draft.domain" type="text" placeholder="WORKGROUP" />
                </label>
                <details class="backup-form__details">
                  <summary>Advanced mount options</summary>
                  <label class="backup-form__field">
                    <span>Mount options</span>
                    <input
                      v-model="draft.mountOptions"
                      type="text"
                      placeholder="vers=3.0,seal"
                    />
                  </label>
                </details>
              </template>
            </template>

            <template v-else>
              <label class="backup-form__field">
                <span>{{ draft.targetType === 'rsync' ? 'Rsync over SSH connection' : 'SSH connection' }}</span>
                <input
                  v-model="draft.connectionString"
                  type="text"
                  placeholder="root@192.168.2.2"
                />
              </label>
              <p class="health-card__details">
                {{
                  draft.targetType === 'rsync'
                    ? 'Use this for rsync over SSH. This is SSH-based transport, not a mounted filesystem.'
                    : 'Use username@host or username@host:port. Expand manual fields only if you prefer entering server, user, and port separately.'
                }}
              </p>
              <p v-if="parsedConnection.error" class="runtime-blocking-message">
                {{ parsedConnection.error }}
              </p>
              <dl v-else-if="parsedConnection.username && parsedConnection.host" class="runtime-detail__grid">
                <dt>Parsed username</dt>
                <dd>{{ parsedConnection.username }}</dd>
                <dt>Parsed host</dt>
                <dd>{{ parsedConnection.host }}</dd>
                <template v-if="parsedConnection.port">
                  <dt>Parsed port</dt>
                  <dd>{{ parsedConnection.port }}</dd>
                </template>
              </dl>
              <button
                class="runtime-action runtime-action--secondary"
                type="button"
                @click="toggleRemoteConnectionMode()"
              >
                {{
                  useManualRemoteFields
                    ? 'Use single connection field'
                    : 'Enter server, user, and port separately'
                }}
              </button>
              <template v-if="useManualRemoteFields">
                <label class="backup-form__field">
                  <span>Server / Host</span>
                  <input v-model="draft.host" type="text" required />
                </label>
                <label class="backup-form__field">
                  <span>Username</span>
                  <input v-model="draft.username" type="text" required />
                </label>
                <label class="backup-form__field">
                  <span>Port</span>
                  <input v-model.number="draft.port" type="number" min="1" />
                </label>
              </template>
              <label class="backup-form__field">
                <span>{{ draft.targetType === 'rsync' ? 'Destination folder on remote system' : 'Destination folder on remote system' }}</span>
                <input v-model="draft.remotePath" type="text" placeholder="/srv/backup" required />
              </label>
              <label class="backup-form__field">
                <span>Authentication method</span>
                <select v-model="draft.authMode">
                  <option value="agent">SSH agent</option>
                  <option value="private_key">Private key</option>
                  <option v-if="sshPasswordAuthEnabled" value="password">Password</option>
                </select>
              </label>
              <p class="health-card__details">
                Username is always required for SSH login. SSH agent mode uses a forwarded host SSH agent in the container, while private key mode uses a stored secret.
              </p>
              <p v-if="sshAgentHelpMessage" class="health-card__details">
                {{ sshAgentHelpMessage }}
              </p>
              <p v-if="draft.authMode === 'password'" class="health-card__details">
                Password-based SSH execution remains hidden and unsupported for execution in this phase.
              </p>
              <p v-if="draft.authMode === 'private_key' && existingPrivateKeySecretRef" class="health-card__details">
                Stored secret reference: {{ existingPrivateKeySecretRef.secretId }}. Leave the private key field empty to keep it.
              </p>
              <template v-if="draft.authMode === 'private_key'">
                <label class="backup-form__field">
                  <span>Private key</span>
                  <textarea
                    v-model="draft.privateKeySecret!.material"
                    rows="5"
                    :required="!existingPrivateKeySecretRef"
                  />
                </label>
              </template>
              <template v-else-if="draft.authMode === 'password'">
                <p v-if="existingPasswordSecretRef" class="health-card__details">
                  Stored secret reference: {{ existingPasswordSecretRef.secretId }}. Leave the password field empty to keep it.
                </p>
                <label class="backup-form__field">
                  <span>Password secret</span>
                  <input
                    v-model="draft.passwordSecret!.material"
                    type="password"
                    :required="!existingPasswordSecretRef"
                    autocomplete="new-password"
                  />
                </label>
              </template>
              <details class="backup-form__details">
                <summary>Advanced SSH options</summary>
                <label class="backup-form__field">
                  <span>Known host mode</span>
                  <select v-model="draft.knownHostMode">
                    <option value="strict">Strict</option>
                    <option value="accept_new">Accept new</option>
                    <option value="disabled">Disabled</option>
                  </select>
                </label>
                <p v-if="draft.knownHostMode === 'disabled'" class="runtime-blocking-message">
                  Disabled known-host mode accepts host changes without verification. Use only for controlled environments.
                </p>
                <label class="backup-form__field">
                  <span>Known hosts file</span>
                  <input
                    v-model="draft.knownHostReference"
                    type="text"
                    placeholder="~/.ssh/known_hosts"
                  />
                </label>
                <p class="health-card__details">
                  Host known_hosts files are not shared into the container automatically. Mount one explicitly if you want strict or accept-new mode to reuse host trust.
                </p>
              </details>
            </template>

            <div class="runtime-actions">
              <button
                class="runtime-action"
                type="submit"
                :disabled="backupStore.isSavingTarget || Boolean(formValidationError)"
              >
                {{ backupStore.isSavingTarget ? "Saving" : editingTargetId ? "Save Target" : "Add Target" }}
              </button>
              <button class="runtime-action" type="button" @click="resetDraft()">
                Reset Form
              </button>
            </div>
            <p v-if="formValidationError" class="runtime-blocking-message">
              {{ formValidationError }}
            </p>
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
            message="Create a target first. Local targets, SMB pre-mounted path targets, and the safe SSH/rsync subset can run manual backups in this phase; SMB system mount remains planned only and is not executable yet."
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
                <StatusTag :status="verificationTag(targetVerificationStatus(target))" />
              </div>
              <dl class="runtime-detail__grid">
                <dt>Enabled</dt>
                <dd>{{ target.enabled ? "Yes" : "No" }}</dd>
                <dt>Execution support</dt>
                <dd>{{ targetExecutionSupport(target) }}</dd>
                <dt>Restore capability</dt>
                <dd>{{ formatRestoreReadiness(target.restoreReadiness) }}</dd>
                <dt>Validation state</dt>
                <dd>{{ validationStateForTarget(target) }}</dd>
                <dt>Coverage</dt>
                <dd>{{ formatCoverage(target.sourceScope) }}</dd>
                <dt>Last test</dt>
                <dd>{{ validationSummaryForTarget(target) }}</dd>
              </dl>
              <p
                v-if="validationDetailForTarget(target)"
                class="health-card__details"
              >
                {{ validationDetailForTarget(target) }}
              </p>
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
                  {{ validationButtonLabel(target) }}
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
import BackupWorkflowPanel from "./BackupWorkflowPanel.vue";
import { useBackupStore } from "@/stores/backup";
import type {
  BackupJobState,
  BackupRuntimeCapability,
  BackupRestoreReadiness,
  BackupSizeEstimateResponse,
  BackupSizeEstimateStatus,
  BackupSnapshotBasicValidity,
  BackupTargetConfig,
  BackupTargetDraft,
  BackupTargetValidationResponse,
  SecretReferenceSummary,
  BackupTargetType,
  BackupTargetVerificationStatus,
  BackupVerificationLevel,
} from "@/api/types/backup";

const SSH_PASSWORD_AUTH_ENABLED = false;
const backupStore = useBackupStore();
const editingTargetId = ref<string | null>(null);
const editingTarget = computed<BackupTargetConfig | null>(() =>
  backupStore.targets.find((target) => target.targetId === editingTargetId.value) ?? null,
);
const selectedExecutionBlocker = computed(() => executionBlockerForTarget(backupStore.selectedTarget));
const selectedExecutionPrimaryLabel = computed(() =>
  targetUsesPathLikeWorkflow(backupStore.selectedTarget)
    ? "Start Check / Sync Missing"
    : "Start Files-Only Backup",
);
const selectedPreRepairLabel = computed(() =>
  targetUsesPathLikeWorkflow(backupStore.selectedTarget)
    ? "Run Pre-Repair Check / Sync"
    : "Run Pre-Repair Files-Only Backup",
);
const useManualRemoteFields = ref(false);
const sshPasswordAuthEnabled = SSH_PASSWORD_AUTH_ENABLED;
const existingPasswordSecretRef = computed<SecretReferenceSummary | null>(
  () => editingTarget.value?.transport.passwordSecretRef ?? null,
);
const existingPrivateKeySecretRef = computed<SecretReferenceSummary | null>(
  () => editingTarget.value?.transport.privateKeySecretRef ?? null,
);
const sshAgentRuntimeCapability = computed<BackupRuntimeCapability | null>(
  () => backupStore.targetsOverview?.runtimeCapabilities?.sshAgent ?? null,
);
const sourceSizeStatus = computed<BackupSizeEstimateStatus>(
  () => backupStore.sizeEstimate?.status ?? "unknown",
);
const sourceSizeActionLabel = computed(() =>
  sourceSizeStatus.value === "unknown" ? "Calculate Estimate" : "Recalculate",
);
const sourceSizePrimaryMessage = computed(() =>
  primarySourceSizeMessage(backupStore.sizeEstimate),
);
const sourceSizeSecondaryMessage = computed(() =>
  secondarySourceSizeMessage(backupStore.sizeEstimate),
);
const sourceSizeTimestampMessage = computed(() =>
  sourceSizeTimestampDetail(backupStore.sizeEstimate),
);
const sshAgentHelpMessage = computed(() => {
  if (draft.value.targetType !== "ssh" && draft.value.targetType !== "rsync") {
    return null;
  }
  if (draft.value.authMode === "private_key") {
    return "Private key mode uses a stored secret reference and does not depend on a forwarded SSH agent.";
  }
  if (draft.value.authMode === "password") {
    return "Password mode still needs a stored secret and remains unsupported for execution in this phase.";
  }
  const capability = sshAgentRuntimeCapability.value;
  if (capability?.available) {
    return `Forwarded SSH agent is available in this doctor runtime. ${capability.summary}`;
  }
  if (capability?.summary) {
    return `${capability.summary} Host SSH success does not automatically mean container SSH success.`;
  }
  return "SSH agent mode expects a forwarded host SSH agent inside the container runtime. Host SSH success does not automatically mean container SSH success.";
});

function defaultDraft(): BackupTargetDraft {
  return {
    targetName: "",
    targetType: "local",
    enabled: true,
    path: "",
    connectionString: "",
    port: 22,
    authMode: "agent",
    mountStrategy: "system_mount",
    knownHostMode: "strict",
    domain: "",
    mountOptions: "",
    passwordSecret: { label: "", material: "" },
    privateKeySecret: { label: "", material: "" },
    retentionPolicy: { mode: "keep_all", pruneAutomatically: false },
  };
}

const draft = ref<BackupTargetDraft>(defaultDraft());
const trimmedConnectionString = computed(() => trimToUndefined(draft.value.connectionString) ?? "");
const parsedConnection = computed(() => {
  if (!trimmedConnectionString.value) {
    return { username: "", host: "", port: null, error: null as string | null };
  }
  return parseConnectionString(trimmedConnectionString.value);
});
const formValidationError = computed(() => validateDraft(draft.value));

function resetDraft(): void {
  editingTargetId.value = null;
  useManualRemoteFields.value = false;
  draft.value = defaultDraft();
}

function selectTarget(targetId: string): void {
  backupStore.selectTarget(targetId);
}

function loadTargetIntoDraft(target: BackupTargetConfig): void {
  editingTargetId.value = target.targetId;
  backupStore.selectTarget(target.targetId);
  useManualRemoteFields.value = false;
  draft.value = {
    targetName: target.targetName,
    targetType: target.targetType,
    enabled: target.enabled,
    path: target.transport.path ?? "",
    connectionString: formatStoredConnectionString(target),
    host: target.transport.host ?? "",
    port: target.transport.port ?? 22,
    share: target.transport.share ?? "",
    remotePath: target.transport.remotePath ?? "",
    username: target.transport.username ?? "",
    authMode: target.transport.authMode ?? "agent",
    mountStrategy: target.transport.mountStrategy ?? "system_mount",
    mountedPath: target.transport.mountedPath ?? "",
    knownHostMode: target.transport.knownHostMode ?? "strict",
    knownHostReference: target.transport.knownHostReference ?? "",
    domain: target.transport.domain ?? "",
    mountOptions: target.transport.mountOptions ?? "",
    passwordSecret: { label: "", material: "" },
    privateKeySecret: { label: "", material: "" },
    retentionPolicy: target.retentionPolicy,
  };
}

async function submitTarget(): Promise<void> {
  const clientValidationError = validateDraft(draft.value);
  if (clientValidationError) {
    return;
  }
  await backupStore.saveTarget(buildTargetPayload(draft.value), editingTargetId.value ?? undefined);
  if (!backupStore.targetError) {
    resetDraft();
  }
}

function buildTargetPayload(currentDraft: BackupTargetDraft): BackupTargetDraft {
  const payload: BackupTargetDraft = {
    targetName: currentDraft.targetName.trim(),
    targetType: currentDraft.targetType,
    enabled: currentDraft.enabled,
    retentionPolicy: currentDraft.retentionPolicy,
  };
  if (currentDraft.targetType === "local") {
    payload.path = trimToUndefined(currentDraft.path);
    return payload;
  }
  payload.mountStrategy = currentDraft.mountStrategy;
  if (currentDraft.targetType === "smb") {
    if (currentDraft.mountStrategy === "pre_mounted_path") {
      payload.mountedPath = trimToUndefined(currentDraft.mountedPath);
      return payload;
    }
    payload.host = trimToUndefined(currentDraft.host);
    payload.share = trimToUndefined(currentDraft.share);
    payload.remotePath = trimToUndefined(currentDraft.remotePath);
    payload.username = trimToUndefined(currentDraft.username);
    payload.domain = trimToUndefined(currentDraft.domain);
    payload.mountOptions = trimToUndefined(currentDraft.mountOptions);
    const passwordSecret = buildSecretInput(currentDraft.passwordSecret?.material);
    if (passwordSecret) {
      payload.passwordSecret = passwordSecret;
    }
    return payload;
  }
  const connectionString = trimToUndefined(currentDraft.connectionString);
  payload.connectionString = connectionString;
  if (connectionString) {
    payload.port = parsedConnection.value.port ?? currentDraft.port ?? 22;
  } else {
    payload.host = trimToUndefined(currentDraft.host);
    payload.port = currentDraft.port ?? 22;
    payload.username = trimToUndefined(currentDraft.username);
  }
  payload.authMode = currentDraft.authMode;
  payload.knownHostMode = currentDraft.knownHostMode;
  payload.knownHostReference = trimToUndefined(currentDraft.knownHostReference);
  payload.remotePath = trimToUndefined(currentDraft.remotePath);
  const passwordSecret = buildSecretInput(currentDraft.passwordSecret?.material);
  if (passwordSecret) {
    payload.passwordSecret = passwordSecret;
  }
  const privateKeySecret = buildSecretInput(currentDraft.privateKeySecret?.material);
  if (privateKeySecret) {
    payload.privateKeySecret = privateKeySecret;
  }
  return payload;
}

function buildSecretInput(material?: string): { material?: string } | undefined {
  const secretMaterial = material ?? "";
  if (!secretMaterial) {
    return undefined;
  }
  return {
    material: secretMaterial,
  };
}

function toggleRemoteConnectionMode(): void {
  if (useManualRemoteFields.value) {
    const username = trimToUndefined(draft.value.username);
    const host = trimToUndefined(draft.value.host);
    if (!trimToUndefined(draft.value.connectionString) && username && host) {
      const port = draft.value.port ?? 22;
      draft.value.connectionString =
        port === 22 ? `${username}@${host}` : `${username}@${host}:${port}`;
    }
    useManualRemoteFields.value = false;
    return;
  }
  if (trimmedConnectionString.value && !parsedConnection.value.error) {
    draft.value.username = draft.value.username ?? parsedConnection.value.username;
    draft.value.host = draft.value.host ?? parsedConnection.value.host;
    draft.value.port = parsedConnection.value.port ?? draft.value.port ?? 22;
    draft.value.connectionString = "";
  }
  useManualRemoteFields.value = true;
}

function formatStoredConnectionString(target: BackupTargetConfig): string {
  if (!target.transport.username || !target.transport.host) {
    return "";
  }
  const port = target.transport.port ?? 22;
  return port === 22
    ? `${target.transport.username}@${target.transport.host}`
    : `${target.transport.username}@${target.transport.host}:${port}`;
}

function validateDraft(currentDraft: BackupTargetDraft): string | null {
  if (!currentDraft.targetName.trim()) {
    return "Target name is required.";
  }
  if (currentDraft.targetType === "local") {
    if (!trimToUndefined(currentDraft.path)) {
      return "Local targets require an absolute destination path.";
    }
    return null;
  }
  if (currentDraft.targetType === "smb") {
    if (currentDraft.mountStrategy === "pre_mounted_path") {
      if (!trimToUndefined(currentDraft.mountedPath)) {
        return "SMB pre-mounted targets require a mounted path.";
      }
      return null;
    }
    if (!trimToUndefined(currentDraft.host) || !trimToUndefined(currentDraft.share)) {
      return "SMB system-mount targets require a server and share name.";
    }
    if (!trimToUndefined(currentDraft.username)) {
      return "SMB system-mount targets require a username.";
    }
    if (!existingPasswordSecretRef.value && !(currentDraft.passwordSecret?.material ?? "")) {
      return "SMB system-mount targets require a password secret.";
    }
    return null;
  }
  if (parsedConnection.value.error) {
    return parsedConnection.value.error;
  }
  if (!trimmedConnectionString.value) {
    if (!trimToUndefined(currentDraft.host) || !trimToUndefined(currentDraft.username)) {
      return "SSH and rsync targets require host and username or a connection string.";
    }
  }
  if (!trimToUndefined(currentDraft.remotePath)) {
    return "SSH and rsync targets require a remote path.";
  }
  if (!currentDraft.authMode) {
    return "SSH and rsync targets require an auth mode.";
  }
  if (!currentDraft.knownHostMode) {
    return "SSH and rsync targets require a known host mode.";
  }
  if (currentDraft.authMode === "private_key" && !existingPrivateKeySecretRef.value && !(currentDraft.privateKeySecret?.material ?? "")) {
    return "Private-key auth requires a private key secret.";
  }
  if (currentDraft.authMode === "password" && !existingPasswordSecretRef.value && !(currentDraft.passwordSecret?.material ?? "")) {
    return "Password auth requires a password secret.";
  }
  return null;
}

function parseConnectionString(connectionString: string): {
  username: string;
  host: string;
  port: number | null;
  error: string | null;
} {
  const trimmed = connectionString.trim();
  if (!trimmed) {
    return { username: "", host: "", port: null, error: null };
  }
  const separator = trimmed.indexOf("@");
  if (separator <= 0 || separator === trimmed.length - 1 || trimmed.indexOf("@", separator + 1) !== -1) {
    return {
      username: "",
      host: "",
      port: null,
      error: "Connection string must use the form username@host.",
    };
  }
  const username = trimmed.slice(0, separator);
  const hostReference = trimmed.slice(separator + 1);
  const parsedHostReference = parseConnectionHostReference(hostReference);
  if (parsedHostReference.error) {
    return {
      username: "",
      host: "",
      port: null,
      error: parsedHostReference.error,
    };
  }
  return {
    username,
    host: parsedHostReference.host,
    port: parsedHostReference.port,
    error: null,
  };
}

function parseConnectionHostReference(hostReference: string): {
  host: string;
  port: number | null;
  error: string | null;
} {
  if (hostReference.startsWith("[")) {
    const closingIndex = hostReference.indexOf("]");
    if (closingIndex <= 1) {
      return { host: "", port: null, error: "Connection string contains an invalid bracketed host." };
    }
    const host = hostReference.slice(1, closingIndex);
    const remainder = hostReference.slice(closingIndex + 1);
    if (!remainder) {
      return { host, port: null, error: null };
    }
    if (!remainder.startsWith(":")) {
      return {
        host: "",
        port: null,
        error: "Connection string must use the form username@host or username@host:port.",
      };
    }
    const parsedPort = parseConnectionPort(remainder.slice(1));
    return parsedPort.error
      ? { host: "", port: null, error: parsedPort.error }
      : { host, port: parsedPort.port, error: null };
  }
  const colonCount = Array.from(hostReference).filter((character) => character === ":").length;
  if (colonCount === 1) {
    const separator = hostReference.lastIndexOf(":");
    const host = hostReference.slice(0, separator);
    const candidatePort = hostReference.slice(separator + 1);
    if (candidatePort && /^\d+$/.test(candidatePort)) {
      if (!host) {
        return { host: "", port: null, error: "Connection string host is missing." };
      }
      const parsedPort = parseConnectionPort(candidatePort);
      return parsedPort.error
        ? { host: "", port: null, error: parsedPort.error }
        : { host, port: parsedPort.port, error: null };
    }
  }
  if (!hostReference) {
    return { host: "", port: null, error: "Connection string host is missing." };
  }
  return { host: hostReference, port: null, error: null };
}

function parseConnectionPort(candidatePort: string): {
  port: number | null;
  error: string | null;
} {
  if (!/^\d+$/.test(candidatePort)) {
    return { port: null, error: "Connection string port must be numeric." };
  }
  const port = Number(candidatePort);
  if (port < 1 || port > 65535) {
    return { port: null, error: "Connection string port must be between 1 and 65535." };
  }
  return { port, error: null };
}

function trimToUndefined(value: string | null | undefined): string | undefined {
  if (value === null || value === undefined) {
    return undefined;
  }
  const trimmed = value.trim();
  return trimmed ? trimmed : undefined;
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

function primarySourceSizeMessage(estimate: BackupSizeEstimateResponse | null): string {
  if (!estimate) {
    return "No source size estimate is available yet.";
  }
  switch (estimate.status) {
    case "unknown":
      return "No current source size estimate is available yet.";
    case "queued":
      return "Source size recalculation is queued.";
    case "running":
      return "Source size recalculation is in progress.";
    case "completed":
      return "Source size estimate completed.";
    case "partial":
      return "Source size estimate is partial.";
    case "failed":
      return "Source size estimate failed.";
    case "unsupported":
      return "Source size estimate is unsupported for the current configuration.";
    case "canceled":
      return "Source size recalculation was canceled.";
    case "stale":
      return estimate.staleReason === "restart"
        ? "Last calculated before doctor restart."
        : "Showing an older source size estimate.";
    default:
      return estimate.summary;
  }
}

function secondarySourceSizeMessage(estimate: BackupSizeEstimateResponse | null): string | null {
  if (!estimate) {
    return "A recalculation starts automatically when doctor starts.";
  }
  if (estimate.status === "running") {
    if (estimate.stale && estimate.collectedAt) {
      return "Showing the previous estimate until refresh completes.";
    }
    return estimate.progress?.message ?? "Source size recalculation is running.";
  }
  if (estimate.status === "queued") {
    return estimate.stale && estimate.collectedAt
      ? "A fresh recalculation was requested. Previous values stay visible until collection starts."
      : "A fresh recalculation was requested and will start shortly.";
  }
  if (estimate.status === "stale") {
    return estimate.staleReason === "restart"
      ? "A new calculation starts automatically after restart. Previous values are not treated as fresh."
      : "Refresh this estimate before using it for planning.";
  }
  if (estimate.status === "partial") {
    return "Partial estimate. Review warnings before using it for planning.";
  }
  if (estimate.status === "failed") {
    return "Calculation failed. Use Refresh to try again.";
  }
  if (estimate.status === "unsupported") {
    return "One or more required source settings are missing or unsupported.";
  }
  return null;
}

function sourceSizeTimestampDetail(estimate: BackupSizeEstimateResponse | null): string | null {
  if (!estimate?.collectedAt) {
    return null;
  }
  if (estimate.staleReason === "restart") {
    return `Last calculated before restart: ${formatDate(estimate.collectedAt)}`;
  }
  if (estimate.stale) {
    return `Showing an older estimate from ${formatDate(estimate.collectedAt)}`;
  }
  return `Last calculated: ${formatDate(estimate.collectedAt)}`;
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
    case "copied_files_sha256":
      return "Copied files verified by SHA-256";
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
    return "Partial path-based selective restore";
  }
  return "Not implemented";
}

function formatTargetType(targetType: BackupTargetType | null | undefined): string {
  switch (targetType) {
    case "local":
      return "Local folder on this system";
    case "smb":
      return "SMB share";
    case "ssh":
      return "SSH target";
    case "rsync":
      return "Rsync over SSH";
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

function activeValidationForTarget(target: BackupTargetConfig): BackupTargetValidationResponse | null {
  return backupStore.activeValidation?.targetId === target.targetId ? backupStore.activeValidation : null;
}

function targetVerificationStatus(target: BackupTargetConfig): BackupTargetVerificationStatus {
  return activeValidationForTarget(target)?.verificationStatus ?? target.verificationStatus;
}

function isTerminalValidationState(state: BackupJobState): boolean {
  return ["completed", "partial", "failed", "unsupported", "canceled"].includes(state);
}

function validationStateForTarget(target: BackupTargetConfig): string {
  const activeValidation = activeValidationForTarget(target);
  if (activeValidation && !isTerminalValidationState(activeValidation.state)) {
    return "Validation running";
  }
  return formatVerificationStatus(targetVerificationStatus(target));
}

function validationSummaryForTarget(target: BackupTargetConfig): string {
  const activeValidation = activeValidationForTarget(target);
  if (activeValidation) {
    return activeValidation.summary;
  }
  return target.lastTestResult?.summary ?? "Target validation has not run yet.";
}

function validationDetailForTarget(target: BackupTargetConfig): string | null {
  const activeValidation = activeValidationForTarget(target);
  const warnings = activeValidation?.warnings ?? target.lastTestResult?.warnings ?? [];
  if (warnings.length > 0) {
    return warnings[0] ?? null;
  }
  const checks =
    activeValidation?.checks ??
    ((target.lastTestResult?.details.checks as Array<{ name?: string; status?: string; message?: string }> | undefined) ?? []);
  const firstProblem = checks.find((check) =>
    (check.status === "fail" || check.status === "warn" || check.status === "skip") &&
    check.name !== "tool_rsync",
  );
  return firstProblem?.message ?? null;
}

function validationButtonLabel(target: BackupTargetConfig): string {
  if (backupStore.isValidatingTarget && backupStore.validatingTargetId === target.targetId) {
    return "Validating";
  }
  return "Validate Target";
}

function executionBlockerForTarget(target: BackupTargetConfig | null): string | null {
  if (!target) {
    return null;
  }
  if (target.targetType === "smb") {
    if (target.transport.mountStrategy === "pre_mounted_path" && target.transport.mountedPath) {
      return null;
    }
    return "SMB system mount is planned only and is not executable yet. Only mounted local path targets can execute through the current path-like workflow.";
  }
  if ((target.targetType === "ssh" || target.targetType === "rsync") && target.transport.authMode === "password") {
    return "Password-based SSH/rsync execution is not implemented in this phase.";
  }
  const executionSupport = executionSupportForTarget(target);
  if (executionSupport && executionSupport.supported === false && executionSupport.summary) {
    return executionSupport.summary;
  }
  const checks =
    (target.lastTestResult?.details.checks as Array<{ name?: string; status?: string; message?: string }> | undefined) ?? [];
  const rsyncCheck = checks.find((check) => check.name === "tool_rsync" && check.status !== "pass");
  if (rsyncCheck?.message && (target.targetType === "ssh" || target.targetType === "rsync")) {
    return rsyncCheck.message;
  }
  return null;
}

function targetUsesPathLikeWorkflow(target: BackupTargetConfig | null): boolean {
  if (!target) {
    return false;
  }
  return (
    target.targetType === "local" ||
    (target.targetType === "smb" &&
      target.transport.mountStrategy === "pre_mounted_path" &&
      Boolean(target.transport.mountedPath))
  );
}

function targetExecutionSupport(target: BackupTargetConfig): string {
  const executionSupport = executionSupportForTarget(target);
  if (executionSupport?.summary) {
    return executionSupport.summary;
  }
  if (target.targetType === "local") {
    return "Asset-aware check / sync is supported";
  }
  if (target.targetType === "smb" && target.transport.mountStrategy === "pre_mounted_path" && target.transport.mountedPath) {
    return "Mounted path check / sync is supported";
  }
  if (target.targetType === "ssh" || target.targetType === "rsync") {
    return executionBlockerForTarget(target) ?? "Files-only snapshot transfer is supported";
  }
  return executionBlockerForTarget(target) ?? "Execution is supported";
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

function executionSupportForTarget(target: BackupTargetConfig): {
  supported: boolean;
  state: string;
  summary: string;
} | null {
  const activeValidation = activeValidationForTarget(target);
  if (activeValidation?.executionSupport) {
    return activeValidation.executionSupport;
  }
  const details = target.lastTestResult?.details as
    | {
        executionSupport?: {
          supported: boolean;
          state: string;
          summary: string;
        };
      }
    | undefined;
  return details?.executionSupport ?? null;
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
