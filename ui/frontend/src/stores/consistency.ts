import { computed, ref } from "vue";
import { defineStore } from "pinia";
import { ApiClientError } from "@/api/client";
import {
  applyCatalogBrokenDbActionDirect,
  applyCatalogFindingActionDirect,
  deleteCatalogQuarantine,
  fetchCatalogConsistencyJob,
  fetchCatalogIgnoredFindings,
  fetchCatalogQuarantine,
  fetchCatalogRemediationFindingDetail,
  fetchCatalogRemediationGroupPage,
  fetchCatalogRemediationOverview,
  ignoreCatalogFindings,
  quarantineCatalogFindings,
  refreshCatalogRemediationOverview,
  releaseCatalogIgnoredFindings,
  restoreCatalogQuarantine,
  startCatalogConsistencyJob,
} from "@/api/consistency";
import type {
  CatalogValidationReport,
  CatalogWorkflowJobRecord,
} from "@/api/types/catalog";
import type {
  CatalogIgnoredFindingsResponse,
  CatalogQuarantineResponse,
  CatalogRemediationActionResponse,
  CatalogRemediationFindingDetailResponse,
  CatalogRemediationGroupKey,
  CatalogRemediationGroupPageResponse,
  CatalogRemediationListItem,
  CatalogRemediationOverviewResponse,
  CatalogRemediationStateItemPayload,
  IgnoredFindingItem,
  QuarantineItemView,
} from "@/api/types/consistency";

function toErrorMessage(caughtError: unknown): string {
  return caughtError instanceof ApiClientError
    ? caughtError.payload.message
    : "Unknown error.";
}

function summarizeActionFailures(result: unknown): string | null {
  if (!result || typeof result !== "object" || !("items" in result)) {
    return null;
  }
  const items = Array.isArray(result.items) ? result.items : [];
  const failedItems = items.filter((item) => {
    if (!item || typeof item !== "object") {
      return false;
    }
    const status = String((item as Record<string, unknown>).status ?? "").toLowerCase();
    return status === "failed";
  });
  if (!failedItems.length) {
    return null;
  }
  const details = failedItems
    .slice(0, 3)
    .map((item) => String((item as Record<string, unknown>).message ?? "Unknown failure."))
    .join(" ");
  const suffix = failedItems.length > 3 ? ` (${failedItems.length} failed items total)` : "";
  return details + suffix;
}

type CatalogReadinessState =
  | "ready"
  | "indexing"
  | "waiting_for_index"
  | "rebuilding"
  | "compare_running"
  | "error";

type RemediationGroupPageState = {
  error: string | null;
  isLoading: boolean;
  items: CatalogRemediationListItem[];
  limit: number | null;
  loaded: boolean;
  offset: number;
  total: number;
};

type RemediationDetailState = {
  data: CatalogRemediationFindingDetailResponse | null;
  error: string | null;
  isLoading: boolean;
};

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
  const normalizedSectionName = sectionName.trim().toUpperCase();
  const section = report?.sections.find(
    (candidate) => String(candidate.name ?? "").trim().toUpperCase() === normalizedSectionName,
  );
  return section ? (section.rows as Array<Record<string, unknown>>) : [];
}

function createEmptyGroupPageState(): RemediationGroupPageState {
  return {
    error: null,
    isLoading: false,
    items: [],
    limit: 20,
    loaded: false,
    offset: 0,
    total: 0,
  };
}

