<template>
  <section class="page">
    <PageHeader
      eyebrow="Reports"
      title="Reports / Logs"
      summary="Structured reports, downloadable logs, and operation history will surface here."
    />
    <EmptyState
      title="Reports and logs placeholder"
      message="No downloadable backend data is faked here while endpoints are still missing."
    />
  </section>
</template>

<script setup lang="ts">
import EmptyState from "@/components/common/EmptyState.vue";
import PageHeader from "@/components/common/PageHeader.vue";
</script>
