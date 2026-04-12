<template>
  <section class="page">
    <PageHeader
      eyebrow="Consistency"
      title="Consistency"
      summary="Review cached, snapshot-based storage-vs-database findings and stage explicit operator actions safely."
    />
    <DisclaimerBanner />

    <LoadingState
      v-if="consistencyStore.isLoading && !consistencyStore.catalogJob"
      title="Loading catalog consistency snapshot"
      message="Reading the latest cached consistency job state."
    />
    <ErrorState
      v-else-if="consistencyStore.catalogJobError && !consistencyStore.catalogReport"
      title="Consistency data unavailable"
      :message="consistencyStore.catalogJobError"
    />

    <template v-else>
      <CatalogConsistencyPanel />
      <CatalogRemediationPanel mode="findings" />
    </template>
  </section>
</template>

<script setup lang="ts">
import { onMounted } from "vue";
import CatalogConsistencyPanel from "@/components/consistency/CatalogConsistencyPanel.vue";
import CatalogRemediationPanel from "@/components/consistency/CatalogRemediationPanel.vue";
import DisclaimerBanner from "@/components/safety/DisclaimerBanner.vue";
import ErrorState from "@/components/common/ErrorState.vue";
import LoadingState from "@/components/common/LoadingState.vue";
import PageHeader from "@/components/common/PageHeader.vue";
import { useConsistencyStore } from "@/stores/consistency";

const consistencyStore = useConsistencyStore();

onMounted(async () => {
  await consistencyStore.load();
  await consistencyStore.ensureRemediationLoaded();
});
</script>
