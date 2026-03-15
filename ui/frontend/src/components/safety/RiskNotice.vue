<template>
  <section class="risk-notice">
    <strong>{{ title }}</strong>
    <p>{{ message }}</p>
  </section>
</template>

<script setup lang="ts">
defineProps<{
  title: string;
  message: string;
}>();
</script>
