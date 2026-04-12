import { mount } from "@vue/test-utils";
import { nextTick } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";
import CatalogRemediationPanel from "./CatalogRemediationPanel.vue";

function createStore(): any {
  return {
    actionError: null,
    applyBrokenDbAction: vi.fn().mockResolvedValue(undefined),
    brokenDbOriginals: [
      {
        finding_id: "broken-1",
        asset_id: "asset-1",
        asset_name: "missing.jpg",
        owner_id: "owner-1",
        owner_label: "Alice",
        classification: "missing_confirmed",
        expected_database_path: "/upload/alice/missing.jpg",
        expected_absolute_path: "/upload/alice/missing.jpg",
        expected_relative_path: "alice/missing.jpg",
        found_absolute_path: null,
        action_reason: "Eligible for cleanup",
        message: "Missing confirmed.",
      },
      {
        finding_id: "broken-2",
        asset_id: "asset-2",
        asset_name: "path-fix.jpg",
        owner_id: "owner-2",
        owner_label: "Bob",
        classification: "found_with_hash_match",
        expected_database_path: "/upload/bob/path-fix.jpg",
        expected_absolute_path: "/upload/bob/path-fix.jpg",
        expected_relative_path: "bob/path-fix.jpg",
        found_absolute_path: "/upload/bob-relocated/path-fix.jpg",
        action_reason: "Eligible for path fix",
        message: "Hash match.",
      },
    ],
    catalogJobError: null,
    catalogReport: {
      summary: "Catalog report loaded.",
      sections: [
        {
          name: "storage_originals_missing_in_db",
          rows: [
            {
              root_slug: "uploads",
              relative_path: "charlie/orphan.jpg",
              absolute_path: "/upload/charlie/orphan.jpg",
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
              root_slug: "thumbs",
              relative_path: "charlie/orphan-preview.webp",
              absolute_path: "/thumbs/charlie/orphan-preview.webp",
              original_relative_path: "charlie/original.jpg",
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
      ],
    },
    fuseHiddenOrphans: [
      {
        finding_id: "fuse-1",
        root_slug: "uploads",
        relative_path: "delta/.fuse_hidden0001",
        absolute_path: "/upload/delta/.fuse_hidden0001",
        file_name: ".fuse_hidden0001",
        size_bytes: 456,
        owner_id: null,
        owner_label: "delta",
        classification: "deletable_orphan",
        action_reason: "Safe for quarantine-first handling.",
        in_use_check_reason: "No open file handles",
        message: "Safe to quarantine.",
      },
    ],
    hiddenFindingIds: new Set<string>(),
    ignoredError: null,
    ignoredFindings: [
      {
        ignored_item_id: "ignored-1",
        category_key: "zero-byte",
        owner_id: null,
        owner_label: "echo",
        reason: "Operator ignored the finding.",
        source_path: "/upload/echo/skip.jpg",
        created_at: "2026-04-10T08:00:00+00:00",
      },
    ],
    ignoredState: {
      summary: "1 ignored finding is currently active.",
    },
    isApplyingAction: false,
    isLoadingRemediation: false,
    isRefreshingRemediation: false,
    lastActionSummary: null,
    quarantineError: null,
    quarantineItems: vi.fn().mockResolvedValue(undefined),
    quarantinedItems: [
      {
        quarantine_item_id: "quarantine-1",
        category_key: "storage-missing",
        owner_id: null,
        owner_label: "frank",
        source_path: "/upload/frank/orphan.jpg",
        original_relative_path: null,
        quarantine_path: "/quarantine/catalog-remediation/storage-missing/item/orphan.jpg",
        reason: "Operator quarantined the finding.",
      },
    ],
    quarantineState: {
      summary: "1 quarantined finding is currently active.",
    },
    loadRemediation: vi.fn().mockResolvedValue(undefined),
    refreshRemediation: vi.fn().mockResolvedValue(undefined),
    releaseIgnoredItems: vi.fn().mockResolvedValue(undefined),
    remediationError: null,
    remediationLoaded: true,
    remediationScanResult: {
      summary: "Detailed findings loaded.",
    },
    restoreQuarantineItems: vi.fn().mockResolvedValue(undefined),
    storageOriginalsMissingInDb: [
      {
        root_slug: "uploads",
        relative_path: "charlie/orphan.jpg",
        absolute_path: "/upload/charlie/orphan.jpg",
        file_name: "orphan.jpg",
        size_bytes: 123,
      },
    ],
    ignoreItems: vi.fn().mockResolvedValue(undefined),
    orphanDerivatives: [
      {
        asset_id: "asset-9",
        derivative_type: "preview",
        root_slug: "thumbs",
        relative_path: "charlie/orphan-preview.webp",
        absolute_path: "/thumbs/charlie/orphan-preview.webp",
        original_relative_path: "charlie/original.jpg",
      },
    ],
    zeroByteFindings: [
      {
        finding_id: "zero-1",
        root_slug: "uploads",
        relative_path: "echo/zero.jpg",
        absolute_path: "/upload/echo/zero.jpg",
        file_name: "zero.jpg",
        size_bytes: 0,
        classification: "zero_byte_upload_critical",
        asset_id: "asset-3",
        asset_name: "zero.jpg",
        owner_id: "owner-3",
        owner_label: "Echo",
        db_reference_kind: "original_path",
        original_relative_path: "echo/zero.jpg",
        action_reason: "Only quarantine is allowed.",
        message: "DB-linked zero-byte original.",
      },
    ],
    deleteQuarantineItemsPermanently: vi.fn().mockResolvedValue(undefined),
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

  it("renders findings with category-local actions and owner labels", async () => {
    const wrapper = mount(CatalogRemediationPanel, {
      props: {
        mode: "findings",
      },
      global: {
        stubs: {
          EmptyState: { template: "<div>{{ title }} {{ message }}</div>", props: ["title", "message"] },
          StatusTag: { template: "<span>{{ status }}</span>", props: ["status"] },
        },
      },
    });
    await nextTick();

    expect(wrapper.text()).toContain("DB originals missing in storage");
    expect(wrapper.text()).toContain("Storage originals missing in DB");
    expect(wrapper.text()).toContain("Alice");
    expect(wrapper.text()).toContain("Quarantine all");
    expect(wrapper.text()).toContain("Ignore unselected");
    expect(wrapper.text()).not.toContain("Select all visible");
  });

  it("stages and applies category actions without checkbox selection", async () => {
    const wrapper = mount(CatalogRemediationPanel, {
      props: {
        mode: "findings",
      },
      global: {
        stubs: {
          EmptyState: { template: "<div>{{ title }} {{ message }}</div>", props: ["title", "message"] },
          StatusTag: { template: "<span>{{ status }}</span>", props: ["status"] },
        },
      },
    });
    await nextTick();

    const markRemovedButton = wrapper
      .findAll("button")
      .find((button) => button.text() === "Mark removed");
    await markRemovedButton!.trigger("click");
    await nextTick();

    const performButton = wrapper
      .findAll("button")
      .find((button) => button.text().includes("Perform staged actions"));
    await performButton!.trigger("click");

    expect(store.applyBrokenDbAction).toHaveBeenCalledWith(["asset-1"], "broken_db_cleanup");
  });

  it("renders the quarantine workspace with dedicated operations", async () => {
    const wrapper = mount(CatalogRemediationPanel, {
      props: {
        mode: "quarantine",
      },
      global: {
        stubs: {
          EmptyState: { template: "<div>{{ title }} {{ message }}</div>", props: ["title", "message"] },
          StatusTag: { template: "<span>{{ status }}</span>", props: ["status"] },
        },
      },
    });
    await nextTick();

    expect(wrapper.text()).toContain("Delete permanently");
  });

  it("renders the ignored workspace with release actions", async () => {
    const wrapper = mount(CatalogRemediationPanel, {
      props: {
        mode: "ignored",
      },
      global: {
        stubs: {
          EmptyState: { template: "<div>{{ title }} {{ message }}</div>", props: ["title", "message"] },
          StatusTag: { template: "<span>{{ status }}</span>", props: ["status"] },
        },
      },
    });
    await nextTick();

    expect(wrapper.text()).toContain("Release ignore");
  });

  it("supports lazy loading of cached findings", async () => {
    store.remediationLoaded = false;

    const wrapper = mount(CatalogRemediationPanel, {
      props: {
        mode: "findings",
      },
      global: {
        stubs: {
          EmptyState: { template: "<div>{{ title }} {{ message }}</div>", props: ["title", "message"] },
          StatusTag: { template: "<span>{{ status }}</span>", props: ["status"] },
        },
      },
    });
    await nextTick();

    const loadButton = wrapper.findAll("button").find((button) => button.text() === "Load cached findings");
    expect(loadButton).toBeTruthy();
    await loadButton!.trigger("click");
    expect(store.loadRemediation).toHaveBeenCalled();
  });
});
