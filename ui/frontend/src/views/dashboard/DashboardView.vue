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

    <LoadingState
      v-if="healthStore.isLoading && !healthStore.items.length"
      title="Loading health state"
      message="The dashboard is requesting backend or mock health data."
    />
    <ErrorState
      v-else-if="healthStore.error"
      title="Health request failed"
      :message="healthStore.error"
    />
    <HealthStatusGrid v-else :items="healthStore.items" />

    <ConfirmOperationDialog />
  </section>
</template>

<script setup lang="ts">
import { onMounted } from "vue";
import ErrorState from "@/components/common/ErrorState.vue";
import LoadingState from "@/components/common/LoadingState.vue";
import PageHeader from "@/components/common/PageHeader.vue";
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
