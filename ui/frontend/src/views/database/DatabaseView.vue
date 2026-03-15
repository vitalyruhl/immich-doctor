<template>
  <section class="page">
    <PageHeader
      eyebrow="Database"
      title="Database"
      summary="Database diagnostics, performance, and schema-safe checks will surface here."
    />
    <EmptyState
      title="Database page placeholder"
      message="Prepared for health checks, performance indexes, and database-specific reports."
    />
  </section>
</template>

<script setup lang="ts">
import EmptyState from "@/components/common/EmptyState.vue";
import PageHeader from "@/components/common/PageHeader.vue";
</script>
