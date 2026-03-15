<template>
  <section class="page">
    <PageHeader
      eyebrow="Consistency"
      title="Consistency"
      summary="Category-first validation and repair planning will be exposed here."
    />
    <RiskNotice
      title="Dry-run before apply"
      message="Mutation-capable consistency actions must remain visibly separate from inspection."
    />
    <EmptyState
      title="Consistency workspace placeholder"
      message="Planned tabs: Overview, Analyze / Validate, Repair, History / Reports, Settings."
    />
  </section>
</template>

<script setup lang="ts">
import EmptyState from "@/components/common/EmptyState.vue";
import PageHeader from "@/components/common/PageHeader.vue";
import RiskNotice from "@/components/safety/RiskNotice.vue";
</script>
