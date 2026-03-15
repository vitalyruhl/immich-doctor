<template>
  <section class="page">
    <PageHeader
      eyebrow="Settings"
      title="Settings"
      summary="Read-only backend capability and configuration overview for operational settings."
    />

    <LoadingState
      v-if="settingsStore.isLoading && !settingsStore.overview"
      title="Loading settings capability"
      message="Inspecting backend settings support and current configuration shape."
    />
    <template v-else>
      <section class="panel settings-overview-card">
        <div>
          <p class="page-header__eyebrow">Capability state</p>
          <h3>Settings route is always navigable.</h3>
          <p class="settings-overview-card__summary">{{ settingsStore.capabilitySummary }}</p>
        </div>
        <CapabilityTag :state="settingsStore.capabilityState" />
      </section>

      <section class="settings-capability-grid">
        <article
          v-for="capability in settingsStore.capabilities"
          :key="capability.id"
          class="panel settings-capability-card"
        >
          <div class="settings-capability-card__header">
            <h3>{{ capability.title }}</h3>
            <CapabilityTag :state="capability.state" />
          </div>
          <p class="settings-capability-card__summary">{{ capability.summary }}</p>
          <p class="settings-capability-card__details">{{ capability.details }}</p>
        </article>
      </section>

      <EmptyState
        v-if="!settingsStore.sections.length"
        title="No settings sections available"
        message="The backend did not expose settings sections. The page remains available with safe capability reporting."
      />
      <section v-else class="settings-grid">
        <article v-for="section in settingsStore.sections" :key="section.id" class="panel">
          <div class="settings-section__header">
            <div>
              <h3>{{ section.title }}</h3>
              <p>{{ section.description }}</p>
            </div>
            <CapabilityTag :state="section.state" />
          </div>
          <p class="settings-section__summary">{{ section.summary }}</p>
          <dl v-if="section.fields.length" class="settings-section__fields">
            <template v-for="field in section.fields" :key="field.key">
              <dt>{{ field.label }}</dt>
              <dd>{{ field.value }}</dd>
            </template>
          </dl>
        </article>
      </section>
    </template>
  </section>
</template>

<script setup lang="ts">
import { onMounted } from "vue";
import CapabilityTag from "@/components/common/CapabilityTag.vue";
import EmptyState from "@/components/common/EmptyState.vue";
import LoadingState from "@/components/common/LoadingState.vue";
import PageHeader from "@/components/common/PageHeader.vue";
import { useSettingsStore } from "@/stores/settings";

const settingsStore = useSettingsStore();

onMounted(async () => {
  await settingsStore.load();
});
</script>