export const useConsistencyStore = defineStore("consistency", () => {
  const remediationOverview = ref<CatalogRemediationOverviewResponse | null>(null);
  const remediationGroupPages = ref<
    Partial<Record<CatalogRemediationGroupKey, RemediationGroupPageState>>
  >({});
  const remediationFindingDetails = ref<
    Record<string, RemediationDetailState>
  >({});
  const catalogJob = ref<CatalogWorkflowJobRecord | null>(null);
  const ignoredState = ref<CatalogIgnoredFindingsResponse | null>(null);
  const quarantineState = ref<CatalogQuarantineResponse | null>(null);

  const isLoading = ref(false);
  const isCatalogLoading = ref(false);
  const isCatalogStarting = ref(false);
  const isLoadingRemediation = ref(false);
  const isRefreshingRemediation = ref(false);
  const isLoadingIgnored = ref(false);
  const isLoadingQuarantine = ref(false);
  const isApplyingAction = ref(false);

  const catalogJobError = ref<string | null>(null);
  const remediationError = ref<string | null>(null);
  const ignoredError = ref<string | null>(null);
  const quarantineError = ref<string | null>(null);
  const actionError = ref<string | null>(null);
  const lastActionSummary = ref<string | null>(null);

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

  const remediationLoaded = computed(() => remediationOverview.value !== null);
  const remediationGroups = computed(() => remediationOverview.value?.groups ?? []);

  function detailStateKey(groupKey: CatalogRemediationGroupKey, findingId: string): string {
    return `${groupKey}:${findingId}`;
  }

  function getGroupPageState(groupKey: CatalogRemediationGroupKey): RemediationGroupPageState {
    return remediationGroupPages.value[groupKey] ?? createEmptyGroupPageState();
  }

  function updateGroupPageState(
    groupKey: CatalogRemediationGroupKey,
    updater: (current: RemediationGroupPageState) => RemediationGroupPageState,
  ): void {
    const current = remediationGroupPages.value[groupKey] ?? createEmptyGroupPageState();
    remediationGroupPages.value = {
      ...remediationGroupPages.value,
      [groupKey]: updater(current),
    };
  }

  function updateFindingDetailState(
    groupKey: CatalogRemediationGroupKey,
    findingId: string,
    updater: (current: RemediationDetailState) => RemediationDetailState,
  ): void {
    const key = detailStateKey(groupKey, findingId);
    const current = remediationFindingDetails.value[key] ?? {
      data: null,
      error: null,
      isLoading: false,
    };
    remediationFindingDetails.value = {
      ...remediationFindingDetails.value,
      [key]: updater(current),
    };
  }

  async function load(): Promise<void> {
    isLoading.value = true;
    try {
      await Promise.all([
        loadCatalogJob(),
        loadIgnored(),
        loadQuarantine(),
        loadRemediationOverview(),
      ]);
    } finally {
      isLoading.value = false;
    }
  }

  async function loadCatalogJob(): Promise<CatalogWorkflowJobRecord | null> {
    isCatalogLoading.value = true;
    catalogJobError.value = null;
    try {
      const response = await fetchCatalogConsistencyJob();
      catalogJob.value = response.data;
      return response.data;
    } catch (caughtError) {
      catalogJobError.value = toErrorMessage(caughtError);
      return null;
    } finally {
      isCatalogLoading.value = false;
    }
  }

  async function startCatalog(force = true): Promise<CatalogWorkflowJobRecord | null> {
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

  async function loadRemediationOverview(): Promise<CatalogRemediationOverviewResponse | null> {
    isLoadingRemediation.value = true;
    remediationError.value = null;
    try {
      const response = await fetchCatalogRemediationOverview();
      remediationOverview.value = response.data;
      return response.data;
    } catch (caughtError) {
      remediationError.value = toErrorMessage(caughtError);
      return null;
    } finally {
      isLoadingRemediation.value = false;
    }
  }

  async function loadRemediationGroupPage(
    groupKey: CatalogRemediationGroupKey,
    options: {
      limit?: number | null;
      offset?: number;
    } = {},
  ): Promise<CatalogRemediationGroupPageResponse | null> {
    const current = getGroupPageState(groupKey);
    const limit = options.limit !== undefined ? options.limit : current.limit;
    const offset = options.offset !== undefined ? options.offset : current.offset;
    updateGroupPageState(groupKey, (state) => ({
      ...state,
      error: null,
      isLoading: true,
      limit,
      offset,
    }));
    try {
      const response = await fetchCatalogRemediationGroupPage(groupKey, { limit, offset });
      updateGroupPageState(groupKey, () => ({
        error: null,
        isLoading: false,
        items: response.data.items,
        limit: response.data.limit,
        loaded: true,
        offset: response.data.offset,
        total: response.data.total,
      }));
      return response.data;
    } catch (caughtError) {
      updateGroupPageState(groupKey, (state) => ({
        ...state,
        error: toErrorMessage(caughtError),
        isLoading: false,
      }));
      return null;
    }
  }

  async function loadRemediationFindingDetail(
    groupKey: CatalogRemediationGroupKey,
    findingId: string,
  ): Promise<CatalogRemediationFindingDetailResponse | null> {
    const current = remediationFindingDetails.value[detailStateKey(groupKey, findingId)];
    if (current?.data && !current.error) {
      return current.data;
    }
    updateFindingDetailState(groupKey, findingId, (state) => ({
      ...state,
      error: null,
      isLoading: true,
    }));
    try {
      const response = await fetchCatalogRemediationFindingDetail(groupKey, findingId);
      updateFindingDetailState(groupKey, findingId, () => ({
        data: response.data,
        error: null,
        isLoading: false,
      }));
      return response.data;
    } catch (caughtError) {
      updateFindingDetailState(groupKey, findingId, (state) => ({
        ...state,
        error: toErrorMessage(caughtError),
        isLoading: false,
      }));
      return null;
    }
  }

  async function refreshRemediation(): Promise<CatalogRemediationOverviewResponse | null> {
    isRefreshingRemediation.value = true;
    remediationError.value = null;
    try {
      const response = await refreshCatalogRemediationOverview();
      remediationOverview.value = response.data;
      const loadedGroups = Object.entries(remediationGroupPages.value)
        .filter(([, state]) => state?.loaded)
        .map(([groupKey, state]) => ({
          groupKey: groupKey as CatalogRemediationGroupKey,
          limit: state?.limit ?? 20,
          offset: state?.offset ?? 0,
        }));
      remediationFindingDetails.value = {};
      await Promise.all(
        loadedGroups.map(({ groupKey, limit, offset }) =>
          loadRemediationGroupPage(groupKey, { limit, offset }),
        ),
      );
      return response.data;
    } catch (caughtError) {
      remediationError.value = toErrorMessage(caughtError);
      return null;
    } finally {
      isRefreshingRemediation.value = false;
    }
  }

  async function refreshLoadedRemediationData(): Promise<void> {
    await loadRemediationOverview();
    remediationFindingDetails.value = {};
    await Promise.all(
      Object.entries(remediationGroupPages.value)
        .filter(([, state]) => state?.loaded)
        .map(([groupKey, state]) =>
          loadRemediationGroupPage(groupKey as CatalogRemediationGroupKey, {
            limit: state?.limit ?? 20,
            offset: state?.offset ?? 0,
          }),
        ),
    );
  }

  async function loadIgnored(): Promise<CatalogIgnoredFindingsResponse | null> {
    isLoadingIgnored.value = true;
    ignoredError.value = null;
    try {
      const response = await fetchCatalogIgnoredFindings();
      ignoredState.value = response.data;
      return response.data;
    } catch (caughtError) {
      ignoredError.value = toErrorMessage(caughtError);
      return null;
    } finally {
      isLoadingIgnored.value = false;
    }
  }

  async function loadQuarantine(): Promise<CatalogQuarantineResponse | null> {
    isLoadingQuarantine.value = true;
    quarantineError.value = null;
    try {
      const response = await fetchCatalogQuarantine();
      quarantineState.value = response.data;
      return response.data;
    } catch (caughtError) {
      quarantineError.value = toErrorMessage(caughtError);
      return null;
    } finally {
      isLoadingQuarantine.value = false;
    }
  }

  async function runWorkspaceAction(
    runner: () => Promise<
      CatalogIgnoredFindingsResponse | CatalogRemediationActionResponse | Record<string, unknown>
    >,
  ): Promise<void> {
    isApplyingAction.value = true;
    actionError.value = null;
    lastActionSummary.value = null;
    try {
      const result = await runner();
      lastActionSummary.value =
        typeof result === "object" && result !== null && "summary" in result
          ? String(result.summary)
          : "Action completed.";
      actionError.value = summarizeActionFailures(result);
      await Promise.all([loadIgnored(), loadQuarantine(), refreshLoadedRemediationData()]);
    } catch (caughtError) {
      actionError.value = toErrorMessage(caughtError);
    } finally {
      isApplyingAction.value = false;
    }
  }

  async function ignoreItems(items: CatalogRemediationStateItemPayload[]): Promise<void> {
    await runWorkspaceAction(async () => {
      const response = await ignoreCatalogFindings({ items });
      return response.data;
    });
  }

  async function quarantineItems(items: CatalogRemediationStateItemPayload[]): Promise<void> {
    await runWorkspaceAction(async () => {
      const response = await quarantineCatalogFindings({ items });
      return response.data;
    });
  }

  async function releaseIgnoredItems(ignoredItemIds: string[]): Promise<void> {
    await runWorkspaceAction(async () => {
      const response = await releaseCatalogIgnoredFindings({
        ignored_item_ids: ignoredItemIds,
      });
      return response.data;
    });
  }

  async function restoreQuarantineItems(quarantineItemIds: string[]): Promise<void> {
    await runWorkspaceAction(async () => {
      const response = await restoreCatalogQuarantine({
        quarantine_item_ids: quarantineItemIds,
      });
      return response.data;
    });
  }

  async function deleteQuarantineItemsPermanently(quarantineItemIds: string[]): Promise<void> {
    await runWorkspaceAction(async () => {
      const response = await deleteCatalogQuarantine({
        quarantine_item_ids: quarantineItemIds,
      });
      return response.data;
    });
  }

  async function applyBrokenDbAction(
    assetIds: string[],
    actionKind: "broken_db_cleanup" | "broken_db_path_fix",
  ): Promise<void> {
    isApplyingAction.value = true;
    actionError.value = null;
    lastActionSummary.value = null;
    try {
      const response = await applyCatalogBrokenDbActionDirect({
        asset_ids: assetIds,
        action_kind: actionKind,
      });
      lastActionSummary.value =
        typeof response.data.summary === "string"
          ? response.data.summary
          : "Action completed.";
      actionError.value = summarizeActionFailures(response.data);
      await Promise.all([loadCatalogJob(), loadIgnored(), loadQuarantine(), refreshRemediation()]);
    } catch (caughtError) {
      actionError.value = toErrorMessage(caughtError);
    } finally {
      isApplyingAction.value = false;
    }
  }

  async function applyFindingAction(
    findingIds: string[],
    actionKind: "zero_byte_delete" | "fuse_hidden_delete",
  ): Promise<void> {
    isApplyingAction.value = true;
    actionError.value = null;
    lastActionSummary.value = null;
    try {
      const response = await applyCatalogFindingActionDirect({
        finding_ids: findingIds,
        action_kind: actionKind,
      });
      lastActionSummary.value =
        typeof response.data.summary === "string"
          ? response.data.summary
          : "Action completed.";
      actionError.value = summarizeActionFailures(response.data);
      await Promise.all([loadCatalogJob(), loadIgnored(), loadQuarantine(), refreshRemediation()]);
    } catch (caughtError) {
      actionError.value = toErrorMessage(caughtError);
    } finally {
      isApplyingAction.value = false;
    }
  }

  const storageOriginalsMissingInDb = computed(() =>
    sectionRows(catalogReport.value, "STORAGE_ORIGINALS_MISSING_IN_DB"),
  );
  const orphanDerivatives = computed(() =>
    sectionRows(catalogReport.value, "ORPHAN_DERIVATIVES_WITHOUT_ORIGINAL"),
  );
  const unmappedDatabasePaths = computed(() =>
    sectionRows(catalogReport.value, "UNMAPPED_DATABASE_PATHS"),
  );
  const ignoredFindings = computed<IgnoredFindingItem[]>(
    () => ignoredState.value?.items ?? [],
  );
  const quarantinedItems = computed<QuarantineItemView[]>(
    () => quarantineState.value?.items ?? [],
  );
  const hiddenFindingIds = computed(() => {
    const ids = new Set<string>();
    for (const item of ignoredFindings.value) {
      ids.add(item.finding_id);
    }
    for (const item of quarantinedItems.value) {
      if (item.finding_id) {
        ids.add(item.finding_id);
      }
    }
    return ids;
  });

  return {
    actionError,
    applyFindingAction,
    applyBrokenDbAction,
    catalogJob,
    catalogJobError,
    catalogReadinessMessage,
    catalogReadinessState,
    catalogReadinessTitle,
    catalogReport,
    deleteQuarantineItemsPermanently,
    getGroupPageState,
    hiddenFindingIds,
    ignoreItems,
    ignoredError,
    ignoredFindings,
    ignoredState,
    isApplyingAction,
    isCatalogLoading,
    isCatalogStarting,
    isLoading,
    isLoadingIgnored,
    isLoadingQuarantine,
    isLoadingRemediation,
    isRefreshingRemediation,
    isWaitingOnCatalog,
    lastActionSummary,
    load,
    loadCatalogJob,
    loadIgnored,
    loadQuarantine,
    loadRemediationFindingDetail,
    loadRemediationGroupPage,
    loadRemediationOverview,
    orphanDerivatives,
    quarantineError,
    quarantineItems,
    quarantineState,
    quarantinedItems,
    refreshRemediation,
    remediationError,
    remediationFindingDetails,
    remediationGroups,
    remediationLoaded,
    remediationOverview,
    releaseIgnoredItems,
    restoreQuarantineItems,
    startCatalog,
    storageOriginalsMissingInDb,
    unmappedDatabasePaths,
  };
});
