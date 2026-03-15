<template>
  <span class="capability-tag" :class="`capability-tag--${stateClass}`">{{ state }}</span>
</template>

<script setup lang="ts">
import { computed } from "vue";
import type { SettingsCapabilityState } from "@/api/types/settings";

const props = defineProps<{
  state: SettingsCapabilityState;
}>();

const stateClass = computed(() => props.state.toLowerCase());
</script>
