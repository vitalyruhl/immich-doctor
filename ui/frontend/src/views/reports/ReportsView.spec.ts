import { mount } from "@vue/test-utils";
import { nextTick } from "vue";
import ReportsView from "./ReportsView.vue";

const repairStore = {
  runs: { items: [] },
  runItems: [
    {
      repairRunId: "repair-run-1",
      status: "partial",
      preRepairSnapshotId: "snapshot-1",
    },
  ],
  selectedRun: {
    repairRun: {
      repairRunId: "repair-run-1",
      startedAt: "2026-03-15T10:00:00+00:00",
      endedAt: "2026-03-15T10:01:00+00:00",
      status: "partial",
      preRepairSnapshotId: "snapshot-1",
      journalEntryCount: 1,
      undoAvailable: true,
      planTokenId: "token-1",
    },
    journalEntries: [
      {
        entryId: "entry-1",
        operationType: "chmod",
        status: "applied",
        assetId: "asset-1",
        originalPath: "/library/asset.jpg",
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
  quarantine: {
    foundationState: "ok",
    path: "/data/quarantine",
    pathSummary: "Quarantine path is ready.",
    indexPresent: true,
    itemCount: 0,
  },
  isLoading: false,
  error: null,
  load: vi.fn().mockResolvedValue(undefined),
  selectRun: vi.fn().mockResolvedValue(undefined),
};

vi.mock("@/stores/repair", () => ({
  useRepairStore: () => repairStore,
}));

describe("ReportsView", () => {
  it("renders repair history and journal visibility", async () => {
    const wrapper = mount(ReportsView, {
      global: {
        stubs: {
          PageHeader: { template: "<div />" },
          RiskNotice: { template: "<div />", props: ["title", "message"] },
          LoadingState: { template: "<div />" },
          ErrorState: { template: "<div />" },
          EmptyState: { template: "<div />" },
          StatusTag: { template: "<span />", props: ["status"] },
        },
      },
    });

    await nextTick();
    await nextTick();

    expect(wrapper.text()).toContain("repair-run-1");
    expect(wrapper.text()).toContain("snapshot-1");
    expect(wrapper.text()).toContain("token-1");
    expect(wrapper.text()).toContain("chmod_restore");
    expect(wrapper.text()).toContain("old=0600 new=0644");
  });
});
