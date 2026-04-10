import { mount } from "@vue/test-utils";
import { nextTick } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";
import CatalogRemediationPanel from "./CatalogRemediationPanel.vue";

function createStore(): any {
  return {
    remediationScanResult: {
      summary: "Catalog remediation findings loaded.",
    },
    remediationError: null,
    remediationPreviewError: null,
    remediationApplyError: null,
    brokenDbOriginals: [
      {
        finding_id: "broken-1",
        asset_id: "asset-1",
        asset_name: "missing.jpg",
        asset_type: "image",
        expected_database_path: "/usr/src/app/upload/upload/user-a/missing.jpg",
        expected_relative_path: "user-a/missing.jpg",
        classification: "missing_confirmed",
        action_eligible: true,
        action_reason: "Eligible",
        found_absolute_path: null,
        message: "Missing confirmed.",
      },
      {
        finding_id: "broken-2",
        asset_id: "asset-2",
        asset_name: "relocated.jpg",
        asset_type: "image",
        expected_database_path: "/usr/src/app/upload/upload/user-a/relocated.jpg",
        expected_relative_path: "user-a/relocated.jpg",
        classification: "found_elsewhere",
        action_eligible: false,
        action_reason: "Inspect only",
        found_absolute_path: "/upload/user-b/relocated.jpg",
        message: "Found elsewhere.",
      },
    ],
    fuseHiddenOrphans: [
      {
        finding_id: "fuse-1",
        root_slug: "uploads",
        relative_path: "user-a/.fuse_hidden0001",
        absolute_path: "/upload/user-a/.fuse_hidden0001",
        file_name: ".fuse_hidden0001",
        size_bytes: 123,
        classification: "blocked_in_use",
        action_eligible: false,
        action_reason: "Blocked",
        message: "Still in use.",
      },
      {
        finding_id: "fuse-2",
        root_slug: "uploads",
        relative_path: "user-b/.fuse_hidden0002",
        absolute_path: "/upload/user-b/.fuse_hidden0002",
        file_name: ".fuse_hidden0002",
        size_bytes: 456,
        classification: "deletable_orphan",
        action_eligible: true,
        action_reason: "Eligible",
        message: "Safe to delete.",
      },
    ],
    isLoadingRemediation: false,
    isPreviewing: false,
    isApplying: false,
    loadRemediation: vi.fn().mockResolvedValue(undefined),
    previewBrokenDbOriginals: vi.fn().mockResolvedValue({
      summary: "Preview planned 1 remediation item.",
      repair_run_id: "broken-run",
    }),
    previewFuseHidden: vi.fn().mockResolvedValue({
      summary: "Preview planned 1 remediation item.",
      repair_run_id: "fuse-run",
    }),
    applyRemediation: vi.fn().mockResolvedValue({
      summary: "Apply processed 1 selected remediation items.",
    }),
  };
}

let store = createStore();

vi.mock("@/stores/consistency", () => ({
  useConsistencyStore: () => store,
}));

describe("CatalogRemediationPanel", () => {
  beforeEach(() => {
    store = createStore();
    vi.clearAllMocks();
  });

  it("previews only eligible broken DB originals and keeps found_elsewhere inspect-only", async () => {
    const wrapper = mount(CatalogRemediationPanel, {
      global: {
        stubs: {
          StatusTag: { template: "<span>{{ status }}</span>", props: ["status"] },
        },
      },
    });
    await nextTick();

    const brokenCheckboxes = wrapper.findAll("tbody input[type='checkbox']");
    expect((brokenCheckboxes[1].element as HTMLInputElement).disabled).toBe(true);

    await brokenCheckboxes[0].setValue(true);
    await nextTick();

    const previewButton = wrapper
      .findAll("button")
      .find((button) => button.text().includes("Preview selected (1)"));
    await previewButton!.trigger("click");
    await nextTick();

    expect(store.previewBrokenDbOriginals).toHaveBeenCalledWith({
      asset_ids: ["asset-1"],
      select_all: false,
    });
  });

  it("requires both confirmation checkboxes before apply for fuse-hidden deletion", async () => {
    const wrapper = mount(CatalogRemediationPanel, {
      global: {
        stubs: {
          StatusTag: { template: "<span>{{ status }}</span>", props: ["status"] },
        },
      },
    });
    await nextTick();

    const previewAllFuseButton = wrapper
      .findAll("button")
      .filter((button) => button.text().includes("Preview all eligible (1)"))[1];
    await previewAllFuseButton!.trigger("click");
    await nextTick();

    const applyButton = wrapper
      .findAll("button")
      .find((button) => button.text().includes("Apply previewed orphan deletion"));
    expect((applyButton!.element as HTMLButtonElement).disabled).toBe(true);

    const confirmations = wrapper.findAll(".catalog-remediation-confirm input");
    await confirmations[2].setValue(true);
    await confirmations[3].setValue(true);
    await nextTick();

    expect((applyButton!.element as HTMLButtonElement).disabled).toBe(false);
    await applyButton!.trigger("click");
    await nextTick();

    expect(store.applyRemediation).toHaveBeenCalledWith("fuse-run");
  });
});
