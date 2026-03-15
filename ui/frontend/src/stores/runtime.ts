import { computed, ref } from "vue";
import { defineStore } from "pinia";
import { ApiClientError } from "@/api/client";
import {
  fetchRuntimeIntegrityInspect,
  fetchRuntimeMetadataFailuresInspect,
  fetchRuntimeRepairReadiness,
  repairRuntimeMetadataFailures,
} from "@/api/runtime";
import { fetchRepairRunDetail } from "@/api/repair";
import type {
  MetadataFailureDiagnostic,
  RuntimeIntegrityInspectResponse,
  RuntimeMetadataFailuresInspectResponse,
  RuntimeMetadataFailuresRepairResponse,
  RuntimeRepairReadinessResponse,
  SuggestedAction,
} from "@/api/types/runtime";
import type { RepairRunDetailResponse } from "@/api/types/repair";

export const useRuntimeStore = defineStore("runtime", () => {
  const integrity = ref<RuntimeIntegrityInspectResponse | null>(null);
  const metadataFailures = ref<RuntimeMetadataFailuresInspectResponse | null>(null);
  const repairResult = ref<RuntimeMetadataFailuresRepairResponse | null>(null);
  const readiness = ref<RuntimeRepairReadinessResponse | null>(null);
  const repairRunDetail = ref<RepairRunDetailResponse | null>(null);
  const isLoading = ref(false);
  const isPlanning = ref(false);
  const error = ref<string | null>(null);
  const planError = ref<string | null>(null);

  async function load(): Promise<void> {
    isLoading.value = true;
    error.value = null;
    try {
      const [integrityResponse, metadataResponse, readinessResponse] = await Promise.all([
        fetchRuntimeIntegrityInspect(),
        fetchRuntimeMetadataFailuresInspect(),
        fetchRuntimeRepairReadiness(),
      ]);
      integrity.value = integrityResponse.data;
      metadataFailures.value = metadataResponse.data;
      readiness.value = readinessResponse.data;
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
      const repairRunId = String(response.data.metadata.repair_run_id ?? "");
      if (repairRunId) {
        repairRunDetail.value = (await fetchRepairRunDetail(repairRunId)).data;
      }
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
    readiness,
    repairResult,
    repairRunDetail,
  };
});
