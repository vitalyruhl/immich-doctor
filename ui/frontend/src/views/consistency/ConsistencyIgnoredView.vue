<template>
  <section class="page">
    <PageHeader
      eyebrow="Consistency / Ignored"
      title="Ignored Findings"
      summary="Inspect active ignore decisions and release them back into the consistency findings workflow when they should be reviewed again."
    />
    <DisclaimerBanner />
    <CatalogRemediationPanel mode="ignored" />
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
