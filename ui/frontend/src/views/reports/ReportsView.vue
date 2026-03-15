<template>
  <section class="page">
    <PageHeader
      eyebrow="Reports"
      title="Reports / Logs"
      summary="Repair history and journal visibility are shown here before broader repair rollout."
    />
    <RiskNotice
      title="Undo visibility only"
      message="Journal-based undo information is visible here, but automated undo and full restore are not implemented yet."
    />

    <LoadingState
      v-if="repairStore.isLoading && !repairStore.runs"
      title="Loading repair history"
      message="Collecting persisted repair runs, journal entries, and quarantine foundation status."
    />
    <ErrorState
      v-else-if="repairStore.error"
      title="Repair history unavailable"
      :message="repairStore.error"
    />
    <template v-else>
      <section class="settings-grid">
        <article class="panel">
          <div class="settings-section__header">
            <div>
              <h3>Repair history</h3>
              <p>Persisted `RepairRun` state from the backend.</p>
            </div>
          </div>
          <p class="health-card__summary">{{ repairStore.runItems.length }} runs visible</p>
          <p class="health-card__details">
            Quarantine foundation: {{ repairStore.quarantine?.pathSummary ?? "Unavailable" }}
          </p>
        </article>

        <article class="panel">
          <div class="settings-section__header">
            <div>
              <h3>Quarantine foundation</h3>
              <p>Current visibility only, no move/restore workflow yet.</p>
            </div>
            <StatusTag :status="repairStore.quarantine?.foundationState ?? 'unknown'" />
          </div>
          <dl class="runtime-detail__grid">
            <dt>Path</dt>
            <dd>{{ repairStore.quarantine?.path ?? "Unavailable" }}</dd>
            <dt>Index present</dt>
            <dd>{{ repairStore.quarantine?.indexPresent ? "Yes" : "No" }}</dd>
            <dt>Indexed items</dt>
            <dd>{{ repairStore.quarantine?.itemCount ?? 0 }}</dd>
          </dl>
        </article>
      </section>

      <EmptyState
        v-if="!repairStore.runItems.length"
        title="No repair runs yet"
        message="A persisted repair run will appear here after a repair workflow creates one."
      />

      <section v-else class="runtime-grid">
        <article class="panel runtime-list">
          <h3>Repair runs</h3>
          <button
            v-for="run in repairStore.runItems"
            :key="run.repairRunId"
            type="button"
            class="runtime-list__item"
            :class="{ 'is-active': repairStore.selectedRun?.repairRun.repairRunId === run.repairRunId }"
            @click="repairStore.selectRun(run.repairRunId)"
          >
            <strong>{{ run.repairRunId }}</strong>
            <span>{{ run.status }}</span>
            <small>snapshot={{ run.preRepairSnapshotId ?? "none" }}</small>
          </button>
        </article>

        <article v-if="repairStore.selectedRun" class="panel runtime-detail">
          <div class="runtime-detail__header">
            <div>
              <h3>Repair run detail</h3>
              <p class="health-card__details">
                {{ repairStore.selectedRun.repairRun.repairRunId }}
              </p>
            </div>
            <StatusTag :status="toStatusTag(repairStore.selectedRun.repairRun.status)" />
          </div>

          <dl class="runtime-detail__grid">
            <dt>Started</dt>
            <dd>{{ repairStore.selectedRun.repairRun.startedAt }}</dd>
            <dt>Ended</dt>
            <dd>{{ repairStore.selectedRun.repairRun.endedAt ?? "Still open" }}</dd>
            <dt>Status</dt>
            <dd>{{ repairStore.selectedRun.repairRun.status }}</dd>
            <dt>Pre-repair snapshot</dt>
            <dd>{{ repairStore.selectedRun.repairRun.preRepairSnapshotId ?? "Not created" }}</dd>
            <dt>Journal entries</dt>
            <dd>{{ repairStore.selectedRun.repairRun.journalEntryCount }}</dd>
            <dt>Undo visible</dt>
            <dd>{{ repairStore.selectedRun.repairRun.undoAvailable ? "Yes" : "No" }}</dd>
            <dt>Plan token</dt>
            <dd>{{ repairStore.selectedRun.repairRun.planTokenId }}</dd>
          </dl>

          <section class="runtime-findings">
            <h4>Journal entries</h4>
            <article
              v-for="entry in repairStore.selectedRun.journalEntries"
              :key="entry.entryId"
              class="runtime-finding"
            >
              <strong>{{ entry.operationType }} / {{ entry.status }}</strong>
              <span>{{ entry.assetId ?? entry.originalPath ?? "No asset reference" }}</span>
              <small>undo={{ entry.undoType }}</small>
              <small v-if="formatModeChange(entry.undoPayload)">
                {{ formatModeChange(entry.undoPayload) }}
              </small>
              <small v-if="formatErrorReason(entry.errorDetails)">
                {{ formatErrorReason(entry.errorDetails) }}
              </small>
            </article>
          </section>

          <RiskNotice
            title="Restore limitation"
            :message="repairStore.selectedRun.limitations[1] ?? 'Full restore is not implemented yet.'"
          />
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
import { useRepairStore } from "@/stores/repair";

const repairStore = useRepairStore();

function toStatusTag(status: string): "ok" | "warning" | "error" | "unknown" {
  if (status === "completed") {
    return "ok";
  }
  if (status === "partial") {
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

onMounted(async () => {
  await repairStore.load();
});
</script>
