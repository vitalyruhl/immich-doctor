<template>
  <section class="page">
    <PageHeader
      eyebrow="Runtime"
      title="Runtime / Health"
      summary="Physical file integrity is checked before metadata extraction failures are classified."
    />
    <DisclaimerBanner />
    <RiskNotice
      title="High-risk integrity workflow"
      message="Metadata extraction failures may be secondary symptoms. Review physical file defects first and avoid blind retries."
    />

    <LoadingState
      v-if="runtimeStore.isLoading && !runtimeStore.metadataFailures"
      title="Loading runtime integrity diagnostics"
      message="Collecting physical file checks, repair readiness, and metadata failure diagnostics from the backend."
    />
    <ErrorState
      v-else-if="runtimeStore.error"
      title="Runtime diagnostics unavailable"
      :message="runtimeStore.error"
    />
    <template v-else>
      <section class="health-grid">
        <article
          class="panel"
          v-for="item in runtimeStore.integrity?.summary_items ?? []"
          :key="item.status"
        >
          <h3>{{ item.status }}</h3>
          <p class="health-card__summary">{{ item.count }} files</p>
        </article>
      </section>

      <section class="health-grid">
        <article
          class="panel"
          v-for="item in runtimeStore.metadataFailures?.metadata_summary ?? []"
          :key="item.root_cause"
        >
          <h3>{{ item.root_cause }}</h3>
          <p class="health-card__summary">{{ item.count }} assets</p>
        </article>
      </section>

      <section class="settings-grid">
        <article class="panel">
          <div class="settings-section__header">
            <div>
              <h3>Apply readiness</h3>
              <p>Current gating for the integrated permission repair flow.</p>
            </div>
            <StatusTag :status="readinessStatus" />
          </div>
          <p class="health-card__summary">
            {{
              runtimeStore.readiness
                ? runtimeStore.readiness.applyAllowed
                  ? "Apply allowed"
                  : "Apply blocked"
                : "Readiness unavailable"
            }}
          </p>
          <p class="health-card__details">
            {{ runtimeStore.readiness?.blockingReasons[0] ?? "No blocking reason reported." }}
          </p>
          <section class="runtime-findings">
            <article
              v-for="condition in runtimeStore.readiness?.preconditions ?? []"
              :key="condition.id"
              class="runtime-finding"
            >
              <div class="runtime-finding__header">
                <strong>{{ condition.label }}</strong>
                <StatusTag :status="condition.status" />
              </div>
              <span>{{ condition.summary }}</span>
              <small v-if="condition.blocking">Blocking precondition</small>
            </article>
          </section>
        </article>

        <article class="panel">
          <div class="settings-section__header">
            <div>
              <h3>Safety context</h3>
              <p>Snapshot, undo, quarantine, and restore visibility for apply.</p>
            </div>
          </div>
          <dl class="runtime-detail__grid">
            <dt>Snapshot kind</dt>
            <dd>{{ runtimeStore.readiness?.snapshotPlan.kind ?? "Unavailable" }}</dd>
            <dt>Snapshot coverage</dt>
            <dd>{{ runtimeStore.readiness?.snapshotPlan.coverage ?? "Unavailable" }}</dd>
            <dt>Undo visible</dt>
            <dd>{{ runtimeStore.readiness?.undoVisibility.journalUndoAvailable ? "Yes" : "No" }}</dd>
            <dt>Automated undo</dt>
            <dd>{{ runtimeStore.readiness?.undoVisibility.automatedUndo ? "Yes" : "No" }}</dd>
            <dt>Restore</dt>
            <dd>{{ runtimeStore.readiness?.restoreImplemented ? "Implemented" : "Not implemented" }}</dd>
          </dl>
          <p class="health-card__details">
            {{ runtimeStore.readiness?.snapshotPlan.note ?? "No snapshot note available." }}
          </p>
          <p class="health-card__details">
            {{ runtimeStore.readiness?.undoVisibility.note ?? "No undo note available." }}
          </p>
          <ul
            v-if="runtimeStore.readiness?.limitations.length"
            class="confirm-dialog__notes"
          >
            <li
              v-for="limitation in runtimeStore.readiness.limitations"
              :key="limitation"
            >
              {{ limitation }}
            </li>
          </ul>
        </article>
      </section>

      <EmptyState
        v-if="!runtimeStore.diagnostics.length"
        title="No metadata failure diagnostics"
        message="The current batch exposed no unresolved metadata extraction failures."
      />

      <section v-else class="runtime-grid">
        <article class="panel runtime-list">
          <h3>Failed assets</h3>
          <button
            v-for="diagnostic in runtimeStore.diagnostics"
            :key="diagnostic.diagnostic_id"
            type="button"
            class="runtime-list__item"
            :class="{ 'is-active': selectedDiagnostic?.diagnostic_id === diagnostic.diagnostic_id }"
            @click="selectedDiagnosticId = diagnostic.diagnostic_id"
          >
            <strong>{{ diagnostic.asset_id }}</strong>
            <span>{{ diagnostic.root_cause }}</span>
            <small>{{ diagnostic.source_path }}</small>
          </button>
        </article>

        <article v-if="selectedDiagnostic" class="panel runtime-detail">
          <div class="runtime-detail__header">
            <div>
              <h3>Diagnostic detail</h3>
              <p class="health-card__details">{{ selectedDiagnostic.diagnostic_id }}</p>
            </div>
          </div>
          <dl class="runtime-detail__grid">
            <dt>Asset</dt>
            <dd>{{ selectedDiagnostic.asset_id }}</dd>
            <dt>Root cause</dt>
            <dd>{{ selectedDiagnostic.root_cause }}</dd>
            <dt>Failure role</dt>
            <dd>{{ selectedDiagnostic.failure_level }}</dd>
            <dt>Confidence</dt>
            <dd>{{ selectedDiagnostic.confidence }}</dd>
            <dt>Suggested action</dt>
            <dd>{{ selectedDiagnostic.suggested_action }}</dd>
            <dt>Source path</dt>
            <dd>{{ selectedDiagnostic.source_path }}</dd>
            <dt>Source file status</dt>
            <dd>{{ selectedDiagnostic.source_file_status }}</dd>
          </dl>

          <RiskNotice
            v-if="selectedDiagnostic.root_cause === 'CAUSED_BY_CORRUPTED_FILE'"
            title="Corruption suspected"
            message="Do not blindly retry metadata extraction. Treat file damage as the primary cause."
          />

          <section class="runtime-actions">
            <button
              v-for="action in selectedDiagnostic.available_actions"
              :key="`${selectedDiagnostic.diagnostic_id}-${action}`"
              type="button"
              class="runtime-action"
              :disabled="runtimeStore.isPlanning"
              @click="planAction(action, false)"
            >
              Dry-run {{ action }}
            </button>
            <button
              v-if="selectedDiagnostic.available_actions.includes('fix_permissions')"
              type="button"
              class="runtime-action runtime-action--danger"
              :disabled="applyDisabled"
              :title="applyDisabled ? applyBlockedMessage ?? 'Apply is blocked.' : 'Apply fix_permissions'"
              @click="openApplyConfirmation()"
            >
              Apply fix_permissions
            </button>
          </section>

          <p v-if="applyBlockedMessage" class="runtime-blocking-message">{{ applyBlockedMessage }}</p>
          <p class="health-card__details">{{ selectedDiagnostic.source_message }}</p>

          <section class="runtime-findings">
            <h4>Related files</h4>
            <article
              v-for="finding in selectedDiagnostic.file_findings"
              :key="finding.finding_id"
              class="runtime-finding"
            >
              <strong>{{ finding.file_role }}</strong>
              <span>{{ finding.status }}</span>
              <small>{{ finding.path }}</small>
            </article>
          </section>
        </article>
      </section>

      <ErrorState
        v-if="runtimeStore.planError"
        title="Repair planning request failed"
        :message="runtimeStore.planError"
      />

      <article v-if="runtimeStore.repairResult" class="panel runtime-plan">
        <div class="settings-section__header">
          <div>
            <h3>Latest repair result</h3>
            <p>Dry-run and apply results for the integrated runtime repair flow.</p>
          </div>
          <StatusTag :status="repairResultStatus" />
        </div>
        <p class="health-card__summary">{{ runtimeStore.repairResult.summary }}</p>
        <dl class="runtime-detail__grid">
          <dt>Mode</dt>
          <dd>{{ runtimeStore.repairResult.metadata.dry_run ? "Dry-run" : "Apply" }}</dd>
          <dt>Repair run</dt>
          <dd>{{ runtimeStore.repairResult.metadata.repair_run_id ?? "Unavailable" }}</dd>
          <dt>Pre-repair snapshot</dt>
          <dd>{{ runtimeStore.repairResult.metadata.pre_repair_snapshot_id ?? "Not created" }}</dd>
        </dl>
        <div
          v-for="action in runtimeStore.repairResult.repair_actions"
          :key="`${action.diagnostic_id}-${action.action}`"
          class="runtime-finding"
        >
          <div class="runtime-finding__header">
            <strong>{{ action.action }}</strong>
            <StatusTag :status="toRepairActionStatus(action.status)" />
          </div>
          <span>{{ action.reason }}</span>
          <small>path={{ action.path }}</small>
        </div>
        <p class="health-card__details">
          Full restore remains unavailable. Use the journal and snapshot references for visibility only.
        </p>
      </article>

      <article v-if="runtimeStore.repairRunDetail" class="panel runtime-plan">
        <div class="settings-section__header">
          <div>
            <h3>Latest repair run journal</h3>
            <p>Persisted run, linked snapshot, and journaled undo visibility.</p>
          </div>
          <StatusTag :status="toRepairRunStatus(runtimeStore.repairRunDetail.repairRun.status)" />
        </div>
        <p class="health-card__summary">{{ runtimeStore.repairRunDetail.repairRun.repairRunId }}</p>
        <dl class="runtime-detail__grid">
          <dt>Started</dt>
          <dd>{{ runtimeStore.repairRunDetail.repairRun.startedAt }}</dd>
          <dt>Ended</dt>
          <dd>{{ runtimeStore.repairRunDetail.repairRun.endedAt ?? "Still open" }}</dd>
          <dt>Pre-repair snapshot</dt>
          <dd>{{ runtimeStore.repairRunDetail.repairRun.preRepairSnapshotId ?? "Not linked" }}</dd>
          <dt>Journal entries</dt>
          <dd>{{ runtimeStore.repairRunDetail.repairRun.journalEntryCount }}</dd>
          <dt>Undo visible</dt>
          <dd>{{ runtimeStore.repairRunDetail.repairRun.undoAvailable ? "Yes" : "No" }}</dd>
        </dl>
        <div
          v-for="entry in runtimeStore.repairRunDetail.journalEntries"
          :key="entry.entryId"
          class="runtime-finding"
        >
          <div class="runtime-finding__header">
            <strong>{{ entry.operationType }}</strong>
            <StatusTag :status="toRepairActionStatus(entry.status)" />
          </div>
          <span>{{ entry.originalPath ?? entry.assetId ?? "No path reference" }}</span>
          <small>undo={{ entry.undoType }}</small>
          <small v-if="formatModeChange(entry.undoPayload)">
            {{ formatModeChange(entry.undoPayload) }}
          </small>
          <small v-if="formatErrorReason(entry.errorDetails)">
            {{ formatErrorReason(entry.errorDetails) }}
          </small>
        </div>
        <ul class="confirm-dialog__notes">
          <li
            v-for="limitation in runtimeStore.repairRunDetail.limitations"
            :key="limitation"
          >
            {{ limitation }}
          </li>
        </ul>
      </article>
    </template>

    <ConfirmOperationDialog
      :visible="showApplyConfirmation"
      title="Apply runtime permission repair"
      summary="This will mutate runtime file permissions only after a files-only pre-repair snapshot has been created."
      :items="confirmationItems"
      :notes="confirmationNotes"
      confirm-label="Apply repair"
      cancel-label="Cancel"
      :confirm-disabled="applyDisabled"
      @cancel="showApplyConfirmation = false"
      @confirm="confirmApply"
    />
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import ConfirmOperationDialog from "@/components/safety/ConfirmOperationDialog.vue";
import DisclaimerBanner from "@/components/safety/DisclaimerBanner.vue";
import EmptyState from "@/components/common/EmptyState.vue";
import ErrorState from "@/components/common/ErrorState.vue";
import LoadingState from "@/components/common/LoadingState.vue";
import PageHeader from "@/components/common/PageHeader.vue";
import StatusTag from "@/components/common/StatusTag.vue";
import RiskNotice from "@/components/safety/RiskNotice.vue";
import { useRuntimeStore } from "@/stores/runtime";
import type { SuggestedAction } from "@/api/types/runtime";

