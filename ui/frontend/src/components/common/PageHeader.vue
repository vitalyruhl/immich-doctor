<template>
  <header class="page-header">
    <div>
      <p class="page-header__eyebrow">{{ eyebrow }}</p>
      <h1>{{ title }}</h1>
      <p class="page-header__summary">{{ summary }}</p>
    </div>
    <slot />
  </header>
</template>

<script setup lang="ts">
defineProps<{
  eyebrow: string;
  title: string;
  summary: string;
}>();
</script>
