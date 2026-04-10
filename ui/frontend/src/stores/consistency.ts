import { computed, ref } from "vue";
import { defineStore } from "pinia";
import { ApiClientError } from "@/api/client";
import {
  fetchCatalogConsistencyJob,
  fetchCatalogRemediationFindings,
  startCatalogConsistencyJob,
} from "@/api/consistency";
import type {
  CatalogValidationReport,
  CatalogWorkflowJobRecord,
} from "@/api/types/catalog";
import type {
  BrokenDbOriginalFinding,
  CatalogRemediationScanResponse,
  FuseHiddenOrphanFinding,
  ZeroByteFinding,
} from "@/api/types/consistency";

function toErrorMessage(caughtError: unknown): string {
  return caughtError instanceof ApiClientError
    ? caughtError.payload.message
    : "Unknown error.";
}

type CatalogReadinessState =
  | "ready"
  | "indexing"
  | "waiting_for_index"
  | "rebuilding"
  | "compare_running"
  | "error";

function catalogBlockedBy(
  job: CatalogWorkflowJobRecord | null,
): Record<string, unknown> | null {
  const result = job?.result;
  if (!result || typeof result !== "object") {
    return null;
  }
  const blockedBy = result.blockedBy;
  return blockedBy && typeof blockedBy === "object"
    ? (blockedBy as Record<string, unknown>)
    : null;
}

function catalogRequiresScan(job: CatalogWorkflowJobRecord | null): boolean {
  const result = job?.result;
  return Boolean(result && typeof result === "object" && result.requiresScan);
}

function sectionRows(
  report: CatalogValidationReport | null,
  sectionName: string,
): Array<Record<string, unknown>> {
  const section = report?.sections.find((candidate) => candidate.name === sectionName);
  return section ? (section.rows as Array<Record<string, unknown>>) : [];
}

