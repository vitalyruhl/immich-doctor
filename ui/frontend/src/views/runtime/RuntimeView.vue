<template>
  <section class="page">
    <PageHeader
      eyebrow="Runtime"
      title="Runtime / Health"
      summary="Health and readiness surfaces will live here."
    />
    <RiskNotice
      title="Read-only focus"
      message="Runtime diagnostics are shown before any mutation-capable workflows exist."
    />
    <EmptyState
      title="Runtime overview placeholder"
      message="This page is ready for runtime checks, scheduler readiness, and execution blockers."
    />
  </section>
</template>

<script setup lang="ts">
import EmptyState from "@/components/common/EmptyState.vue";
import PageHeader from "@/components/common/PageHeader.vue";
import RiskNotice from "@/components/safety/RiskNotice.vue";
</script>
