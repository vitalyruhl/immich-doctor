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
      message="Collecting physical file checks and metadata failure diagnostics from the backend."
    />
    <ErrorState
      v-else-if="runtimeStore.error"
      title="Runtime diagnostics unavailable"
      :message="runtimeStore.error"
    />
    <template v-else>
      <section class="health-grid">
        <article class="panel" v-for="item in runtimeStore.integrity?.summary_items ?? []" :key="item.status">
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
              :disabled="runtimeStore.isPlanning"
              @click="planAction('fix_permissions', true)"
            >
              Apply fix_permissions
            </button>
          </section>

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
        <h3>Latest repair plan</h3>
        <p class="health-card__summary">{{ runtimeStore.repairResult.summary }}</p>
        <div v-for="action in runtimeStore.repairResult.repair_actions" :key="`${action.diagnostic_id}-${action.action}`">
          <strong>{{ action.action }}</strong>
          <p class="health-card__details">{{ action.reason }}</p>
        </div>
      </article>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import DisclaimerBanner from "@/components/safety/DisclaimerBanner.vue";
import EmptyState from "@/components/common/EmptyState.vue";
import ErrorState from "@/components/common/ErrorState.vue";
import LoadingState from "@/components/common/LoadingState.vue";
import PageHeader from "@/components/common/PageHeader.vue";
import RiskNotice from "@/components/safety/RiskNotice.vue";
import { useRuntimeStore } from "@/stores/runtime";
import type { SuggestedAction } from "@/api/types/runtime";

const runtimeStore = useRuntimeStore();
const selectedDiagnosticId = ref<string | null>(null);

const selectedDiagnostic = computed(() =>
  runtimeStore.diagnostics.find((item) => item.diagnostic_id === selectedDiagnosticId.value)
    ?? runtimeStore.diagnostics[0]
    ?? null,
);

async function planAction(action: SuggestedAction, apply: boolean): Promise<void> {
  if (!selectedDiagnostic.value) {
    return;
  }
  if (
    apply &&
    !window.confirm(
      `Apply ${action} for asset ${selectedDiagnostic.value.asset_id}? This changes runtime state.`,
    )
  ) {
    return;
  }
  await runtimeStore.planRepair(selectedDiagnostic.value.diagnostic_id, action, apply);
}

onMounted(async () => {
  await runtimeStore.load();
  selectedDiagnosticId.value = runtimeStore.diagnostics[0]?.diagnostic_id ?? null;
});
</script>
