<template>
  <section class="state-card state-card--error">
    <i class="pi pi-times-circle state-card__icon" />
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
