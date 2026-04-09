<template>
  <section class="page">
    <PageHeader
      eyebrow="Database"
      title="Database"
      summary="Current DB access, detected version signals, and schema compatibility status."
    />
    <DisclaimerBanner />
    <RiskNotice
      title="Current tested scope"
      :message="`Current validation and schema-safe checks are tested against Immich ${testedAgainstVersion}.`"
    />

    <LoadingState
      v-if="databaseStore.isLoading && !databaseStore.overview"
      title="Loading database overview"
      message="Requesting current DB access, version, and compatibility signals from the backend."
    />
    <ErrorState
      v-else-if="databaseStore.error && !databaseStore.overview"
      title="Database overview unavailable"
      :message="databaseStore.error"
    />

    <template v-else-if="overview">
      <article class="panel">
        <div class="health-card__header">
          <h3>Database overview</h3>
          <StatusTag :status="overview.connectivity.status" />
        </div>
        <p class="health-card__summary">{{ overview.connectivity.summary }}</p>
        <p class="health-card__details">
          Last updated: {{ formatDate(overview.generatedAt) }}
        </p>
      </article>

      <section class="health-grid">
        <article class="panel">
          <div class="health-card__header">
            <h3>Connectivity</h3>
            <StatusTag :status="overview.connectivity.status" />
          </div>
          <p class="health-card__summary">{{ overview.connectivity.summary }}</p>
          <p class="health-card__details">{{ overview.connectivity.details }}</p>
          <dl class="runtime-detail__grid">
            <dt>Engine</dt>
            <dd>{{ overview.connectivity.engine ?? "Unavailable" }}</dd>
            <dt>Host</dt>
            <dd>{{ overview.connectivity.host ?? "Unavailable" }}</dd>
            <dt>Port</dt>
            <dd>{{ overview.connectivity.port ?? "Unavailable" }}</dd>
            <dt>Database</dt>
            <dd>{{ overview.connectivity.databaseName ?? "Unavailable" }}</dd>
            <dt>Server version</dt>
            <dd>{{ overview.connectivity.serverVersion ?? "Unavailable" }}</dd>
          </dl>
          <p v-if="overview.connectivity.serverVersionError" class="runtime-blocking-message">
            {{ overview.connectivity.serverVersionError }}
          </p>
        </article>

        <article class="panel">
          <div class="health-card__header">
            <h3>Immich version signal</h3>
            <StatusTag :status="overview.immich.status" />
          </div>
          <p class="health-card__summary">{{ overview.immich.summary }}</p>
          <p class="health-card__details">{{ overview.immich.details }}</p>
          <dl class="runtime-detail__grid">
            <dt>Detected version</dt>
            <dd>{{ overview.immich.productVersionCurrent ?? "Unavailable" }}</dd>
            <dt>Confidence</dt>
            <dd>{{ overview.immich.productVersionConfidence }}</dd>
            <dt>Source</dt>
            <dd>{{ overview.immich.productVersionSource }}</dd>
            <dt>Support status</dt>
            <dd>{{ overview.immich.supportStatus }}</dd>
            <dt>Schema profile</dt>
            <dd class="runtime-detail__mono">{{ overview.immich.schemaGenerationKey ?? "Unavailable" }}</dd>
          </dl>
        </article>

        <article class="panel">
          <div class="health-card__header">
            <h3>Compatibility</h3>
            <StatusTag :status="overview.compatibility.status" />
          </div>
          <p class="health-card__summary">{{ overview.compatibility.summary }}</p>
          <p class="health-card__details">{{ overview.compatibility.details }}</p>
          <dl class="runtime-detail__grid">
            <dt>Tested against</dt>
            <dd>Immich {{ overview.compatibility.testedAgainstImmichVersion }}</dd>
            <dt>Detected version</dt>
            <dd>{{ overview.immich.productVersionCurrent ?? "Unknown" }}</dd>
            <dt>Schema support</dt>
            <dd>{{ overview.immich.supportStatus }}</dd>
          </dl>
        </article>

        <article class="panel">
          <div class="health-card__header">
            <h3>Related findings</h3>
            <StatusTag :status="overview.relatedFindings.status" />
          </div>
          <p class="health-card__summary">{{ overview.relatedFindings.summary }}</p>
          <p class="health-card__details">{{ overview.relatedFindings.details }}</p>
          <RouterLink class="runtime-action runtime-action--secondary" :to="overview.relatedFindings.route">
            Open consistency details
          </RouterLink>
        </article>
      </section>

      <section class="health-grid">
        <article class="panel">
          <div class="health-card__header">
            <h3>Risk flags</h3>
            <StatusTag :status="overview.immich.riskFlags.length ? 'warning' : 'ok'" />
          </div>
          <p class="health-card__summary">
            {{ overview.immich.riskFlags.length ? `${overview.immich.riskFlags.length} active signal(s)` : "No current schema risk flags reported." }}
          </p>
          <ul v-if="overview.immich.riskFlags.length" class="runtime-findings">
            <li v-for="flag in overview.immich.riskFlags" :key="flag" class="runtime-finding">
              <strong>{{ flag }}</strong>
            </li>
          </ul>
          <p v-else class="health-card__details">
            The current schema detector did not report additional risk flags.
          </p>
        </article>

        <article class="panel">
          <div class="health-card__header">
            <h3>Detection notes</h3>
            <StatusTag :status="overview.immich.notes.length ? 'warning' : 'unknown'" />
          </div>
          <p class="health-card__summary">
            {{ overview.immich.notes.length ? "Schema detector notes are available." : "No additional detector notes are available." }}
          </p>
          <ul v-if="overview.immich.notes.length" class="runtime-findings">
            <li v-for="note in overview.immich.notes" :key="note" class="runtime-finding">
              <strong>{{ note }}</strong>
            </li>
          </ul>
          <p v-else class="health-card__details">
            Deeper DB diagnostics can extend this page later without changing the current compatibility contract.
          </p>
        </article>
      </section>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted } from "vue";
import { RouterLink } from "vue-router";
import DisclaimerBanner from "@/components/safety/DisclaimerBanner.vue";
import ErrorState from "@/components/common/ErrorState.vue";
import LoadingState from "@/components/common/LoadingState.vue";
import PageHeader from "@/components/common/PageHeader.vue";
import RiskNotice from "@/components/safety/RiskNotice.vue";
import StatusTag from "@/components/common/StatusTag.vue";
import { useDatabaseStore } from "@/stores/database";

const databaseStore = useDatabaseStore();
const overview = computed(() => databaseStore.overview);
const testedAgainstVersion = computed(
  () => overview.value?.testedAgainstImmichVersion ?? "2.5.6",
);

function formatDate(value: string): string {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

onMounted(async () => {
  await databaseStore.load();
});
</script>
