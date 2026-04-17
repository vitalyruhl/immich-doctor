import { computed, ref } from "vue";
import { defineStore } from "pinia";
import { ApiClientError } from "@/api/client";
import {
  deleteEmptyFolders,
  fetchEmptyFolderQuarantineList,
  fetchEmptyFolderScan,
  fetchEmptyFolderScanStatus,
  quarantineEmptyFolders,
  restoreEmptyFolders,
} from "@/api/storage";
import type {
  EmptyDirectoryFinding,
  EmptyDirQuarantineItem,
  EmptyFolderQuarantineActionResponse,
  EmptyFolderScanReport,
  EmptyFolderScanStatus,
} from "@/api/types/storage";

function toErrorMessage(caughtError: unknown): string {
  return caughtError instanceof ApiClientError ? caughtError.payload.message : "Unknown error.";
}

export const useStorageEmptyFoldersStore = defineStore("storage-empty-folders", () => {
  const selectedRoot = ref<string | null>(null);
  const scanReport = ref<EmptyFolderScanReport | null>(null);
  const scanStatus = ref<EmptyFolderScanStatus | null>(null);
  const quarantinedItems = ref<EmptyDirQuarantineItem[]>([]);
  const isLoading = ref(false);
  const isScanning = ref(false);
  const isApplyingAction = ref(false);
  const error = ref<string | null>(null);
  const actionError = ref<string | null>(null);
  const lastActionSummary = ref<string | null>(null);

  async function load(): Promise<void> {
    isLoading.value = true;
    error.value = null;
    try {
      const [statusResponse, quarantineResponse] = await Promise.all([
        fetchEmptyFolderScanStatus(),
        fetchEmptyFolderQuarantineList(),
      ]);
      scanStatus.value = statusResponse.data;
      quarantinedItems.value = quarantineResponse.data.items;
    } catch (caughtError) {
      error.value = toErrorMessage(caughtError);
    } finally {
      isLoading.value = false;
    }
  }

  async function runScan(): Promise<EmptyFolderScanReport | null> {
    isScanning.value = true;
    error.value = null;
    try {
      const response = await fetchEmptyFolderScan(selectedRoot.value);
      scanReport.value = response.data;
      const statusResponse = await fetchEmptyFolderScanStatus();
      scanStatus.value = statusResponse.data;
      return response.data;
    } catch (caughtError) {
      error.value = toErrorMessage(caughtError);
      return null;
    } finally {
      isScanning.value = false;
    }
  }

  async function refreshQuarantine(): Promise<void> {
    try {
      const response = await fetchEmptyFolderQuarantineList();
      quarantinedItems.value = response.data.items;
    } catch (caughtError) {
      actionError.value = toErrorMessage(caughtError);
    }
  }

  async function runAction(
    runner: () => Promise<EmptyFolderQuarantineActionResponse>,
  ): Promise<void> {
    isApplyingAction.value = true;
    actionError.value = null;
    lastActionSummary.value = null;
    try {
      const result = await runner();
      lastActionSummary.value = result.summary;
      if (Array.isArray(result.failed) && result.failed.length) {
        actionError.value = result.failed
          .slice(0, 3)
          .map((item) => String(item.reason ?? "Unknown failure."))
          .join(" ");
      }
      await Promise.all([refreshQuarantine(), runScan()]);
    } catch (caughtError) {
      actionError.value = toErrorMessage(caughtError);
    } finally {
      isApplyingAction.value = false;
    }
  }

  async function quarantineAll(dryRun: boolean): Promise<void> {
    await runAction(async () => {
      const response = await quarantineEmptyFolders({
        quarantine_all: true,
        dry_run: dryRun,
        root_slugs: selectedRoot.value ? [selectedRoot.value] : [],
      });
      return response.data;
    });
  }

  async function quarantinePath(finding: EmptyDirectoryFinding, dryRun: boolean): Promise<void> {
    await runAction(async () => {
      const response = await quarantineEmptyFolders({
        quarantine_all: false,
        dry_run: dryRun,
        paths: [finding.relative_path],
        root_slugs: [finding.root_slug],
      });
      return response.data;
    });
  }

  async function restoreItem(item: EmptyDirQuarantineItem, dryRun: boolean): Promise<void> {
    await runAction(async () => {
      const response = await restoreEmptyFolders(item.session_id, {
        restore_all: false,
        dry_run: dryRun,
        paths: [item.quarantine_item_id],
      });
      return response.data;
    });
  }

  async function deleteItem(item: EmptyDirQuarantineItem, dryRun: boolean): Promise<void> {
    await runAction(async () => {
      const response = await deleteEmptyFolders(item.session_id, {
        delete_all: false,
        dry_run: dryRun,
        paths: [item.quarantine_item_id],
      });
      return response.data;
    });
  }

  async function restoreAll(sessionId: string): Promise<void> {
    await runAction(async () => {
      const response = await restoreEmptyFolders(sessionId, {
        restore_all: true,
        dry_run: false,
      });
      return response.data;
    });
  }

  async function deleteAll(sessionId: string): Promise<void> {
    await runAction(async () => {
      const response = await deleteEmptyFolders(sessionId, {
        delete_all: true,
        dry_run: false,
      });
      return response.data;
    });
  }

  const groupedSessions = computed(() => {
    const sessions = new Map<string, EmptyDirQuarantineItem[]>();
    for (const item of quarantinedItems.value) {
      const current = sessions.get(item.session_id) ?? [];
      current.push(item);
      sessions.set(item.session_id, current);
    }
    return [...sessions.entries()].map(([sessionId, items]) => ({
      sessionId,
      items: [...items].sort((left, right) => left.relative_path.localeCompare(right.relative_path)),
    }));
  });

  return {
    actionError,
    deleteAll,
    deleteItem,
    error,
    groupedSessions,
    isApplyingAction,
    isLoading,
    isScanning,
    lastActionSummary,
    load,
    quarantineAll,
    quarantinePath,
    quarantinedItems,
    refreshQuarantine,
    restoreAll,
    restoreItem,
    runScan,
    scanReport,
    scanStatus,
    selectedRoot,
  };
});
