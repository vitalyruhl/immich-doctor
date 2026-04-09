import { computed, ref } from "vue";
import { defineStore } from "pinia";
import { ApiClientError } from "@/api/client";
import {
  fetchCatalogScanJob,
  fetchCatalogStatus,
  fetchCatalogZeroByte,
  startCatalogScanJob,
} from "@/api/catalog";
import type {
  CatalogRootRow,
  CatalogValidationReport,
  CatalogWorkflowJobRecord,
} from "@/api/types/catalog";

interface CatalogScanCoverageMetadata {
  effectiveRootSlugs?: string[];
  committedRootSlugs?: string[];
  missingRootSlugs?: string[];
  requiresScan?: boolean;
  hasCompleteCoverage?: boolean;
  activeSessions?: Array<Record<string, unknown>>;
}

function toErrorMessage(caughtError: unknown): string {
  return caughtError instanceof ApiClientError ? caughtError.payload.message : "Unknown error.";
}

function extractRoots(report: CatalogValidationReport | null): CatalogRootRow[] {
  const section = report?.sections.find((candidate) => candidate.name === "CATALOG_ROOTS");
  if (!section) {
    return [];
  }
  return section.rows as unknown as CatalogRootRow[];
}

function extractLatestSnapshots(report: CatalogValidationReport | null): Array<Record<string, unknown>> {
  const section = report?.sections.find((candidate) => candidate.name === "LATEST_SNAPSHOTS");
  if (!section) {
    return [];
  }
  return section.rows;
}

function extractScanCoverage(
  report: CatalogValidationReport | null,
): CatalogScanCoverageMetadata | null {
  const metadata = report?.metadata?.scanCoverage;
  return metadata && typeof metadata === "object"
    ? (metadata as CatalogScanCoverageMetadata)
    : null;
}

function normalizeSelectedRoot(
  requestedRoot: string | null,
  roots: CatalogRootRow[],
): string | null {
  if (requestedRoot && roots.some((root) => root.slug === requestedRoot)) {
    return requestedRoot;
  }
  if (roots.length === 1) {
    return roots[0].slug;
  }
  return null;
}

function isActiveScanJob(job: CatalogWorkflowJobRecord | null): boolean {
  return job !== null && ["pending", "running", "cancel_requested"].includes(job.state);
}

export const useCatalogStore = defineStore("catalog", () => {
  const statusReport = ref<CatalogValidationReport | null>(null);
  const zeroByteReport = ref<CatalogValidationReport | null>(null);
  const scanJob = ref<CatalogWorkflowJobRecord | null>(null);
  const roots = ref<CatalogRootRow[]>([]);
  const selectedRoot = ref<string | null>(null);
  const isLoading = ref(false);
  const isScanning = ref(false);
  const error = ref<string | null>(null);
  const scanError = ref<string | null>(null);

  async function loadReports(rootSlug: string | null = selectedRoot.value): Promise<void> {
    const statusResponse = await fetchCatalogStatus(rootSlug);
    const nextRoots = extractRoots(statusResponse.data);
    const normalizedRoot = normalizeSelectedRoot(rootSlug, nextRoots);
    const zeroByteResponse = await fetchCatalogZeroByte(normalizedRoot);
    statusReport.value = statusResponse.data;
    zeroByteReport.value = zeroByteResponse.data;
    roots.value = nextRoots;
    selectedRoot.value = normalizedRoot;
  }

  async function loadScanJob(): Promise<CatalogWorkflowJobRecord | null> {
    const wasActive = isActiveScanJob(scanJob.value);
    const response = await fetchCatalogScanJob();
    scanJob.value = response.data;
    if (wasActive && !isActiveScanJob(scanJob.value)) {
      await loadReports(selectedRoot.value);
    }
    return response.data;
  }

  async function load(rootSlug: string | null = selectedRoot.value): Promise<void> {
    isLoading.value = true;
    error.value = null;
    try {
      await Promise.all([loadReports(rootSlug), loadScanJob()]);
    } catch (caughtError) {
      error.value = toErrorMessage(caughtError);
    } finally {
      isLoading.value = false;
    }
  }

  async function refresh(): Promise<void> {
    await load(selectedRoot.value);
  }

  function setSelectedRoot(rootSlug: string | null): void {
    selectedRoot.value = rootSlug;
  }

  async function refreshScanJob(): Promise<CatalogWorkflowJobRecord | null> {
    scanError.value = null;
    try {
      return await loadScanJob();
    } catch (caughtError) {
      scanError.value = toErrorMessage(caughtError);
      return null;
    }
  }

  async function startScan(force = true): Promise<CatalogWorkflowJobRecord | null> {
    isScanning.value = true;
    scanError.value = null;
    try {
      const response = await startCatalogScanJob({ force });
      scanJob.value = response.data;
      return response.data;
    } catch (caughtError) {
      scanError.value = toErrorMessage(caughtError);
      return null;
    } finally {
      isScanning.value = false;
    }
  }

  const latestSnapshots = computed(() => extractLatestSnapshots(statusReport.value));
  const scanCoverage = computed(() => extractScanCoverage(statusReport.value));
  const hasCommittedSnapshot = computed(() =>
    latestSnapshots.value.some((row) => row.snapshot_id !== null),
  );
  const scanJobActive = computed(() => isActiveScanJob(scanJob.value));
  const shouldAutoStartScan = computed(() => !scanJobActive.value && Boolean(scanCoverage.value?.requiresScan));
  const rootCount = computed(() => roots.value.length);

  return {
    error,
    hasCommittedSnapshot,
    isLoading,
    isScanning,
    latestSnapshots,
    load,
    refresh,
    refreshScanJob,
    rootCount,
    roots,
    scanError,
    scanCoverage,
    scanJob,
    scanJobActive,
    selectedRoot,
    setSelectedRoot,
    shouldAutoStartScan,
    startScan,
    statusReport,
    zeroByteReport,
  };
});
