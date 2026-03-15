<template>
  <article class="health-card">
    <div class="health-card__header">
      <h3>{{ item.title }}</h3>
      <StatusTag :status="item.status" />
    </div>
    <p class="health-card__summary">{{ item.summary }}</p>
    <p class="health-card__details">{{ item.details }}</p>
    <footer class="health-card__footer">
      <span>{{ item.source }}</span>
      <span>{{ new Date(item.updatedAt).toLocaleString() }}</span>
    </footer>
  </article>
</template>

<script setup lang="ts">
import type { HealthItem } from "@/api/types/health";
import StatusTag from "@/components/common/StatusTag.vue";

defineProps<{
  item: HealthItem;
}>();
</script>
