<template>
  <span class="status-tag" :class="`status-tag--${status}`">{{ label }}</span>
</template>

<script setup lang="ts">
import { computed } from "vue";
import type { HealthState } from "@/api/types/common";

const props = defineProps<{
  status: HealthState;
}>();

const label = computed(() => props.status.toUpperCase());
</script>
