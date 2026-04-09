<template>
  <section class="page settings-page">
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

      <section
        v-if="settingsStore.testbedDump?.enabled"
        class="panel settings-testbed-card"
      >
        <div class="settings-section__header">
          <div>
            <h3>Testbed dump reload</h3>
            <p>Local-only DB reload for the dev-testbed environment.</p>
          </div>
          <CapabilityTag :state="settingsStore.testbedDump.canImport ? 'READY' : 'PARTIAL'" />
        </div>
        <p class="settings-overview-card__summary">{{ settingsStore.testbedDump.summary }}</p>
        <div class="settings-testbed-card__stack">
          <dl class="settings-section__fields">
            <dt>Default dump path</dt>
            <dd>{{ settingsStore.testbedDump.defaultPath ?? "Not configured" }}</dd>
            <dt>Init mode</dt>
            <dd>{{ settingsStore.testbedDump.initMode }}</dd>
            <dt>Default format</dt>
            <dd>{{ settingsStore.testbedDump.defaultFormat }}</dd>
            <dt>Auto import on empty DB</dt>
            <dd>{{ settingsStore.testbedDump.autoImportOnEmpty ? "Enabled" : "Disabled" }}</dd>
          </dl>
        </div>
        <div class="settings-section__header">
          <div>
            <h3>Manual reload</h3>
            <p>
              The current testbed database will be recreated from the selected dump path.
              This control is intentionally unavailable outside <code>dev-testbed</code>.
            </p>
          </div>
        </div>
        <label class="backup-form__field">
          <span>Dump path</span>
          <input
            v-model="importPath"
            type="text"
            placeholder="Absolute dump path"
            :disabled="settingsStore.isImporting"
          />
        </label>
        <label class="backup-form__field">
          <span>Dump format</span>
          <select v-model="importFormat" :disabled="settingsStore.isImporting">
            <option value="auto">auto</option>
            <option value="plain">plain</option>
            <option value="custom">custom</option>
          </select>
        </label>
        <label class="consistency-disclaimer__check">
          <input
            v-model="importConfirmed"
            type="checkbox"
            :disabled="settingsStore.isImporting"
          />
          <span>I understand this recreates the current testbed database state.</span>
        </label>
        <div class="runtime-actions">
          <button
            class="runtime-action"
            type="button"
            :disabled="!canTriggerImport"
            @click="void triggerImport()"
          >
            {{ settingsStore.isImporting ? "Importing dump" : "Reload testbed DB" }}
          </button>
        </div>
        <p v-if="settingsStore.importError" class="runtime-blocking-message">
          {{ settingsStore.importError }}
        </p>
        <dl v-if="settingsStore.testbedImportResult" class="settings-section__fields">
          <dt>Last result</dt>
          <dd>{{ settingsStore.testbedImportResult.summary }}</dd>
          <dt>Classification</dt>
          <dd>{{ settingsStore.testbedImportResult.classification }}</dd>
          <dt>Effective path</dt>
          <dd>{{ settingsStore.testbedImportResult.effectivePath }}</dd>
          <dt>Meaningful errors</dt>
          <dd>{{ settingsStore.testbedImportResult.meaningfulErrorCount }}</dd>
        </dl>
      </section>

      <EmptyState
        v-if="!settingsStore.sections.length"
        title="No settings sections available"
        message="The backend did not expose settings sections. The page remains available with safe capability reporting."
      />
      <section v-else class="settings-grid settings-grid--stacked">
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
import { computed, onMounted, ref, watch } from "vue";
import CapabilityTag from "@/components/common/CapabilityTag.vue";
import EmptyState from "@/components/common/EmptyState.vue";
import LoadingState from "@/components/common/LoadingState.vue";
import PageHeader from "@/components/common/PageHeader.vue";
import { useSettingsStore } from "@/stores/settings";

const settingsStore = useSettingsStore();
const importPath = ref("");
const importFormat = ref("auto");
const importConfirmed = ref(false);

const canTriggerImport = computed(
  () =>
    Boolean(settingsStore.testbedDump?.canImport) &&
    Boolean(importPath.value.trim()) &&
    importConfirmed.value &&
    !settingsStore.isImporting,
);

watch(
  () => settingsStore.testbedDump,
  (value) => {
    importPath.value = value?.defaultPath ?? "";
    importFormat.value = value?.defaultFormat ?? "auto";
    importConfirmed.value = false;
  },
  { immediate: true },
);

async function triggerImport(): Promise<void> {
  if (!canTriggerImport.value) {
    return;
  }
  await settingsStore.triggerTestbedDumpImport({
    path: importPath.value.trim(),
    format: importFormat.value,
    force: true,
  });
}

onMounted(async () => {
  await settingsStore.load();
});
</script>
