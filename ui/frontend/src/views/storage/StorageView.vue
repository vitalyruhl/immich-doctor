<template>
  <section class="page">
    <PageHeader
      eyebrow="Storage"
      title="Storage"
      summary="Storage paths, mounts, and direct filesystem checks will live here."
    />
    <RiskNotice
      title="Container-path truth"
      message="Storage checks must reflect the runtime/container view instead of guessed host mappings."
    />
    <EmptyState
      title="Storage page placeholder"
      message="Prepared for path checks, mount safety, and future storage consistency results."
    />
  </section>
</template>

<script setup lang="ts">
import EmptyState from "@/components/common/EmptyState.vue";
import PageHeader from "@/components/common/PageHeader.vue";
import RiskNotice from "@/components/safety/RiskNotice.vue";
</script>
