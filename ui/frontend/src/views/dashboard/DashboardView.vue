<template>
  <section class="page">
    <PageHeader
      eyebrow="Overview"
      title="Dashboard"
      summary="Operational overview for health, readiness, and safety posture."
    />
    <DisclaimerBanner />
    <RiskNotice
      title="Unknown stays visible"
      message="The dashboard intentionally keeps unknown states distinct from healthy states."
    />
    <RiskNotice
      v-if="healthStore.mocked"
      title="Mock mode is active"
      message="The dashboard is showing clearly marked mock data instead of backend truth."
    />

    <LoadingState
      v-if="healthStore.isLoading && !healthStore.hasLoaded"
      title="Loading health state"
      message="The dashboard is requesting backend or mock health data."
    />
    <ErrorState
      v-else-if="healthStore.error"
      title="Health request failed"
      :message="healthStore.error"
    />
    <template v-else>
      <article class="panel">
        <div class="health-card__header">
          <h3>Overall backend health</h3>
          <StatusTag :status="healthStore.overallStatus" />
        </div>
        <p class="health-card__summary">The dashboard aggregates current backend truth conservatively.</p>
        <p class="health-card__details">
          Last updated:
          {{ healthStore.generatedAt ? new Date(healthStore.generatedAt).toLocaleString() : "not loaded" }}
        </p>
      </article>
      <HealthStatusGrid :items="healthStore.items" />
    </template>

    <ConfirmOperationDialog
      :visible="false"
      title="Operation confirmation"
      summary="Confirmation dialogs are reserved for mutating workflows."
      :items="[]"
    />
  </section>
</template>

<script setup lang="ts">
import { onMounted } from "vue";
import ErrorState from "@/components/common/ErrorState.vue";
import LoadingState from "@/components/common/LoadingState.vue";
import PageHeader from "@/components/common/PageHeader.vue";
import StatusTag from "@/components/common/StatusTag.vue";
import HealthStatusGrid from "@/components/health/HealthStatusGrid.vue";
import ConfirmOperationDialog from "@/components/safety/ConfirmOperationDialog.vue";
import DisclaimerBanner from "@/components/safety/DisclaimerBanner.vue";
import RiskNotice from "@/components/safety/RiskNotice.vue";
import { useHealthStore } from "@/stores/health";

const healthStore = useHealthStore();

onMounted(async () => {
  await healthStore.load();
});
</script>
