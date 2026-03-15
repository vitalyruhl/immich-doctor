<template>
  <section class="state-card">
    <i class="pi pi-spin pi-spinner state-card__icon" />
    <h3>{{ title }}</h3>
    <p>{{ message }}</p>
  </section>
</template>

<script setup lang="ts">
defineProps<{
  title: string;
  message: string;
}>();
</script>
