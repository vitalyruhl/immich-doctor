import { computed, ref } from "vue";
import { defineStore } from "pinia";
import { ApiClientError } from "@/api/client";
import { fetchHealthOverview } from "@/api/health";
import type { HealthItem } from "@/api/types/health";

function createUnknownItems(): HealthItem[] {
  return [
    {
      id: "immich-connectivity",
      title: "Immich connectivity",
      status: "unknown",
      summary: "Backend state not loaded yet.",
      details: "No request has completed yet.",
      updatedAt: new Date(0).toISOString(),
      blocking: true,
      source: "ui/unloaded",
    },
    {
      id: "db-reachability",
      title: "DB reachability",
      status: "unknown",
      summary: "Backend state not loaded yet.",
      details: "No request has completed yet.",
      updatedAt: new Date(0).toISOString(),
      blocking: true,
      source: "ui/unloaded",
    },
    {
      id: "storage-reachability",
      title: "Storage reachability",
      status: "unknown",
      summary: "Backend state not loaded yet.",
      details: "No request has completed yet.",
      updatedAt: new Date(0).toISOString(),
      blocking: true,
      source: "ui/unloaded",
    },
    {
      id: "path-consistency-readiness",
      title: "Path consistency readiness",
      status: "unknown",
      summary: "Backend state not loaded yet.",
      details: "No request has completed yet.",
      updatedAt: new Date(0).toISOString(),
      blocking: false,
      source: "ui/unloaded",
    },
    {
      id: "backup-target-readiness",
      title: "Backup target readiness",
      status: "unknown",
      summary: "Backend state not loaded yet.",
      details: "No request has completed yet.",
      updatedAt: new Date(0).toISOString(),
      blocking: false,
      source: "ui/unloaded",
    },
    {
      id: "scheduler-runtime-readiness",
      title: "Scheduler/runtime readiness",
      status: "unknown",
      summary: "Backend state not loaded yet.",
      details: "No request has completed yet.",
      updatedAt: new Date(0).toISOString(),
      blocking: false,
      source: "ui/unloaded",
    },
  ];
}

export const useHealthStore = defineStore("health", () => {
  const items = ref<HealthItem[]>(createUnknownItems());
  const isLoading = ref(false);
  const error = ref<string | null>(null);
  const mocked = ref(false);

  async function load(): Promise<void> {
    isLoading.value = true;
    error.value = null;
    try {
      const response = await fetchHealthOverview();
      items.value = response.data.items;
      mocked.value = response.mocked;
    } catch (caughtError) {
      error.value =
        caughtError instanceof ApiClientError ? caughtError.payload.message : "Unknown error.";
    } finally {
      isLoading.value = false;
    }
  }

  const blockingItems = computed(() => items.value.filter((item) => item.blocking));

  return {
    blockingItems,
    error,
    isLoading,
    items,
    load,
    mocked,
  };
});
