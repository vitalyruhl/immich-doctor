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
  scanJob: Record<string, unknown> | null;
  scanRuntime: Record<string, unknown> | null;
  scanJobActive: boolean;
  isLoading: boolean;
  isScanning: boolean;
  isLifecycleTransitioning: boolean;
  isActorTransitioning: ReturnType<typeof vi.fn>;
  error: string | null;
  scanError: string | null;
  load: ReturnType<typeof vi.fn>;
  refresh: ReturnType<typeof vi.fn>;
  refreshScanJob: ReturnType<typeof vi.fn>;
  startScan: ReturnType<typeof vi.fn>;
  pauseScan: ReturnType<typeof vi.fn>;
  resumeScan: ReturnType<typeof vi.fn>;
  stopScan: ReturnType<typeof vi.fn>;
  pauseScanActor: ReturnType<typeof vi.fn>;
  resumeScanActor: ReturnType<typeof vi.fn>;
  stopScanActor: ReturnType<typeof vi.fn>;
  requestScanWorkers: ReturnType<typeof vi.fn>;
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
  scanJob: {
    jobId: "catalog-scan-1",
    jobType: "catalog_inventory_scan",
    state: "completed",
    summary: "Catalog scan completed across 1 configured root.",
    result: {
      runtime: {
        scanState: "completed",
        configuredWorkerCount: 4,
        activeWorkerCount: 0,
        actors: [
          {
            actorId: "collector",
            role: "collector",
            state: "completed",
            currentRelativePath: null,
          },
          {
            actorId: "worker-1",
            role: "worker",
            state: "running",
            currentRelativePath: "26eef001-a2a1-4a88-a980-04ae572e2de0/00",
          },
          {
            actorId: "worker-2",
            role: "worker",
            state: "paused",
            currentRelativePath: null,
          },
        ],
        workerResize: {
          supported: false,
          semantics: "next_run_only",
          message: "Runtime worker resizing is not supported safely in the current architecture.",
        },
      },
      progress: {
        percent: 100,
        directoriesCompleted: 4,
        pendingDirectories: 0,
      },
    },
  },
  scanRuntime: {
    scanState: "completed",
    configuredWorkerCount: 4,
    activeWorkerCount: 0,
    actors: [
      {
        actorId: "collector",
        role: "collector",
        state: "completed",
        currentRelativePath: null,
      },
      {
        actorId: "worker-1",
        role: "worker",
        state: "running",
        currentRelativePath: "26eef001-a2a1-4a88-a980-04ae572e2de0/00",
      },
      {
        actorId: "worker-2",
        role: "worker",
        state: "paused",
        currentRelativePath: null,
      },
    ],
    workerResize: {
      supported: false,
      semantics: "next_run_only",
      message: "Runtime worker resizing is not supported safely in the current architecture.",
    },
  },
  scanJobActive: false,
  isLoading: false,
  isScanning: false,
  isLifecycleTransitioning: false,
  isActorTransitioning: vi.fn(() => false),
  error: null,
  scanError: null,
  load: vi.fn().mockResolvedValue(undefined),
  refresh: vi.fn().mockResolvedValue(undefined),
  refreshScanJob: vi.fn().mockResolvedValue(undefined),
  startScan: vi.fn().mockResolvedValue(undefined),
  pauseScan: vi.fn().mockResolvedValue(undefined),
  resumeScan: vi.fn().mockResolvedValue(undefined),
  stopScan: vi.fn().mockResolvedValue(undefined),
  pauseScanActor: vi.fn().mockResolvedValue(undefined),
  resumeScanActor: vi.fn().mockResolvedValue(undefined),
  stopScanActor: vi.fn().mockResolvedValue(undefined),
  requestScanWorkers: vi.fn().mockResolvedValue(undefined),
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
    expect(wrapper.text()).toContain("Directories: 4 / 4");
    expect(wrapper.text()).toContain("Configured workers: 4");
    expect(wrapper.text()).toContain("Active workers: 0");
    expect(wrapper.text()).toContain("Runtime actors");
    expect(wrapper.text()).toContain("Collector");
    expect(wrapper.text()).toContain("Worker 1");
    expect(wrapper.text()).not.toContain("Configured roots");
    expect(wrapper.text()).not.toContain("Zero-byte files");

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

    const pauseButton = wrapper.findAll("button").find((button) => button.text() === "Pause");
    expect(pauseButton).toBeTruthy();

    const resumeButton = wrapper.findAll("button").find((button) => button.text() === "Resume");
    expect(resumeButton).toBeTruthy();

    const stopButton = wrapper.findAll("button").find((button) => button.text() === "Stop");
    expect(stopButton).toBeTruthy();

    const actorCards = wrapper.findAll(".runtime-actor-card");
    expect(actorCards.length).toBeGreaterThanOrEqual(3);

    const runningWorkerCard = actorCards.find((card) => card.text().includes("Worker 1"));
    expect(runningWorkerCard).toBeTruthy();
    const workerPauseButton = runningWorkerCard!.findAll("button").find((button) => button.text() === "Pause");
    expect(workerPauseButton).toBeTruthy();
    await workerPauseButton!.trigger("click");
    expect(catalogStore.pauseScanActor).toHaveBeenCalledWith("worker-1");
    const workerStopButton = runningWorkerCard!.findAll("button").find((button) => button.text() === "Stop");
    expect(workerStopButton).toBeTruthy();
    await workerStopButton!.trigger("click");
    expect(catalogStore.stopScanActor).toHaveBeenCalledWith("worker-1");

    const pausedWorkerCard = actorCards.find((card) => card.text().includes("Worker 2"));
    expect(pausedWorkerCard).toBeTruthy();
    const workerResumeButton = pausedWorkerCard!.findAll("button").find((button) => button.text() === "Resume");
    expect(workerResumeButton).toBeTruthy();
    await workerResumeButton!.trigger("click");
    expect(catalogStore.resumeScanActor).toHaveBeenCalledWith("worker-2");
  });

  it("keeps cached storage status visible when a later request error exists", async () => {
    catalogStore.error = "Request timed out.";

    const wrapper = mount(StorageView, {
      global: {
        stubs: {
          PageHeader: { template: "<div><slot /></div>" },
          RiskNotice: { template: "<div><slot /></div>", props: ["title", "message"] },
          LoadingState: { template: "<div />" },
          ErrorState: { template: "<div class='error-stub'>error</div>" },
          EmptyState: { template: "<div>{{ title }} {{ message }}</div>", props: ["title", "message"] },
          StatusTag: { template: "<span>{{ status }}</span>", props: ["status"] },
        },
      },
    });

    await nextTick();
    await nextTick();

    expect(wrapper.text()).toContain("Storage index scan");
    expect(wrapper.text()).toContain("Request timed out.");
    expect(wrapper.text()).not.toContain("error");
  });
});
