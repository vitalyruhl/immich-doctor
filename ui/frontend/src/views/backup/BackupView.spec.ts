import { mount } from "@vue/test-utils";
import { nextTick } from "vue";
import BackupView from "./BackupView.vue";

const backupStore = {
  targetsOverview: {
    items: [
      {
        targetId: "target-1",
        targetName: "Local Backup",
        targetType: "local",
        enabled: true,
        transport: { path: "/backup" },
        verificationStatus: "ready",
        lastTestResult: {
          checkedAt: "2026-03-18T20:00:00+00:00",
          status: "ready",
          summary: "Target validation completed for currently implemented checks.",
          warnings: [],
          details: {},
        },
        lastSuccessfulBackup: null,
        retentionPolicy: { mode: "keep_all", maxVersions: null, pruneAutomatically: false },
        restoreReadiness: "not_implemented",
        sourceScope: "files_only",
        schedulingCompatible: true,
        warnings: [],
        createdAt: "2026-03-18T20:00:00+00:00",
        updatedAt: "2026-03-18T20:00:00+00:00",
      },
    ],
    limitations: [],
  },
  targets: [
    {
      targetId: "target-1",
      targetName: "Local Backup",
      targetType: "local",
      enabled: true,
      transport: { path: "/backup" },
      verificationStatus: "ready",
      lastTestResult: {
        checkedAt: "2026-03-18T20:00:00+00:00",
        status: "ready",
        summary: "Target validation completed for currently implemented checks.",
        warnings: [],
        details: {},
      },
      lastSuccessfulBackup: null,
      retentionPolicy: { mode: "keep_all", maxVersions: null, pruneAutomatically: false },
      restoreReadiness: "not_implemented",
      sourceScope: "files_only",
      schedulingCompatible: true,
      warnings: [],
      createdAt: "2026-03-18T20:00:00+00:00",
      updatedAt: "2026-03-18T20:00:00+00:00",
    },
  ],
  selectedTargetId: "target-1",
  selectedTarget: {
    targetId: "target-1",
    targetName: "Local Backup",
    targetType: "local",
    enabled: true,
    transport: { path: "/backup" },
    verificationStatus: "ready",
    lastTestResult: {
      checkedAt: "2026-03-18T20:00:00+00:00",
      status: "ready",
      summary: "Target validation completed for currently implemented checks.",
      warnings: [],
      details: {},
    },
    lastSuccessfulBackup: null,
    retentionPolicy: { mode: "keep_all", maxVersions: null, pruneAutomatically: false },
    restoreReadiness: "not_implemented",
    sourceScope: "files_only",
    schedulingCompatible: true,
    warnings: [],
    createdAt: "2026-03-18T20:00:00+00:00",
    updatedAt: "2026-03-18T20:00:00+00:00",
  },
  sizeEstimate: {
    summary: "Backup size collection completed with partial data for: Storage backup estimate.",
    state: "partial",
    warnings: [],
    scopes: [
      {
        scope: "storage",
        label: "Storage backup estimate",
        state: "completed",
        sourceScope: "/library",
        representation: "filesystem_usage",
        bytes: 2048,
        fileCount: 2,
        stale: false,
        categories: [],
        warnings: [],
        metadata: {},
      },
      {
        scope: "database",
        label: "Database backup estimate",
        state: "unsupported",
        sourceScope: "database",
        representation: "physical_db_size_proxy",
        bytes: null,
        fileCount: null,
        stale: false,
        categories: [],
        warnings: [],
        metadata: {},
      },
    ],
    limitations: [],
  },
  storageEstimate: {
    scope: "storage",
    label: "Storage backup estimate",
    state: "completed",
    sourceScope: "/library",
    representation: "filesystem_usage",
    bytes: 2048,
    fileCount: 2,
    stale: false,
    categories: [],
    warnings: [],
    metadata: {},
  },
  databaseEstimate: {
    scope: "database",
    label: "Database backup estimate",
    state: "unsupported",
    sourceScope: "database",
    representation: "physical_db_size_proxy",
    bytes: null,
    fileCount: null,
    stale: false,
    categories: [],
    warnings: [],
    metadata: {},
  },
  currentExecution: {
    state: "completed",
    summary: "Manual files-only backup completed. Restore execution remains unavailable.",
    targetType: "local",
    warnings: [],
    report: {
      verificationLevel: "destination_exists",
      bytesPlanned: 2048,
      bytesTransferred: 2048,
    },
    snapshot: {
      snapshotId: "snapshot-1",
      createdAt: "2026-03-18T20:00:00+00:00",
      kind: "manual",
      coverage: "files_only",
      repairRunId: null,
      manifestPath: "/data/manifests/backup/snapshots/snapshot-1.json",
      fileArtifactCount: 1,
      hasDbArtifact: false,
      basicValidity: "valid",
      validityMessage: "Snapshot manifest structure is valid. Artifact content is not verified here.",
    },
  },
  snapshots: {
    limitations: ["Current executable snapshot coverage is files-only."],
  },
  snapshotItems: [
    {
      snapshotId: "snapshot-1",
      createdAt: "2026-03-18T20:00:00+00:00",
      kind: "manual",
      coverage: "files_only",
      repairRunId: null,
      manifestPath: "/data/manifests/backup/snapshots/snapshot-1.json",
      fileArtifactCount: 1,
      hasDbArtifact: false,
      basicValidity: "valid",
      validityMessage: "Snapshot manifest structure is valid. Artifact content is not verified here.",
    },
  ],
  quarantine: {
    foundationState: "ok",
    path: "/data/quarantine",
    indexPresent: true,
    itemCount: 0,
  },
  hasTargets: true,
  isLoading: false,
  isSavingTarget: false,
  isExecuting: false,
  isExecutionRunning: false,
  isSizeCollectionRunning: false,
  isValidatingTarget: false,
  error: null,
  targetError: null,
  executionError: null,
  validationError: null,
  load: vi.fn().mockResolvedValue(undefined),
  saveTarget: vi.fn().mockResolvedValue(undefined),
  removeTarget: vi.fn().mockResolvedValue(undefined),
  validateTarget: vi.fn().mockResolvedValue(undefined),
  startExecution: vi.fn().mockResolvedValue(undefined),
  cancelExecution: vi.fn().mockResolvedValue(undefined),
  refreshSizeEstimate: vi.fn().mockResolvedValue(undefined),
  selectTarget: vi.fn(),
};

