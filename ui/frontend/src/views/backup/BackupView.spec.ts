import { mount } from "@vue/test-utils";
import { nextTick } from "vue";
import BackupView from "./BackupView.vue";

function createLocalTarget() {
  return {
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
  };
}

const backupStore: any = {
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
    summary: "Source size estimate completed with partial data for: Storage backup estimate.",
    state: "partial",
    status: "partial",
    staleReason: null,
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
    summary: "Check/sync copied 1 missing assets and verified 1. 0 mismatches, 0 conflicts, and 0 restore candidates still require review.",
    targetType: "local",
    warnings: [],
    report: {
      verificationLevel: "copied_files_sha256",
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
  validatingTargetId: null,
  activeValidation: null,
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

function resetMockStore(): void {
  const target = createLocalTarget();
  backupStore.targetsOverview = {
    items: [target],
    limitations: [],
  };
  backupStore.targets = [target];
  backupStore.selectedTargetId = target.targetId;
  backupStore.selectedTarget = target;
  backupStore.sizeEstimate = {
    summary: "Source size estimate completed with partial data for: Storage backup estimate.",
    state: "partial",
    status: "partial",
    staleReason: null,
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
  };
  backupStore.storageEstimate = backupStore.sizeEstimate.scopes[0];
  backupStore.databaseEstimate = backupStore.sizeEstimate.scopes[1];
  backupStore.currentExecution = {
    state: "completed",
    summary: "Check/sync copied 1 missing assets and verified 1. 0 mismatches, 0 conflicts, and 0 restore candidates still require review.",
    targetType: "local",
    warnings: [],
    report: {
      verificationLevel: "copied_files_sha256",
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
  };
  backupStore.snapshots = {
    limitations: ["Current executable snapshot coverage is files-only."],
  };
  backupStore.snapshotItems = [backupStore.currentExecution.snapshot];
  backupStore.quarantine = {
    foundationState: "ok",
    path: "/data/quarantine",
    indexPresent: true,
    itemCount: 0,
  };
  backupStore.hasTargets = true;
  backupStore.isLoading = false;
  backupStore.isSavingTarget = false;
  backupStore.isExecuting = false;
  backupStore.isExecutionRunning = false;
  backupStore.isSizeCollectionRunning = false;
  backupStore.isValidatingTarget = false;
  backupStore.validatingTargetId = null;
  backupStore.activeValidation = null;
  backupStore.error = null;
  backupStore.targetError = null;
  backupStore.executionError = null;
  backupStore.validationError = null;
  backupStore.load = vi.fn().mockResolvedValue(undefined);
  backupStore.saveTarget = vi.fn().mockResolvedValue(undefined);
  backupStore.removeTarget = vi.fn().mockResolvedValue(undefined);
  backupStore.validateTarget = vi.fn().mockResolvedValue(undefined);
  backupStore.startExecution = vi.fn().mockResolvedValue(undefined);
  backupStore.cancelExecution = vi.fn().mockResolvedValue(undefined);
  backupStore.refreshSizeEstimate = vi.fn().mockResolvedValue(undefined);
  backupStore.selectTarget = vi.fn();
}

resetMockStore();

vi.mock("@/stores/backup", () => ({
  useBackupStore: () => backupStore,
}));

describe("BackupView", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    resetMockStore();
  });

  it("renders target management and non-blocking size visibility", async () => {
    const wrapper = mount(BackupView, {
      global: {
        stubs: {
          BackupWorkflowPanel: { template: "<div />" },
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
    expect(wrapper.text()).toContain("Source size estimate is partial.");
    expect(wrapper.text()).toContain("Check/sync copied 1 missing assets and verified 1. 0 mismatches, 0 conflicts, and 0 restore candidates still require review.");
    expect(wrapper.text()).toContain("snapshot-1");
  });

  it("shows stale source-size status after restart and allows manual refresh", async () => {
    backupStore.sizeEstimate = {
      ...backupStore.sizeEstimate,
      state: "completed",
      status: "stale",
      stale: true,
      staleReason: "restart",
      collectedAt: "2026-03-20T18:00:00+00:00",
      summary: "Source size estimate completed.",
    };
    backupStore.storageEstimate = backupStore.sizeEstimate.scopes[0];
    backupStore.databaseEstimate = backupStore.sizeEstimate.scopes[1];

    const wrapper = mount(BackupView, {
      global: {
        stubs: {
          BackupWorkflowPanel: { template: "<div />" },
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

    expect(wrapper.text()).toContain("Last calculated before doctor restart.");
    expect(wrapper.text()).toContain("A new calculation starts automatically after restart.");

    const refreshButton = wrapper.findAll("button").find((button) => button.text().includes("Recalculate"));
    await refreshButton?.trigger("click");

    expect(backupStore.refreshSizeEstimate).toHaveBeenCalledWith(true);
  });

  it("disables source-size refresh while recalculation is active", async () => {
    backupStore.isSizeCollectionRunning = true;
    backupStore.sizeEstimate = {
      ...backupStore.sizeEstimate,
      state: "running",
      status: "running",
      stale: true,
      staleReason: "restart",
      collectedAt: "2026-03-20T18:00:00+00:00",
      progress: {
        message: "Source size recalculation is running.",
      },
    };

    const wrapper = mount(BackupView, {
      global: {
        stubs: {
          BackupWorkflowPanel: { template: "<div />" },
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

    expect(wrapper.text()).toContain("Showing the previous estimate until refresh completes.");
    const refreshButton = wrapper.findAll("button").find((button) =>
      button.text().includes("Recalculation Running"),
    );
    expect(refreshButton?.attributes("disabled")).toBeDefined();
  });

  it("calls save and execution actions through the store", async () => {
    const wrapper = mount(BackupView, {
      global: {
        stubs: {
          BackupWorkflowPanel: { template: "<div />" },
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

    await wrapper.findAll('input[type="text"]')[0]?.setValue("Draft Local");
    await wrapper.find('input[placeholder="/backups/immich"]').setValue("/backup/draft");
    const form = wrapper.find("form");
    await form.trigger("submit");

    const executionButton = wrapper.findAll("button").find((button) =>
      button.text().includes("Start Check / Sync Missing"),
    );
    await executionButton?.trigger("click");

    expect(backupStore.saveTarget).toHaveBeenCalledTimes(1);
    expect(backupStore.saveTarget).toHaveBeenCalledWith(
      expect.objectContaining({
        targetType: "local",
        path: "/backup/draft",
      }),
      undefined,
    );
    expect(backupStore.startExecution).toHaveBeenCalled();
  });

  it("parses SSH connection strings and saves secret-safe agent payloads", async () => {
    const wrapper = mount(BackupView, {
      global: {
        stubs: {
          BackupWorkflowPanel: { template: "<div />" },
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

    const selects = wrapper.findAll("select");
    await selects[0]?.setValue("ssh");
    await nextTick();
    await wrapper.findAll('input[type="text"]')[0]?.setValue("Draft SSH");
    await wrapper.find('input[placeholder="root@192.168.2.2"]').setValue("root@192.168.2.2");
    await wrapper.find('input[placeholder="/srv/backup"]').setValue("/srv/backup");
    await nextTick();

    expect(wrapper.text()).toContain("Parsed username");
    expect(wrapper.text()).toContain("root");
    expect(wrapper.text()).toContain("192.168.2.2");

    await wrapper.find("form").trigger("submit");

    expect(backupStore.saveTarget).toHaveBeenCalledWith(
      expect.objectContaining({
        targetType: "ssh",
        connectionString: "root@192.168.2.2",
        remotePath: "/srv/backup",
        authMode: "agent",
        knownHostMode: "strict",
      }),
      undefined,
    );
    const lastPayload = backupStore.saveTarget.mock.calls[backupStore.saveTarget.mock.calls.length - 1]?.[0];
    expect(lastPayload).not.toHaveProperty("privateKeySecret");
  });

  it("parses SSH connection strings with ports", async () => {
    const wrapper = mount(BackupView, {
      global: {
        stubs: {
          BackupWorkflowPanel: { template: "<div />" },
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

    const selects = wrapper.findAll("select");
    await selects[0]?.setValue("ssh");
    await nextTick();
    await wrapper.findAll('input[type="text"]')[0]?.setValue("Draft SSH Port");
    await wrapper.find('input[placeholder="root@192.168.2.2"]').setValue("root@192.168.2.2:2222");
    await wrapper.find('input[placeholder="/srv/backup"]').setValue("/srv/backup");
    expect(wrapper.text()).toContain("Parsed port");
    expect(wrapper.text()).toContain("2222");

    await wrapper.find("form").trigger("submit");

    expect(backupStore.saveTarget).toHaveBeenCalledWith(
      expect.objectContaining({
        targetType: "ssh",
        connectionString: "root@192.168.2.2:2222",
        port: 2222,
      }),
      undefined,
    );
  });

  it("shows SMB pre-mounted targets as executable", async () => {
    backupStore.targetsOverview.items = [
      {
        targetId: "target-smb",
        targetName: "Mounted SMB",
        targetType: "smb",
        enabled: true,
        transport: {
          host: "nas.local",
          share: "immich",
          remotePath: "/backup",
          mountStrategy: "pre_mounted_path",
          mountedPath: "/mnt/immich-backup",
        },
        verificationStatus: "ready",
        lastTestResult: null,
        lastSuccessfulBackup: null,
        retentionPolicy: { mode: "keep_all", maxVersions: null, pruneAutomatically: false },
        restoreReadiness: "partial",
        sourceScope: "files_only",
        schedulingCompatible: true,
        warnings: [],
        createdAt: "2026-03-18T20:00:00+00:00",
        updatedAt: "2026-03-18T20:00:00+00:00",
      },
    ];
    backupStore.targets = backupStore.targetsOverview.items;
    backupStore.selectedTargetId = "target-smb";
    backupStore.selectedTarget = backupStore.targets[0];

    const wrapper = mount(BackupView, {
      global: {
        stubs: {
          BackupWorkflowPanel: { template: "<div />" },
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

    expect(wrapper.text()).toContain("Mounted path check / sync is supported");
    expect(wrapper.text()).not.toContain("SMB system-mount execution is not implemented");
  });

  it("shows only mounted-path fields for SMB pre-mounted mode", async () => {
    const wrapper = mount(BackupView, {
      global: {
        stubs: {
          BackupWorkflowPanel: { template: "<div />" },
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

    const selects = wrapper.findAll("select");
    await selects[0]?.setValue("smb");
    await nextTick();
    const accessModeSelect = wrapper.findAll("select").find((select) =>
      select.text().includes("Mounted local path"),
    );
    await accessModeSelect?.setValue("pre_mounted_path");
    await nextTick();

    expect(wrapper.text()).toContain("Mounted local path");
    expect(wrapper.text()).toContain("already mounted outside doctor");
    expect(wrapper.text()).not.toContain("Server / Host");
    expect(wrapper.text()).not.toContain("Share name");
    expect(wrapper.text()).not.toContain("Subfolder in share");
    expect(wrapper.text()).not.toContain("Password secret");

    await wrapper.findAll('input[type="text"]')[0]?.setValue("Mounted SMB");
    await wrapper.find('input[placeholder="/mnt/immich-backup"]').setValue("/mnt/backup");
    await wrapper.find("form").trigger("submit");

    expect(backupStore.saveTarget).toHaveBeenCalledWith(
      expect.objectContaining({
        targetType: "smb",
        mountStrategy: "pre_mounted_path",
        mountedPath: "/mnt/backup",
      }),
      undefined,
    );
    const lastPayload = backupStore.saveTarget.mock.calls[backupStore.saveTarget.mock.calls.length - 1]?.[0];
    expect(lastPayload.host).toBeUndefined();
    expect(lastPayload.share).toBeUndefined();
    expect(lastPayload.remotePath).toBeUndefined();
  });

  it("shows share and optional subfolder semantics for SMB system-mount mode", async () => {
    const wrapper = mount(BackupView, {
      global: {
        stubs: {
          BackupWorkflowPanel: { template: "<div />" },
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

    const selects = wrapper.findAll("select");
    await selects[0]?.setValue("smb");
    await nextTick();

    expect(wrapper.text()).toContain("Server / Host");
    expect(wrapper.text()).toContain("Share name");
    expect(wrapper.text()).toContain("Subfolder in share");
    expect(wrapper.text()).toContain("not executable in the current safe subset");
    expect(wrapper.text()).not.toContain("Password secret label");
  });

  it("shows active validation state on the target card without getting stuck", async () => {
    backupStore.isValidatingTarget = true;
    backupStore.validatingTargetId = "target-1";
    backupStore.activeValidation = {
      generatedAt: "2026-03-21T14:00:00+00:00",
      jobId: "validation-1",
      targetId: "target-1",
      targetType: "ssh",
      state: "running",
      verificationStatus: "running",
      summary: "SSH validation is running.",
      checks: [],
      warnings: [],
    };

    const wrapper = mount(BackupView, {
      global: {
        stubs: {
          BackupWorkflowPanel: { template: "<div />" },
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

    expect(wrapper.text()).toContain("Validation running");
    expect(wrapper.text()).toContain("SSH validation is running.");
    expect(wrapper.text()).toContain("Validating");
  });

  it("shows actionable SSH validation failure details from the backend result", async () => {
    backupStore.targets[0].targetType = "ssh";
    backupStore.targets[0].transport = { host: "backup.example", username: "backup", remotePath: "/srv/backup", authMode: "agent" };
    backupStore.targets[0].verificationStatus = "failed";
    backupStore.targets[0].lastTestResult = {
      checkedAt: "2026-03-21T14:00:00+00:00",
      status: "failed",
      summary: "Target validation failed: SSH agent auth is selected, but SSH_AUTH_SOCK is not available in the doctor runtime.",
      warnings: [],
      details: {
        checks: [
          {
            name: "remote_agent_socket",
            status: "fail",
            message: "SSH agent auth is selected, but SSH_AUTH_SOCK is not available in the doctor runtime.",
          },
        ],
      },
    };
    backupStore.targetsOverview.items = backupStore.targets;
    backupStore.selectedTarget = backupStore.targets[0];

    const wrapper = mount(BackupView, {
      global: {
        stubs: {
          BackupWorkflowPanel: { template: "<div />" },
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

    expect(wrapper.text()).toContain("Validation failed");
    expect(wrapper.text()).toContain("SSH_AUTH_SOCK is not available in the doctor runtime");
    expect(wrapper.text()).not.toContain("Validation running");
  });

  it("keeps SSH shorthand primary and separate fields secondary", async () => {
    const wrapper = mount(BackupView, {
      global: {
        stubs: {
          BackupWorkflowPanel: { template: "<div />" },
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

    const selects = wrapper.findAll("select");
    await selects[0]?.setValue("ssh");
    await nextTick();

    expect(wrapper.text()).toContain("SSH connection");
    expect(wrapper.text()).toContain("username@host or username@host:port");
    expect(wrapper.text()).not.toContain("Server / Host");

    const toggleButtons = wrapper.findAll("button").filter((button) =>
      button.text().includes("Enter server, user, and port separately"),
    );
    await toggleButtons[0]?.trigger("click");
    await nextTick();

    expect(wrapper.text()).toContain("Server / Host");
    expect(wrapper.text()).toContain("Port");
  });

  it("uses rsync over SSH wording", async () => {
    const wrapper = mount(BackupView, {
      global: {
        stubs: {
          BackupWorkflowPanel: { template: "<div />" },
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

    const selects = wrapper.findAll("select");
    await selects[0]?.setValue("rsync");
    await nextTick();

    expect(wrapper.text()).toContain("Rsync over SSH");
    expect(wrapper.text()).toContain("This is SSH-based transport, not a mounted filesystem.");
  });
});
