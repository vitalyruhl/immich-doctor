import { computed, ref } from "vue";
import { defineStore } from "pinia";

export const useAppStore = defineStore("app", () => {
  const sidebarCollapsed = ref(false);

  function toggleSidebar(): void {
    sidebarCollapsed.value = !sidebarCollapsed.value;
  }

  const shellMode = computed(() => (sidebarCollapsed.value ? "compact" : "expanded"));

  return {
    shellMode,
    sidebarCollapsed,
    toggleSidebar,
  };
});
