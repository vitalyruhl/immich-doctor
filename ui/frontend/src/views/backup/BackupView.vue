<template>
  <section class="page">
    <PageHeader
      eyebrow="Backup"
      title="Backup"
      summary="Backup readiness and future backup operations will be managed here."
    />
    <RiskNotice
      title="Backup before repair"
      message="Repair-capable areas should surface backup recommendations before any apply action."
    />
    <EmptyState
      title="Backup page placeholder"
      message="Prepared for target readiness, backup planning, and future operation history."
    />
  </section>
</template>

<script setup lang="ts">
import EmptyState from "@/components/common/EmptyState.vue";
import PageHeader from "@/components/common/PageHeader.vue";
import RiskNotice from "@/components/safety/RiskNotice.vue";
</script>
