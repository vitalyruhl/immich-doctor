<template>
  <section class="page">
    <PageHeader
      eyebrow="Consistency / Quarantine"
      title="Quarantine"
      summary="Review quarantined consistency findings, restore them when needed, or delete them permanently from the dedicated quarantine workspace."
    />
    <DisclaimerBanner />
    <CatalogRemediationPanel mode="quarantine" />
  </section>
</template>

<script setup lang="ts">
import { onMounted } from "vue";
import CatalogRemediationPanel from "@/components/consistency/CatalogRemediationPanel.vue";
import DisclaimerBanner from "@/components/safety/DisclaimerBanner.vue";
import PageHeader from "@/components/common/PageHeader.vue";
import { useConsistencyStore } from "@/stores/consistency";

const consistencyStore = useConsistencyStore();

onMounted(async () => {
  await consistencyStore.load();
});
</script>
