<template>
  <nav class="breadcrumbs" aria-label="Breadcrumb">
    <span>immich-doctor</span>
    <i class="pi pi-angle-right" />
    <span>{{ section }}</span>
    <i class="pi pi-angle-right" />
    <strong>{{ title }}</strong>
  </nav>
</template>

<script setup lang="ts">
defineProps<{
  section: string;
  title: string;
}>();
</script>