export const useConsistencyStore = defineStore("consistency", () => {
  const remediationScanResult = ref<CatalogRemediationScanResponse | null>(null);
  const catalogJob = ref<CatalogWorkflowJobRecord | null>(null);
  const lastLoadedRemediationReportAt = ref<string | null>(null);

  const isLoading = ref(false);
  const isCatalogLoading = ref(false);
  const isCatalogStarting = ref(false);
  const isLoadingRemediation = ref(false);

  const catalogJobError = ref<string | null>(null);
  const remediationError = ref<string | null>(null);

  const catalogReport = computed<CatalogValidationReport | null>(() => {
    const candidate = catalogJob.value?.result?.report;
    return candidate && typeof candidate === "object"
      ? (candidate as CatalogValidationReport)
      : null;
  });

  const catalogReadinessState = computed<CatalogReadinessState>(() => {
    if (catalogJobError.value) {
      return "error";
    }
    const job = catalogJob.value;
    if (!job) {
      return "ready";
    }
    const blockedBy = catalogBlockedBy(job);
    if (blockedBy?.jobType === "catalog_inventory_scan") {
      return "indexing";
    }
    if (job.state === "running") {
      return "compare_running";
    }
    if (catalogRequiresScan(job)) {
      return "waiting_for_index";
    }
    const result =
      job.result && typeof job.result === "object"
        ? (job.result as Record<string, unknown>)
        : null;
    if (job.state === "pending" && result && Boolean(result.stale)) {
      return "rebuilding";
    }
    return "ready";
  });

  const isWaitingOnCatalog = computed(
    () =>
      catalogReadinessState.value === "indexing" ||
      catalogReadinessState.value === "waiting_for_index" ||
      catalogReadinessState.value === "rebuilding" ||
      catalogReadinessState.value === "compare_running",
  );

  const catalogReadinessTitle = computed(() => {
    switch (catalogReadinessState.value) {
      case "indexing":
        return "Consistency is waiting for storage indexing";
      case "waiting_for_index":
        return "Consistency is waiting for a current storage index";
      case "rebuilding":
        return "Consistency is rebuilding after the storage index changed";
      case "compare_running":
        return "Consistency compare is running";
      case "error":
        return "Consistency readiness could not be determined";
      default:
        return "Consistency data is ready";
    }
  });

  const catalogReadinessMessage = computed(() => {
    if (catalogJobError.value) {
      return catalogJobError.value;
    }
    if (catalogJob.value?.summary) {
      return catalogJob.value.summary;
    }
    return "Consistency findings become current after the catalog-backed storage index is ready.";
  });

  async function load(): Promise<void> {
    isLoading.value = true;
    try {
      await loadCatalogJob();
    } finally {
      isLoading.value = false;
    }
    if (catalogReport.value) {
      void loadRemediation();
    }
  }

  async function loadCatalogJob(): Promise<CatalogWorkflowJobRecord | null> {
    isCatalogLoading.value = true;
    catalogJobError.value = null;
    try {
      const response = await fetchCatalogConsistencyJob();
      catalogJob.value = response.data;
      if (catalogReport.value) {
        void loadRemediation();
      }
      return response.data;
    } catch (caughtError) {
      catalogJobError.value = toErrorMessage(caughtError);
      return null;
    } finally {
      isCatalogLoading.value = false;
    }
  }

  async function startCatalog(
    force = true,
  ): Promise<CatalogWorkflowJobRecord | null> {
    isCatalogStarting.value = true;
    catalogJobError.value = null;
    try {
      const response = await startCatalogConsistencyJob({ force });
      catalogJob.value = response.data;
      return response.data;
    } catch (caughtError) {
      catalogJobError.value = toErrorMessage(caughtError);
      return null;
    } finally {
      isCatalogStarting.value = false;
    }
  }

  async function loadRemediation(
    force = false,
  ): Promise<CatalogRemediationScanResponse | null> {
    const reportGeneratedAt = catalogReport.value?.generated_at ?? null;
    if (!force && !reportGeneratedAt) {
      return remediationScanResult.value;
    }
    if (
      !force &&
      remediationScanResult.value &&
      reportGeneratedAt === lastLoadedRemediationReportAt.value
    ) {
      return remediationScanResult.value;
    }

    isLoadingRemediation.value = true;
    remediationError.value = null;
    try {
      const response = await fetchCatalogRemediationFindings();
      remediationScanResult.value = response.data;
      lastLoadedRemediationReportAt.value = reportGeneratedAt;
      return response.data;
    } catch (caughtError) {
      remediationError.value = toErrorMessage(caughtError);
      return null;
    } finally {
      isLoadingRemediation.value = false;
    }
  }

  const brokenDbOriginals = computed<BrokenDbOriginalFinding[]>(
    () => remediationScanResult.value?.broken_db_originals ?? [],
  );
  const zeroByteFindings = computed<ZeroByteFinding[]>(
    () => remediationScanResult.value?.zero_byte_findings ?? [],
  );
  const fuseHiddenOrphans = computed<FuseHiddenOrphanFinding[]>(
    () => remediationScanResult.value?.fuse_hidden_orphans ?? [],
  );
  const storageOriginalsMissingInDb = computed(() =>
    sectionRows(catalogReport.value, "STORAGE_ORIGINALS_MISSING_IN_DB"),
  );
  const orphanDerivatives = computed(() =>
    sectionRows(catalogReport.value, "ORPHAN_DERIVATIVES_WITHOUT_ORIGINAL"),
  );
  const unmappedDatabasePaths = computed(() =>
    sectionRows(catalogReport.value, "UNMAPPED_DATABASE_PATHS"),
  );

  return {
    brokenDbOriginals,
    catalogJob,
    catalogJobError,
    catalogReadinessMessage,
    catalogReadinessState,
    catalogReadinessTitle,
    catalogReport,
    fuseHiddenOrphans,
    isCatalogLoading,
    isCatalogStarting,
    isLoading,
    isLoadingRemediation,
    isWaitingOnCatalog,
    load,
    loadCatalogJob,
    loadRemediation,
    orphanDerivatives,
    remediationError,
    remediationScanResult,
    startCatalog,
    storageOriginalsMissingInDb,
    unmappedDatabasePaths,
    zeroByteFindings,
  };
});
