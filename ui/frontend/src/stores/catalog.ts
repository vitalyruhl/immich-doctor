import { computed, ref } from "vue";
import { defineStore } from "pinia";
import { ApiClientError } from "@/api/client";
import { fetchCatalogStatus, fetchCatalogZeroByte, startCatalogScan } from "@/api/catalog";
import type {
  CatalogRootRow,
  CatalogScanRequest,
  CatalogValidationReport,
} from "@/api/types/catalog";

function extractRoots(report: CatalogValidationReport | null): CatalogRootRow[] {
  const section = report?.sections.find((candidate) => candidate.name === "CATALOG_ROOTS");
  if (!section) {
    return [];
  }
  return section.rows as unknown as CatalogRootRow[];
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

export const useCatalogStore = defineStore("catalog", () => {
  const statusReport = ref<CatalogValidationReport | null>(null);
  const zeroByteReport = ref<CatalogValidationReport | null>(null);
  const scanReport = ref<CatalogValidationReport | null>(null);
  const roots = ref<CatalogRootRow[]>([]);
  const selectedRoot = ref<string | null>(null);
  const isLoading = ref(false);
  const isScanning = ref(false);
  const error = ref<string | null>(null);
  const scanError = ref<string | null>(null);

  async function load(rootSlug: string | null = selectedRoot.value): Promise<void> {
    isLoading.value = true;
    error.value = null;
    try {
      const [statusResponse, zeroByteResponse] = await Promise.all([
        fetchCatalogStatus(rootSlug),
        fetchCatalogZeroByte(rootSlug),
      ]);
      statusReport.value = statusResponse.data;
      zeroByteReport.value = zeroByteResponse.data;
      roots.value = extractRoots(statusResponse.data);
      selectedRoot.value = normalizeSelectedRoot(rootSlug, roots.value);
    } catch (caughtError) {
      error.value =
        caughtError instanceof ApiClientError ? caughtError.payload.message : "Unknown error.";
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

  async function scan(rootSlug: string | null = selectedRoot.value): Promise<void> {
    let targetRoot = rootSlug;
    if (!targetRoot && roots.value.length === 1) {
      targetRoot = roots.value[0].slug;
    }
    if (!targetRoot) {
      scanError.value = "Select a storage root before starting a catalog scan.";
      return;
    }

    isScanning.value = true;
    scanError.value = null;
    try {
      const payload: CatalogScanRequest = { root: targetRoot };
      const response = await startCatalogScan(payload);
      scanReport.value = response.data;
      selectedRoot.value = targetRoot;
      await load(targetRoot);
    } catch (caughtError) {
      scanError.value =
        caughtError instanceof ApiClientError ? caughtError.payload.message : "Unknown error.";
    } finally {
      isScanning.value = false;
    }
  }

  const rootCount = computed(() => roots.value.length);

  return {
    error,
    isLoading,
    isScanning,
    load,
    refresh,
    rootCount,
    roots,
    scan,
    scanError,
    scanReport,
    selectedRoot,
    setSelectedRoot,
    statusReport,
    zeroByteReport,
  };
});