const runtimeStore = useRuntimeStore();
const selectedDiagnosticId = ref<string | null>(null);
const showApplyConfirmation = ref(false);

const selectedDiagnostic = computed(() =>
  runtimeStore.diagnostics.find((item) => item.diagnostic_id === selectedDiagnosticId.value)
    ?? runtimeStore.diagnostics[0]
    ?? null,
);

const applyDisabled = computed(
  () =>
    runtimeStore.isPlanning
    || !selectedDiagnostic.value
    || !runtimeStore.readiness?.applyAllowed
    || !selectedDiagnostic.value.available_actions.includes("fix_permissions"),
);

const applyBlockedMessage = computed(
  () =>
    runtimeStore.readiness?.blockingReasons[0]
    ?? (!selectedDiagnostic.value ? "No diagnostic selected." : null),
);

const readinessStatus = computed<"ok" | "warning" | "error" | "unknown">(() => {
  if (!runtimeStore.readiness) {
    return "unknown";
  }
  return runtimeStore.readiness.applyAllowed ? "ok" : "error";
});

const repairResultStatus = computed<"ok" | "warning" | "error" | "unknown">(() => {
  const result = runtimeStore.repairResult;
  if (!result) {
    return "unknown";
  }
  if (result.status === "PASS") {
    return "ok";
  }
  if (result.status === "WARN") {
    return "warning";
  }
  if (result.status === "FAIL") {
    return "error";
  }
  return "unknown";
});

