<template>
  <section class="page">
    <PageHeader
      eyebrow="Settings"
      title="Settings"
      summary="Operational settings structure for database, storage, backup, and runtime."
    />

    <LoadingState
      v-if="settingsStore.isLoading && !settingsStore.sections.length"
      title="Loading settings structure"
      message="Fetching backend or mock settings shell."
    />
    <ErrorState
      v-else-if="settingsStore.error"
      title="Settings request failed"
      :message="settingsStore.error"
    />
    <section v-else class="settings-grid">
      <article v-for="section in settingsStore.sections" :key="section.id" class="panel">
        <h3>{{ section.title }}</h3>
        <p>{{ section.description }}</p>
      </article>
    </section>
  </section>
</template>

<script setup lang="ts">
import { onMounted } from "vue";
import ErrorState from "@/components/common/ErrorState.vue";
import LoadingState from "@/components/common/LoadingState.vue";
import PageHeader from "@/components/common/PageHeader.vue";
import { useSettingsStore } from "@/stores/settings";

const settingsStore = useSettingsStore();

onMounted(async () => {
  await settingsStore.load();
});
</script>
