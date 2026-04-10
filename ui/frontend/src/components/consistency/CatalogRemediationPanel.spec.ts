import { mount } from "@vue/test-utils";
import { nextTick } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";
import CatalogRemediationPanel from "./CatalogRemediationPanel.vue";

function createStore(): any {
  return {
    catalogReport: {
      summary: "Catalog report loaded.",
      generated_at: "2026-04-10T08:00:00+00:00",
      sections: [
        {
          name: "STORAGE_ORIGINALS_MISSING_IN_DB",
          rows: [
            {
              root_slug: "uploads",
              relative_path: "user-a/orphan.jpg",
              file_name: "orphan.jpg",
              size_bytes: 123,
            },
          ],
        },
        {
          name: "ORPHAN_DERIVATIVES_WITHOUT_ORIGINAL",
          rows: [
            {
              asset_id: "asset-9",
              derivative_type: "preview",
              relative_path: "user-a/orphan-preview.webp",
              original_relative_path: "user-a/original.jpg",
            },
          ],
        },
        {
          name: "UNMAPPED_DATABASE_PATHS",
          rows: [
            {
              asset_id: "asset-7",
              asset_name: "legacy.jpg",
              database_path: "/usr/src/app/upload/thumbs/legacy.jpg",
              mapping_status: "unexpected_root",
              path_kind: "original",
            },
          ],
        },
        {
          name: "ZERO_BYTE_FILES",
          rows: [
            {
              root_slug: "uploads",
              relative_path: "user-a/raw-zero.jpg",
              file_name: "raw-zero.jpg",
              size_bytes: 0,
              generation: 2,
            },
          ],
        },
      ],
    },
    remediationScanResult: {
      summary: "Catalog remediation findings loaded.",
    },
    remediationError: null,
    isLoadingRemediation: false,
    brokenDbOriginals: [
      {
        finding_id: "broken-1",
        asset_id: "asset-1",
        asset_name: "missing.jpg",
        classification: "missing_confirmed",
        expected_database_path: "/usr/src/app/upload/upload/user-a/missing.jpg",
        found_absolute_path: null,
        action_reason: "Eligible for cleanup",
        action_eligible: true,
        message: "Missing confirmed.",
      },
      {
        finding_id: "broken-2",
        asset_id: "asset-2",
        asset_name: "path-fix.jpg",
        classification: "found_with_hash_match",
        expected_database_path: "/usr/src/app/upload/upload/user-a/path-fix.jpg",
        found_absolute_path: "/upload/user-a/path-fix.jpg",
        action_reason: "Eligible for path fix",
        action_eligible: true,
        message: "Hash match.",
      },
      {
        finding_id: "broken-3",
        asset_id: "asset-3",
        asset_name: "relocated.jpg",
        classification: "found_elsewhere",
        expected_database_path: "/usr/src/app/upload/upload/user-a/relocated.jpg",
        found_absolute_path: "/upload/user-b/relocated.jpg",
        action_reason: "Inspect only",
        action_eligible: false,
        message: "Found elsewhere.",
      },
    ],
    storageOriginalsMissingInDb: [
      {
        root_slug: "uploads",
        relative_path: "user-a/orphan.jpg",
        file_name: "orphan.jpg",
        size_bytes: 123,
      },
    ],
    orphanDerivatives: [
      {
        asset_id: "asset-9",
        derivative_type: "preview",
        relative_path: "user-a/orphan-preview.webp",
        original_relative_path: "user-a/original.jpg",
      },
    ],
    zeroByteFindings: [
      {
        finding_id: "zero-1",
        root_slug: "uploads",
        absolute_path: "/upload/user-a/orphan-zero.jpg",
        file_name: "orphan-zero.jpg",
        size_bytes: 0,
        classification: "zero_byte_upload_orphan",
        action_reason: "Delete allowed",
        message: "Orphan zero-byte upload.",
      },
      {
        finding_id: "zero-2",
        root_slug: "uploads",
        absolute_path: "/upload/user-a/critical-zero.jpg",
        file_name: "critical-zero.jpg",
        size_bytes: 0,
        classification: "zero_byte_upload_critical",
        action_reason: "Still referenced as original",
        message: "Critical original.",
      },
    ],
    fuseHiddenOrphans: [
      {
        finding_id: "fuse-1",
        root_slug: "uploads",
        absolute_path: "/upload/user-a/.fuse_hidden0001",
        file_name: ".fuse_hidden0001",
        size_bytes: 123,
        classification: "blocked_in_use",
        in_use_check_reason: "File is still in use",
        action_reason: "Ignore only",
        message: "Still in use.",
      },
      {
        finding_id: "fuse-2",
        root_slug: "uploads",
        absolute_path: "/upload/user-b/.fuse_hidden0002",
        file_name: ".fuse_hidden0002",
        size_bytes: 456,
        classification: "deletable_orphan",
        in_use_check_reason: "No open file handles",
        action_reason: "Eligible",
        message: "Safe to delete.",
      },
    ],
    unmappedDatabasePaths: [
      {
        asset_id: "asset-7",
        asset_name: "legacy.jpg",
        database_path: "/usr/src/app/upload/thumbs/legacy.jpg",
        mapping_status: "unexpected_root",
        path_kind: "original",
      },
    ],
    loadRemediation: vi.fn().mockResolvedValue(undefined),
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

  it("renders grouped catalog findings without preview/apply blocks", async () => {
    const wrapper = mount(CatalogRemediationPanel, {
      global: {
        stubs: {
          EmptyState: { template: "<div>{{ title }} {{ message }}</div>", props: ["title", "message"] },
          StatusTag: { template: "<span>{{ status }}</span>", props: ["status"] },
        },
      },
    });
    await nextTick();

    expect(wrapper.text()).toContain("Catalog findings workspace");
    expect(wrapper.text()).toContain("DB originals missing in storage");
    expect(wrapper.text()).toContain("Storage originals missing in DB");
    expect(wrapper.text()).toContain("Zero-byte files");
    expect(wrapper.text()).toContain("`.fuse_hidden*` artifacts");
    expect(wrapper.text()).not.toContain("Preview");
    expect(wrapper.text()).not.toContain("Apply");

    const groupCards = wrapper.findAll(".catalog-remediation-group");
    expect(groupCards.length).toBeGreaterThanOrEqual(5);
    expect(groupCards.some((card) => card.text().includes("DB originals missing in storage"))).toBe(true);
    expect(groupCards.some((card) => card.text().includes("Storage originals missing in DB"))).toBe(true);
  });

  it("stages context-sensitive bulk actions only for selected eligible rows", async () => {
    const wrapper = mount(CatalogRemediationPanel, {
      global: {
        stubs: {
          EmptyState: { template: "<div>{{ title }} {{ message }}</div>", props: ["title", "message"] },
          StatusTag: { template: "<span>{{ status }}</span>", props: ["status"] },
        },
      },
    });
    await nextTick();

    const selectAllButton = wrapper
      .findAll("button")
      .find((button) => button.text() === "Select all visible");
    await selectAllButton!.trigger("click");
    await nextTick();

    expect(wrapper.text()).toContain("Repair selected");
    expect(wrapper.text()).toContain("Delete selected");

    const deleteSelectedButton = wrapper
      .findAll("button")
      .find((button) => button.text().includes("Delete selected"));
    await deleteSelectedButton!.trigger("click");
    await nextTick();

    expect(wrapper.text()).toContain("Staged actions");
    expect(wrapper.text()).toContain("Delete:");
  });

  it("shows blocked reasons and row-specific actions per finding type", async () => {
    const wrapper = mount(CatalogRemediationPanel, {
      global: {
        stubs: {
          EmptyState: { template: "<div>{{ title }} {{ message }}</div>", props: ["title", "message"] },
          StatusTag: { template: "<span>{{ status }}</span>", props: ["status"] },
        },
      },
    });
    await nextTick();

    expect(wrapper.text()).toContain("Still referenced as original");
    expect(wrapper.text()).toContain("Inspect");
    expect(wrapper.text()).toContain("Mark removed");
    expect(wrapper.text()).toContain("Repair path");
    expect(wrapper.text()).toContain("Quarantine");
    expect(wrapper.text()).toContain("Ignore");
  });

  it("falls back to raw zero-byte snapshot rows when remediation enrichment is unavailable", async () => {
    store.zeroByteFindings = [];

    const wrapper = mount(CatalogRemediationPanel, {
      global: {
        stubs: {
          EmptyState: { template: "<div>{{ title }} {{ message }}</div>", props: ["title", "message"] },
          StatusTag: { template: "<span>{{ status }}</span>", props: ["status"] },
        },
      },
    });
    await nextTick();

    expect(wrapper.text()).toContain("raw-zero.jpg");
    expect(wrapper.text()).toContain("Zero-byte snapshot");
    expect(wrapper.text()).toContain("Detailed remediation classification is not loaded.");
  });
});
