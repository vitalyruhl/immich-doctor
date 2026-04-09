import { computed, ref } from "vue";
import { defineStore } from "pinia";
import { ApiClientError } from "@/api/client";
import { fetchHealthOverview } from "@/api/health";
import type { HealthItem } from "@/api/types/health";

function createUnknownItems(): HealthItem[] {
  return [
    {
      id: "immich-configured",
      title: "Immich configured",
      status: "unknown",
      summary: "Backend state not loaded yet.",
      details: "No request has completed yet.",
      updatedAt: new Date(0).toISOString(),
      blocking: true,
      source: "ui/unloaded",
    },
    {
      id: "immich-reachable",
      title: "Immich reachable",
      status: "unknown",
      summary: "Backend state not loaded yet.",
      details: "No request has completed yet.",
      updatedAt: new Date(0).toISOString(),
      blocking: true,
      source: "ui/unloaded",
    },
    {
      id: "db-reachability",
      title: "DB reachable",
      status: "unknown",
      summary: "Backend state not loaded yet.",
      details: "No request has completed yet.",
      updatedAt: new Date(0).toISOString(),
      blocking: true,
      source: "ui/unloaded",
    },
    {
      id: "storage-reachability",
      title: "Storage reachable",
      status: "unknown",
      summary: "Backend state not loaded yet.",
      details: "No request has completed yet.",
      updatedAt: new Date(0).toISOString(),
      blocking: true,
      source: "ui/unloaded",
    },
    {
      id: "path-readiness",
      title: "Path readiness",
      status: "unknown",
      summary: "Backend state not loaded yet.",
      details: "No request has completed yet.",
      updatedAt: new Date(0).toISOString(),
      blocking: false,
      source: "ui/unloaded",
    },
    {
      id: "consistency-readiness",
      title: "Consistency readiness",
      status: "unknown",
      summary: "Backend state not loaded yet.",
      details: "No request has completed yet.",
      updatedAt: new Date(0).toISOString(),
      blocking: false,
      source: "ui/unloaded",
    },
    {
      id: "backup-readiness",
      title: "Backup readiness",
      status: "unknown",
      summary: "Backend state not loaded yet.",
      details: "No request has completed yet.",
      updatedAt: new Date(0).toISOString(),
      blocking: false,
      source: "ui/unloaded",
    },
    {
      id: "scheduler-runtime-readiness",
      title: "Scheduler / runtime readiness",
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
  const hasLoaded = ref(false);
  const generatedAt = ref<string | null>(null);
  const overallStatus = ref<HealthItem["status"]>("unknown");

  async function load(): Promise<void> {
    isLoading.value = true;
    error.value = null;
    try {
      const response = await fetchHealthOverview();
      items.value = response.data.items;
      generatedAt.value = response.data.generatedAt;
      overallStatus.value = response.data.overallStatus;
      mocked.value = response.mocked;
      hasLoaded.value = true;
    } catch (caughtError) {
      error.value =
        caughtError instanceof ApiClientError ? caughtError.payload.message : "Unknown error.";
      mocked.value = false;
      overallStatus.value = "unknown";
    } finally {
      isLoading.value = false;
    }
  }

  const blockingItems = computed(() => items.value.filter((item) => item.blocking));

  return {
    blockingItems,
    error,
    generatedAt,
    hasLoaded,
    isLoading,
    items,
    load,
    mocked,
    overallStatus,
  };
});
