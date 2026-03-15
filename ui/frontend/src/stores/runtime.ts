import { computed, ref } from "vue";
import { defineStore } from "pinia";
import { ApiClientError } from "@/api/client";
import {
  fetchRuntimeIntegrityInspect,
  fetchRuntimeMetadataFailuresInspect,
  repairRuntimeMetadataFailures,
} from "@/api/runtime";
import type {
  MetadataFailureDiagnostic,
  RuntimeIntegrityInspectResponse,
  RuntimeMetadataFailuresInspectResponse,
  RuntimeMetadataFailuresRepairResponse,
  SuggestedAction,
} from "@/api/types/runtime";

export const useRuntimeStore = defineStore("runtime", () => {
  const integrity = ref<RuntimeIntegrityInspectResponse | null>(null);
  const metadataFailures = ref<RuntimeMetadataFailuresInspectResponse | null>(null);
  const repairResult = ref<RuntimeMetadataFailuresRepairResponse | null>(null);
  const isLoading = ref(false);
  const isPlanning = ref(false);
  const error = ref<string | null>(null);
  const planError = ref<string | null>(null);

  async function load(): Promise<void> {
    isLoading.value = true;
    error.value = null;
    try {
      const [integrityResponse, metadataResponse] = await Promise.all([
        fetchRuntimeIntegrityInspect(),
        fetchRuntimeMetadataFailuresInspect(),
      ]);
      integrity.value = integrityResponse.data;
      metadataFailures.value = metadataResponse.data;
    } catch (caughtError) {
      error.value =
        caughtError instanceof ApiClientError ? caughtError.payload.message : "Unknown error.";
    } finally {
      isLoading.value = false;
    }
  }

  async function planRepair(diagnosticId: string, action: SuggestedAction, apply: boolean): Promise<void> {
    isPlanning.value = true;
    planError.value = null;
    try {
      const response = await repairRuntimeMetadataFailures(diagnosticId, action, apply);
      repairResult.value = response.data;
      if (apply) {
        await load();
      }
    } catch (caughtError) {
      planError.value =
        caughtError instanceof ApiClientError ? caughtError.payload.message : "Unknown error.";
    } finally {
      isPlanning.value = false;
    }
  }

  const diagnostics = computed<MetadataFailureDiagnostic[]>(
    () => metadataFailures.value?.diagnostics ?? [],
  );

  return {
    diagnostics,
    error,
    integrity,
    isLoading,
    isPlanning,
    load,
    metadataFailures,
    planError,
    planRepair,
    repairResult,
  };
});
