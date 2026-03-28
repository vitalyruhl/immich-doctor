import { mount } from "@vue/test-utils";
import { nextTick } from "vue";
import { vi } from "vitest";
import ConsistencyView from "./ConsistencyView.vue";

const findings = [
  {
    finding_id: "finding-2",
    asset_id: "asset-2",
    asset_type: "image",
    status: "missing_on_disk",
    logical_path: "/library/assets/asset-2.jpg",
    resolved_physical_path: "/data/library/assets/asset-2.jpg",
    owner_id: "user-1",
    created_at: "2026-03-20T10:00:00+00:00",
    updated_at: "2026-03-21T10:00:00+00:00",
    scan_timestamp: "2026-03-28T08:00:00+00:00",
    repair_readiness: "ready",
    repair_blockers: [],
    message: "Missing file on disk.",
  },
  {
    finding_id: "finding-1",
    asset_id: "asset-1",
    asset_type: "image",
    status: "missing_on_disk",
    logical_path: "/library/assets/asset-1.jpg",
    resolved_physical_path: "/data/library/assets/asset-1.jpg",
    owner_id: "user-1",
    created_at: "2026-03-19T10:00:00+00:00",
    updated_at: "2026-03-21T09:30:00+00:00",
    scan_timestamp: "2026-03-28T08:00:00+00:00",
    repair_readiness: "ready",
    repair_blockers: [],
    message: "Missing file on disk.",
  },
  {
    finding_id: "finding-3",
    asset_id: "asset-3",
    asset_type: "image",
    status: "unsupported",
    logical_path: "/library/assets/asset-3.jpg",
    resolved_physical_path: "/data/library/assets/asset-3.jpg",
    owner_id: null,
    created_at: "2026-03-18T10:00:00+00:00",
    updated_at: "2026-03-22T10:00:00+00:00",
    scan_timestamp: "2026-03-28T08:00:00+00:00",
    repair_readiness: "blocked",
    repair_blockers: ["unsupported scope"],
    message: "Unsupported reference type.",
  },
];

const restorePoints = [
  {
    restore_point_id: "restore-point-1",
    repair_run_id: "repair-run-1",
    asset_id: "asset-2",
    created_at: "2026-03-28T08:15:00+00:00",
    status: "available",
    record_count: 2,
    logical_path: "/library/assets/asset-2.jpg",
    records: [
      { table: "asset", row_count: 1 },
      { table: "files", row_count: 1 },
    ],
  },
  {
    restore_point_id: "restore-point-2",
    repair_run_id: "repair-run-2",
    asset_id: "asset-3",
    created_at: "2026-03-28T08:16:00+00:00",
    status: "available",
    record_count: 1,
    logical_path: "/library/assets/asset-3.jpg",
    records: [{ table: "asset", row_count: 1 }],
  },
];

function buildPreviewResponse(selectedFindings: typeof findings, repairRunId: string, mode: string) {
  return {
    domain: "consistency",
    action: "preview",
    status: "PASS",
    summary: `${mode} preview completed`,
    generated_at: "2026-03-28T08:30:00+00:00",
    checks: [],
    selected_findings: selectedFindings,
    repair_run_id: repairRunId,
    metadata: {},
    recommendations: [],
  };
}

function buildApplyResponse(repairRunId: string) {
  return {
    domain: "consistency",
    action: "apply",
    status: "PASS",
    summary: "Apply completed",
    generated_at: "2026-03-28T08:31:00+00:00",
    checks: [],
    repair_run_id: repairRunId,
    items: [],
    metadata: {},
    recommendations: [],
  };
}

function buildRestoreResponse() {
  return {
    domain: "consistency",
    action: "restore",
    status: "PASS",
    summary: "Restore completed",
    generated_at: "2026-03-28T08:32:00+00:00",
    checks: [],
    repair_run_id: "repair-run-restore",
    items: [],
    metadata: {},
  };
}

function buildDeleteResponse() {
  return {
    domain: "consistency",
    action: "delete_restore_points",
    status: "PASS",
    summary: "Delete completed",
    generated_at: "2026-03-28T08:33:00+00:00",
    checks: [],
    items: [],
    metadata: {},
  };
}

