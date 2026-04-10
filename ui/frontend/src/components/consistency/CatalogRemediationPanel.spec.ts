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
        expected_absolute_path: "/upload/user-a/missing.jpg",
        classification: "missing_confirmed",
        checksum_value: null,
        checksum_algorithm: null,
        checksum_match: null,
        eligible_actions: ["broken_db_cleanup"],
        action_eligible: true,
        action_reason: "Eligible for cleanup",
        found_absolute_path: null,
        message: "Missing confirmed.",
      },
      {
        finding_id: "broken-2",
        asset_id: "asset-2",
        asset_name: "path-fix.jpg",
        asset_type: "image",
        expected_database_path:
          "/usr/src/app/upload/upload/user-a/path-fix.jpg",
        expected_relative_path: "user-a/path-fix.jpg",
        expected_absolute_path: "/upload/user-a/path-fix.jpg",
        classification: "found_with_hash_match",
        checksum_value: "abc",
        checksum_algorithm: "sha256",
        checksum_match: true,
        eligible_actions: ["broken_db_path_fix"],
        action_eligible: true,
        action_reason: "Eligible for path fix",
        found_absolute_path: "/upload/user-a/path-fix.jpg",
        message: "Hash match.",
      },
      {
        finding_id: "broken-3",
        asset_id: "asset-3",
        asset_name: "relocated.jpg",
        asset_type: "image",
        expected_database_path:
          "/usr/src/app/upload/upload/user-a/relocated.jpg",
        expected_relative_path: "user-a/relocated.jpg",
        expected_absolute_path: "/upload/user-a/relocated.jpg",
        classification: "found_elsewhere",
        checksum_value: null,
        checksum_algorithm: null,
        checksum_match: null,
        eligible_actions: [],
        action_eligible: false,
        action_reason: "Inspect only",
        found_absolute_path: "/upload/user-b/relocated.jpg",
        message: "Found elsewhere.",
      },
    ],
    zeroByteFindings: [
      {
        finding_id: "zero-1",
        root_slug: "uploads",
        relative_path: "user-a/orphan-zero.jpg",
        absolute_path: "/upload/user-a/orphan-zero.jpg",
        file_name: "orphan-zero.jpg",
        size_bytes: 0,
        classification: "zero_byte_upload_orphan",
        asset_id: null,
        asset_name: null,
        original_relative_path: null,
        eligible_actions: ["zero_byte_delete"],
        action_eligible: true,
        action_reason: "Delete allowed",
        message: "Orphan zero-byte upload.",
      },
      {
        finding_id: "zero-2",
        root_slug: "uploads",
        relative_path: "user-a/critical-zero.jpg",
        absolute_path: "/upload/user-a/critical-zero.jpg",
        file_name: "critical-zero.jpg",
        size_bytes: 0,
        classification: "zero_byte_upload_critical",
        asset_id: "asset-4",
        asset_name: "critical-zero.jpg",
        original_relative_path: "user-a/critical-zero.jpg",
        eligible_actions: [],
        action_eligible: false,
        action_reason: "Blocked",
        message: "Critical original.",
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
        eligible_actions: [],
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
        eligible_actions: ["fuse_hidden_delete"],
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
      summary: "Preview planned 1 cleanup item.",
      repair_run_id: "broken-cleanup-run",
    }),
    previewBrokenDbPathFix: vi.fn().mockResolvedValue({
      summary: "Preview planned 1 path-fix item.",
      repair_run_id: "broken-fix-run",
    }),
    previewZeroByte: vi.fn().mockResolvedValue({
      summary: "Preview planned 1 zero-byte item.",
      repair_run_id: "zero-run",
    }),
    previewFuseHidden: vi.fn().mockResolvedValue({
      summary: "Preview planned 1 fuse-hidden item.",
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

  it("separates cleanup and path-fix preview selections for broken DB rows", async () => {
    const wrapper = mount(CatalogRemediationPanel, {
      global: {
        stubs: {
          StatusTag: {
            template: "<span>{{ status }}</span>",
            props: ["status"],
          },
        },
      },
    });
    await nextTick();

    const checkboxes = wrapper.findAll("tbody input[type='checkbox']");
    await checkboxes[0].setValue(true);
    await checkboxes[1].setValue(true);
    await nextTick();

    await wrapper.findAll("button")[1].trigger("click");
    await nextTick();
    expect(store.previewBrokenDbOriginals).toHaveBeenCalledWith({
      asset_ids: ["asset-1"],
      select_all: false,
    });

    await wrapper.findAll("button")[3].trigger("click");
    await nextTick();
    expect(store.previewBrokenDbPathFix).toHaveBeenCalledWith({
      asset_ids: ["asset-2"],
      select_all: false,
    });
  });

  it("previews only eligible zero-byte items and blocks critical originals", async () => {
    const wrapper = mount(CatalogRemediationPanel, {
      global: {
        stubs: {
          StatusTag: {
            template: "<span>{{ status }}</span>",
            props: ["status"],
          },
        },
      },
    });
    await nextTick();

    const checkboxes = wrapper.findAll("tbody input[type='checkbox']");
    expect((checkboxes[4].element as HTMLInputElement).disabled).toBe(true);

    await checkboxes[3].setValue(true);
    await nextTick();
    const previewSelectedButtons = wrapper
      .findAll("button")
      .filter((button) => button.text().includes("Preview selected (1)"));
    await previewSelectedButtons[0].trigger("click");
    await nextTick();

    expect(store.previewZeroByte).toHaveBeenCalledWith({
      finding_ids: ["zero-1"],
      select_all: false,
    });
  });

  it("requires both confirmation checkboxes before apply for fuse-hidden deletion", async () => {
    const wrapper = mount(CatalogRemediationPanel, {
      global: {
        stubs: {
          StatusTag: {
            template: "<span>{{ status }}</span>",
            props: ["status"],
          },
        },
      },
    });
    await nextTick();

    const previewAllButtons = wrapper
      .findAll("button")
      .filter((button) => button.text().includes("Preview all eligible (1)"));
    await previewAllButtons[1].trigger("click");
    await nextTick();

    const applyButton = wrapper
      .findAll("button")
      .find((button) =>
        button.text().includes("Apply `.fuse_hidden*` preview"),
      );
    expect((applyButton!.element as HTMLButtonElement).disabled).toBe(true);

    const confirmations = wrapper.findAll(".catalog-remediation-confirm input");
    await confirmations[confirmations.length - 2].setValue(true);
    await confirmations[confirmations.length - 1].setValue(true);
    await nextTick();

    expect((applyButton!.element as HTMLButtonElement).disabled).toBe(false);
    await applyButton!.trigger("click");
    await nextTick();

    expect(store.applyRemediation).toHaveBeenCalledWith("fuse-run");
  });
});
