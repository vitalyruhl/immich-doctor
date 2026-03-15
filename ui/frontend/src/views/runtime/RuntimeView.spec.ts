import { mount } from "@vue/test-utils";
import { nextTick } from "vue";
import RuntimeView from "./RuntimeView.vue";

const runtimeStore = {
  integrity: {
    summary_items: [{ status: "FILE_PERMISSION_DENIED", count: 1 }],
  },
  metadataFailures: {
    metadata_summary: [{ root_cause: "CAUSED_BY_PERMISSION_ERROR", count: 1 }],
  },
  readiness: {
    applyAllowed: false,
    blockingReasons: ["Backup target path is not writable."],
    preconditions: [
      {
        id: "backup_target_path_writable",
        label: "backup target path writable",
        status: "error",
        blocking: true,
        summary: "Backup target path is not writable.",
        details: {},
      },
    ],
    snapshotPlan: {
      kind: "pre_repair",
      coverage: "files_only",
      willCreate: true,
      note: "Integrated runtime apply creates a files-only pre-repair snapshot first.",
    },
    undoVisibility: {
      journalUndoAvailable: true,
      automatedUndo: false,
      note: "Undo is visible through journal data, but not automated yet.",
    },
    restoreImplemented: false,
    limitations: [
      "Snapshots are currently files-only.",
      "Full restore orchestration is not implemented yet.",
    ],
  },
  diagnostics: [
    {
      diagnostic_id: "metadata_failure:asset-1",
      asset_id: "asset-1",
      root_cause: "CAUSED_BY_PERMISSION_ERROR",
      failure_level: "secondary",
      confidence: "high",
      suggested_action: "fix_permissions",
      source_path: "/library/asset.jpg",
      source_file_status: "FILE_PERMISSION_DENIED",
      source_message: "File exists but is not readable by the current process.",
      available_actions: ["fix_permissions", "report_only"],
      file_findings: [
        {
          finding_id: "file_integrity:asset-1",
          file_role: "source",
          status: "FILE_PERMISSION_DENIED",
          path: "/library/asset.jpg",
        },
      ],
    },
  ],
  repairResult: {
    summary: "Runtime repair planned 1 action.",
    status: "WARN",
    metadata: {
      dry_run: true,
      repair_run_id: "repair-run-1",
      pre_repair_snapshot_id: "snapshot-1",
    },
    repair_actions: [
      {
        diagnostic_id: "metadata_failure:asset-1",
        action: "fix_permissions",
        status: "planned",
        reason: "Planned fix_permissions.",
        path: "/library/asset.jpg",
      },
    ],
  },
  repairRunDetail: {
    repairRun: {
      repairRunId: "repair-run-1",
      status: "partial",
      startedAt: "2026-03-15T10:00:00+00:00",
      endedAt: null,
      preRepairSnapshotId: "snapshot-1",
      journalEntryCount: 1,
      undoAvailable: true,
    },
    journalEntries: [
      {
        entryId: "entry-1",
        operationType: "chmod",
        status: "applied",
        originalPath: "/library/asset.jpg",
        assetId: "asset-1",
        undoType: "chmod_restore",
        undoPayload: { old_mode: "0600", new_mode: "0644" },
        errorDetails: null,
      },
    ],
    limitations: [
      "Undo visibility exists through persisted journal data.",
      "Full restore orchestration is not implemented yet.",
    ],
  },
  isLoading: false,
  isPlanning: false,
  error: null,
  planError: null,
  load: vi.fn().mockResolvedValue(undefined),
  planRepair: vi.fn().mockResolvedValue(undefined),
};

vi.mock("@/stores/runtime", () => ({
  useRuntimeStore: () => runtimeStore,
}));

describe("RuntimeView", () => {
  it("renders safety context and blocks apply when readiness fails", async () => {
    const wrapper = mount(RuntimeView, {
      global: {
        stubs: {
          PageHeader: { template: "<div><slot /></div>" },
          DisclaimerBanner: { template: "<div />" },
          RiskNotice: { template: "<div><slot /></div>", props: ["title", "message"] },
          LoadingState: { template: "<div />" },
          ErrorState: { template: "<div />" },
          EmptyState: { template: "<div />" },
          StatusTag: { template: "<span><slot /></span>", props: ["status"] },
          ConfirmOperationDialog: { template: "<div />", props: ["visible"] },
        },
      },
    });

    await nextTick();
    await nextTick();

    expect(wrapper.text()).toContain("Apply readiness");
    expect(wrapper.text()).toContain("Backup target path is not writable.");
    expect(wrapper.text()).toContain("snapshot-1");
    expect(wrapper.text()).toContain("chmod_restore");
    const applyButton = wrapper
      .findAll("button")
      .find((button) => button.text() === "Apply fix_permissions");
    expect(applyButton?.attributes("disabled")).toBeDefined();
  });
});