function createStore() {
  return {
    findings,
    restorePoints,
    scanResult: {
      domain: "consistency",
      action: "scan",
      status: "PASS",
      summary: "3 findings loaded",
      generated_at: "2026-03-28T08:00:00+00:00",
      checks: [],
      findings,
      metadata: {
        supportedScope: {
          scanTables: ["assets"],
          scanPathField: "file_path",
          repairRestoreTables: ["repair_runs", "restore_points"],
          blockingIssues: ["permission denied"],
        },
      },
      recommendations: [],
    },
    restorePointsResult: {
      domain: "consistency",
      action: "restore-points",
      status: "PASS",
      summary: "2 restore points available",
      generated_at: "2026-03-28T08:00:00+00:00",
      checks: [],
      items: restorePoints,
      metadata: {},
    },
    isLoading: false,
    isScanning: false,
    isLoadingRestorePoints: false,
    isPreviewing: false,
    isApplying: false,
    isRestoring: false,
    isDeletingRestorePoints: false,
    scanError: null,
    restorePointsError: null,
    previewError: null,
    applyError: null,
    restoreError: null,
    deleteError: null,
    load: vi.fn().mockResolvedValue(undefined),
    scan: vi.fn().mockResolvedValue(undefined),
    loadRestorePoints: vi.fn().mockResolvedValue(undefined),
    preview: vi.fn(async (payload: { asset_ids: string[]; select_all: boolean }) => {
      if (payload.select_all) {
        return buildPreviewResponse(findings, "repair-run-all", "all");
      }
      const selectedFindings = findings.filter((finding) => payload.asset_ids.includes(finding.asset_id));
      if (payload.asset_ids.length === 1) {
        return buildPreviewResponse(selectedFindings, "repair-run-single", "single");
      }
      return buildPreviewResponse(selectedFindings, "repair-run-selected", "selected");
    }),
    apply: vi.fn(async () => buildApplyResponse("repair-run-all")),
    restore: vi.fn(async () => buildRestoreResponse()),
    deleteRestorePoints: vi.fn(async () => buildDeleteResponse()),
  };
}

const store = createStore();

vi.mock("@/stores/consistency", () => ({
  useConsistencyStore: () => store,
}));

function mountView() {
  return mount(ConsistencyView, {
    global: {
      stubs: {
        PageHeader: { template: "<div class='page-header-stub' />" },
        DisclaimerBanner: { template: "<div class='disclaimer-stub' />" },
        RiskNotice: { template: "<div class='risk-notice-stub' />", props: ["title", "message"] },
        LoadingState: { template: "<div class='loading-stub' />" },
        ErrorState: { template: "<div class='error-stub' />" },
        StatusTag: { template: "<span class='status-tag-stub'>{{ status }}</span>", props: ["status"] },
        ConfirmOperationDialog: {
          props: ["visible", "confirmLabel", "cancelLabel"],
          emits: ["confirm", "cancel"],
          template: `
            <div v-if="visible" class="confirm-dialog">
              <button class="runtime-action" type="button" @click="$emit('cancel')">
                {{ cancelLabel }}
              </button>
              <button
                class="runtime-action runtime-action--danger"
                type="button"
                @click="$emit('confirm')"
              >
                {{ confirmLabel }}
              </button>
            </div>
          `,
        },
      },
    },
  });
}

async function settle() {
  await Promise.resolve();
  await nextTick();
  await Promise.resolve();
  await nextTick();
}

