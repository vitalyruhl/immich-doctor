<template>
  <header class="app-topbar">
    <button class="app-topbar__toggle" type="button" @click="$emit('toggle-sidebar')">
      <i class="pi pi-bars" />
    </button>
    <div>
      <p class="app-topbar__label">Safety-first operational surface</p>
      <strong>{{ title }}</strong>
    </div>
  </header>
</template>

<script setup lang="ts">
defineEmits<{
  (event: "toggle-sidebar"): void;
}>();

defineProps<{
  title: string;
}>();
</script>