vi.mock("@/stores/backup", () => ({
  useBackupStore: () => backupStore,
}));

describe("BackupView", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders target management and non-blocking size visibility", async () => {
    const wrapper = mount(BackupView, {
      global: {
        stubs: {
          PageHeader: { template: "<div />" },
          RiskNotice: { template: "<div />" },
          LoadingState: { template: "<div />" },
          ErrorState: { template: "<div />" },
          EmptyState: { template: "<div />" },
          StatusTag: { template: "<span />", props: ["status"] },
        },
      },
    });

    await nextTick();
    await nextTick();

    expect(wrapper.text()).toContain("Source size estimate");
    expect(wrapper.text()).toContain("Local Backup");
    expect(wrapper.text()).toContain("Manual files-only backup completed. Restore execution remains unavailable.");
    expect(wrapper.text()).toContain("snapshot-1");
  });

  it("calls save and execution actions through the store", async () => {
    const wrapper = mount(BackupView, {
      global: {
        stubs: {
          PageHeader: { template: "<div />" },
          RiskNotice: { template: "<div />" },
          LoadingState: { template: "<div />" },
          ErrorState: { template: "<div />" },
          EmptyState: { template: "<div />" },
          StatusTag: { template: "<span />", props: ["status"] },
        },
      },
    });

    await nextTick();
    await nextTick();

    const form = wrapper.find("form");
    await form.trigger("submit");

    const buttons = wrapper.findAll("button");
    await buttons[0]?.trigger("click");

    expect(backupStore.saveTarget).toHaveBeenCalledTimes(1);
    expect(backupStore.startExecution).toHaveBeenCalled();
  });
});