describe("ConsistencyView", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders preview flows and requires both disclaimer checks before apply", async () => {
    const wrapper = mountView();
    await settle();

    const findingsTable = wrapper.findAll("table.consistency-table")[0];
    await findingsTable.findAll("tbody tr")[0].get("button").trigger("click");
    await settle();

    expect(store.preview).toHaveBeenCalledWith({
      asset_ids: ["asset-2"],
      select_all: false,
      limit: 1,
      offset: 0,
    });

    const previewAllButton = wrapper.findAll("button").find((button) => button.text().includes("Preview all"));
    expect(previewAllButton).toBeTruthy();
    await previewAllButton!.trigger("click");
    await settle();

    expect(store.preview).toHaveBeenLastCalledWith({
      asset_ids: [],
      select_all: true,
    });

    const applyButton = wrapper.findAll("button").find((button) => button.text().includes("Apply all removals"));
    expect(applyButton?.element).toBeTruthy();
    expect((applyButton!.element as HTMLButtonElement).disabled).toBe(true);

    const disclaimerChecks = wrapper.findAll(".consistency-disclaimer__check input");
    await disclaimerChecks[0].setValue(true);
    await disclaimerChecks[1].setValue(true);
    await settle();

    expect((applyButton!.element as HTMLButtonElement).disabled).toBe(false);
    await applyButton!.trigger("click");
    await settle();

    expect(store.apply).toHaveBeenCalledWith("repair-run-all");
    expect(wrapper.text()).toContain("Latest apply result");
  });

  it("filters, sorts, and previews selected findings", async () => {
    const wrapper = mountView();
    await settle();

    const searchInput = wrapper.get('input[type="search"]');
    await searchInput.setValue("asset-1");
    await settle();

    const findingsTable = wrapper.findAll("table.consistency-table")[0];
    expect(findingsTable.findAll("tbody tr")).toHaveLength(1);
    expect(findingsTable.text()).toContain("asset-1");

    await searchInput.setValue("");
    await settle();

    const assetSortButton = wrapper.findAll("button").find((button) => button.text().includes("Asset id"));
    expect(assetSortButton).toBeTruthy();
    await assetSortButton!.trigger("click");
    await settle();

    const sortedRows = wrapper.findAll("table.consistency-table")[0].findAll("tbody tr");
    expect(sortedRows[0].text()).toContain("asset-1");

    await wrapper.get('input[aria-label="Select finding finding-2"]').setValue(true);
    await settle();

    const previewSelectedButton = wrapper.findAll("button").find((button) =>
      button.text().includes("Preview selected"),
    );
    expect(previewSelectedButton).toBeTruthy();
    await previewSelectedButton!.trigger("click");
    await settle();

    expect(store.preview).toHaveBeenLastCalledWith({
      asset_ids: ["asset-2"],
      select_all: false,
      limit: 1,
      offset: 0,
    });
  });

  it("restores selected and all restore points", async () => {
    const wrapper = mountView();
    await settle();

    await wrapper.get('input[aria-label="Select restore point restore-point-2"]').setValue(true);
    await settle();

    const restoreSelectedButton = wrapper.findAll("button").find((button) =>
      button.text().includes("Restore selected"),
    );
    await restoreSelectedButton!.trigger("click");
    await settle();

    expect(store.restore).toHaveBeenCalledWith({
      restore_point_ids: ["restore-point-2"],
      select_all: false,
    });

    const restoreAllButton = wrapper.findAll("button").find((button) => button.text().includes("Restore all"));
    await restoreAllButton!.trigger("click");
    await settle();

    expect(store.restore).toHaveBeenLastCalledWith({
      restore_point_ids: ["restore-point-1", "restore-point-2"],
      select_all: true,
    });
  });

  it("confirms delete actions separately for single, selected, and all restore points", async () => {
    const wrapper = mountView();
    await settle();

    const restorePointsTable = wrapper.findAll("table.consistency-table")[1];
    await restorePointsTable.findAll("tbody tr")[0].findAll("button")[1].trigger("click");
    await settle();

    expect(wrapper.text()).toContain("Delete restore points");
    await wrapper.find(".confirm-dialog button.runtime-action--danger").trigger("click");
    await settle();

    expect(store.deleteRestorePoints).toHaveBeenCalledWith({
      restore_point_ids: ["restore-point-1"],
      select_all: false,
    });

    await wrapper.get('input[aria-label="Select restore point restore-point-2"]').setValue(true);
    await settle();

    const deleteSelectedButton = wrapper.findAll("button").find((button) =>
      button.text().includes("Delete selected"),
    );
    await deleteSelectedButton!.trigger("click");
    await settle();

    await wrapper.find(".confirm-dialog button.runtime-action--danger").trigger("click");
    await settle();

    expect(store.deleteRestorePoints).toHaveBeenLastCalledWith({
      restore_point_ids: ["restore-point-2"],
      select_all: false,
    });

    const deleteAllButton = wrapper.findAll("button").find((button) => button.text().includes("Delete all"));
    await deleteAllButton!.trigger("click");
    await settle();

    await wrapper.find(".confirm-dialog button.runtime-action--danger").trigger("click");
    await settle();

    expect(store.deleteRestorePoints).toHaveBeenLastCalledWith({
      restore_point_ids: ["restore-point-1", "restore-point-2"],
      select_all: true,
    });
  });
});
