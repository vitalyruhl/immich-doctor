<template>
  <section class="health-grid">
    <HealthStatusCard v-for="item in items" :key="item.id" :item="item" />
  </section>
</template>

<script setup lang="ts">
import type { HealthItem } from "@/api/types/health";
import HealthStatusCard from "./HealthStatusCard.vue";

defineProps<{
  items: HealthItem[];
}>();
</script>
