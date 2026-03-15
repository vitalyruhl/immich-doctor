import { mount } from "@vue/test-utils";
import { nextTick } from "vue";
import BackupView from "./BackupView.vue";

const backupStore = {
  snapshots: {
    limitations: ["Current executable snapshot creation is files-only."],
  },
  quarantine: {
    foundationState: "ok",
    path: "/data/quarantine",
    indexPresent: true,
    itemCount: 0,
    workflowImplemented: false,
    message: "Quarantine indexing exists, but move/restore workflow is not implemented yet.",
  },
  snapshotItems: [
    {
      snapshotId: "snapshot-1",
      createdAt: "2026-03-15T10:00:00+00:00",
      kind: "pre_repair",
      coverage: "files_only",
      repairRunId: "repair-run-1",
      verified: true,
      hasDbArtifact: false,
      manifestPath: "/data/manifests/backup/snapshots/snapshot-1.json",
      basicValidity: "valid",
      validityMessage: "Snapshot metadata is structurally valid.",
    },
  ],
  isLoading: false,
  error: null,
  load: vi.fn().mockResolvedValue(undefined),
};

vi.mock("@/stores/backup", () => ({
  useBackupStore: () => backupStore,
}));

describe("BackupView", () => {
  it("renders snapshot and quarantine foundation visibility", async () => {
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

    expect(wrapper.text()).toContain("snapshot-1");
    expect(wrapper.text()).toContain("files_only");
    expect(wrapper.text()).toContain("/data/quarantine");
    expect(wrapper.text()).toContain("Visibility only");
  });
});