const confirmationItems = computed(() => [
  `asset=${selectedDiagnostic.value?.asset_id ?? "none"}`,
  `snapshot=${runtimeStore.readiness?.snapshotPlan.kind ?? "unavailable"}:${runtimeStore.readiness?.snapshotPlan.coverage ?? "unknown"}`,
  `undo=${runtimeStore.readiness?.undoVisibility.journalUndoAvailable ? "journal-visible" : "not-visible"}`,
  "restore=not-implemented",
]);

const confirmationNotes = computed(() => [
  ...(runtimeStore.readiness?.blockingReasons ?? []),
  ...(runtimeStore.readiness?.limitations ?? []),
]);

function toRepairActionStatus(
  status: string,
): "ok" | "warning" | "error" | "unknown" {
  if (status === "applied" || status === "repaired") {
    return "ok";
  }
  if (status === "planned" || status === "detected" || status === "skipped") {
    return "warning";
  }
  if (status === "failed") {
    return "error";
  }
  return "unknown";
}

function toRepairRunStatus(
  status: string,
): "ok" | "warning" | "error" | "unknown" {
  if (status === "completed") {
    return "ok";
  }
  if (status === "partial" || status === "planned" || status === "running") {
    return "warning";
  }
  if (status === "failed") {
    return "error";
  }
  return "unknown";
}

function formatModeChange(payload: Record<string, unknown>): string | null {
  const oldMode = payload["old_mode"];
  const newMode = payload["new_mode"];
  if (typeof oldMode !== "string" && typeof oldMode !== "number") {
    return null;
  }
  if (typeof newMode !== "string" && typeof newMode !== "number") {
    return null;
  }
  return `old=${String(oldMode)} new=${String(newMode)}`;
}

function formatErrorReason(
  details: Record<string, unknown> | null | undefined,
): string | null {
  const reason = details?.["reason"];
  return typeof reason === "string" ? reason : null;
}

async function planAction(action: SuggestedAction, apply: boolean): Promise<void> {
  if (!selectedDiagnostic.value) {
    return;
  }
  await runtimeStore.planRepair(selectedDiagnostic.value.diagnostic_id, action, apply);
}

function openApplyConfirmation(): void {
  if (applyDisabled.value) {
    return;
  }
  showApplyConfirmation.value = true;
}

async function confirmApply(): Promise<void> {
  showApplyConfirmation.value = false;
  await planAction("fix_permissions", true);
}

onMounted(async () => {
  await runtimeStore.load();
  selectedDiagnosticId.value = runtimeStore.diagnostics[0]?.diagnostic_id ?? null;
});
</script>
