import { mount } from "@vue/test-utils";
import { nextTick } from "vue";
import StorageView from "./StorageView.vue";

const catalogStore: {
  roots: Array<Record<string, unknown>>;
  selectedRoot: string | null;
  rootCount: number;
  hasCommittedSnapshot: boolean;
  shouldAutoStartScan: boolean;
  statusReport: Record<string, unknown>;
  zeroByteReport: Record<string, unknown>;
  scanJob: Record<string, unknown> | null;
  scanJobActive: boolean;
  isLoading: boolean;
  isScanning: boolean;
  error: string | null;
  scanError: string | null;
  load: ReturnType<typeof vi.fn>;
  refresh: ReturnType<typeof vi.fn>;
  refreshScanJob: ReturnType<typeof vi.fn>;
  startScan: ReturnType<typeof vi.fn>;
  setSelectedRoot: ReturnType<typeof vi.fn>;
} = {
  roots: [
    {
      id: 1,
      slug: "uploads",
      setting_name: "immich_uploads_path",
      root_type: "source",
      absolute_path: "/mnt/immich/storage/upload",
      enabled: 1,
      created_at: "2026-04-08T09:00:00+00:00",
      updated_at: "2026-04-08T09:00:00+00:00",
    },
  ],
  selectedRoot: "uploads",
  rootCount: 1,
  hasCommittedSnapshot: true,
  shouldAutoStartScan: false,
  statusReport: {
    domain: "analyze.catalog",
    action: "status",
    status: "PASS",
    summary: "Catalog status loaded 1 roots, 1 latest snapshots, and 1 scan sessions.",
    generated_at: "2026-04-08T09:00:00+00:00",
    metadata: {
      catalog_path: "/data/manifests/catalog/file-catalog.sqlite3",
    },
    checks: [],
    sections: [
      {
        name: "CATALOG_ROOTS",
        status: "pass",
        rows: [
          {
            id: 1,
            slug: "uploads",
            setting_name: "immich_uploads_path",
            root_type: "source",
            absolute_path: "/mnt/immich/storage/upload",
            enabled: 1,
            created_at: "2026-04-08T09:00:00+00:00",
            updated_at: "2026-04-08T09:00:00+00:00",
          },
        ],
      },
      {
        name: "LATEST_SNAPSHOTS",
        status: "pass",
        rows: [
          {
            root_slug: "uploads",
            root_type: "source",
            snapshot_id: 7,
            generation: 2,
            status: "committed",
            started_at: "2026-04-08T09:00:00+00:00",
            committed_at: "2026-04-08T09:02:00+00:00",
            item_count: 2,
            zero_byte_count: 1,
          },
        ],
      },
      {
        name: "SCAN_SESSIONS",
        status: "pass",
        rows: [
          {
            id: "session-1",
            status: "completed",
            started_at: "2026-04-08T09:00:00+00:00",
            heartbeat_at: "2026-04-08T09:02:00+00:00",
            completed_at: "2026-04-08T09:02:00+00:00",
            max_files: null,
            files_seen: 2,
            bytes_seen: 5,
            directories_completed: 1,
            error_count: 0,
            last_relative_path: "empty.jpg",
            snapshot_id: 7,
            root_slug: "uploads",
            root_type: "source",
            root_path: "/mnt/immich/storage/upload",
          },
        ],
      },
    ],
    metrics: [],
    recommendations: [],
  },
  zeroByteReport: {
    domain: "analyze.catalog",
    action: "zero-byte",
    status: "FAIL",
    summary: "Loaded 1 zero-byte file findings from the latest committed catalog snapshots.",
    generated_at: "2026-04-08T09:02:00+00:00",
    metadata: {
      catalog_path: "/data/manifests/catalog/file-catalog.sqlite3",
      root_slug: "uploads",
    },
    checks: [],
    sections: [
      {
        name: "ZERO_BYTE_FILES",
        status: "fail",
        rows: [
          {
            root_slug: "uploads",
            relative_path: "nested/empty.jpg",
            file_name: "empty.jpg",
            extension: ".jpg",
            size_bytes: 0,
            modified_at_fs: "2026-04-08T09:01:00+00:00",
            snapshot_id: 7,
            generation: 2,
          },
        ],
      },
    ],
    metrics: [],
    recommendations: [],
  },
  scanJob: {
    jobId: "catalog-scan-1",
    jobType: "catalog_inventory_scan",
    state: "completed",
    summary: "Catalog scan completed across 1 configured root.",
    result: {
      progress: {
        percent: 100,
        directoriesCompleted: 4,
        pendingDirectories: 0,
      },
    },
  },
  scanJobActive: false,
  isLoading: false,
  isScanning: false,
  error: null,
  scanError: null,
  load: vi.fn().mockResolvedValue(undefined),
  refresh: vi.fn().mockResolvedValue(undefined),
  refreshScanJob: vi.fn().mockResolvedValue(undefined),
  startScan: vi.fn().mockResolvedValue(undefined),
  setSelectedRoot: vi.fn((root: string | null) => {
    catalogStore.selectedRoot = root;
  }),
};

vi.mock("@/stores/catalog", () => ({
  useCatalogStore: () => catalogStore,
}));

describe("StorageView", () => {
  it("renders persisted catalog status and triggers rescans", async () => {
    const wrapper = mount(StorageView, {
      global: {
        stubs: {
          PageHeader: { template: "<div><slot /></div>" },
          RiskNotice: { template: "<div><slot /></div>", props: ["title", "message"] },
          LoadingState: { template: "<div />" },
          ErrorState: { template: "<div />" },
          EmptyState: { template: "<div>{{ title }} {{ message }}</div>", props: ["title", "message"] },
          StatusTag: { template: "<span>{{ status }}</span>", props: ["status"] },
        },
      },
    });

    await nextTick();
    await nextTick();

    expect(wrapper.text()).toContain("Storage index scan");
    expect(wrapper.text()).toContain("generation 2");
    expect(wrapper.text()).toContain("nested/empty.jpg");
    expect(wrapper.text()).toContain("Directories: 4 / 4");

    const runButton = wrapper
      .findAll("button")
      .find((button) => button.text() === "Rescan storage index");
    expect(runButton).toBeTruthy();

    await runButton!.trigger("click");
    expect(catalogStore.startScan).toHaveBeenCalledWith(true);

    const refreshButton = wrapper
      .findAll("button")
      .find((button) => button.text() === "Refresh status");
    expect(refreshButton).toBeTruthy();

    await refreshButton!.trigger("click");
    expect(catalogStore.refresh).toHaveBeenCalled();
  });
});
