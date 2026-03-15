<template>
  <div v-if="visible" class="confirm-dialog" role="dialog" aria-modal="true">
    <div class="confirm-dialog__backdrop" @click="$emit('cancel')" />
    <section class="confirm-dialog__panel">
      <p class="confirm-dialog__eyebrow">Apply confirmation</p>
      <h3>{{ title }}</h3>
      <p class="confirm-dialog__summary">{{ summary }}</p>
      <ul class="confirm-dialog__list">
        <li v-for="item in items" :key="item">{{ item }}</li>
      </ul>
      <ul v-if="notes.length" class="confirm-dialog__notes">
        <li v-for="note in notes" :key="note">{{ note }}</li>
      </ul>
      <div class="confirm-dialog__actions">
        <button type="button" class="runtime-action" @click="$emit('cancel')">
          {{ cancelLabel }}
        </button>
        <button
          type="button"
          class="runtime-action runtime-action--danger"
          :disabled="confirmDisabled"
          @click="$emit('confirm')"
        >
          {{ confirmLabel }}
        </button>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    visible: boolean;
    title: string;
    summary: string;
    items: string[];
    notes?: string[];
    confirmLabel?: string;
    cancelLabel?: string;
    confirmDisabled?: boolean;
  }>(),
  {
    notes: () => [],
    confirmLabel: "Confirm",
    cancelLabel: "Cancel",
    confirmDisabled: false,
  },
);

defineEmits<{
  cancel: [];
  confirm: [];
}>();
</script>
