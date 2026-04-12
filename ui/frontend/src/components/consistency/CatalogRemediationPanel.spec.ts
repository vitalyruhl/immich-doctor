import { mount } from "@vue/test-utils";
import { nextTick } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";
import CatalogRemediationPanel from "./CatalogRemediationPanel.vue";

function createStore(): any {
  const pageStateByGroup: Record<string, any> = {
    "broken-db": {
      loaded: true,
      isLoading: false,
      error: null,
      limit: 20,
      offset: 0,
      total: 2,
      items: [
        {
          finding_id: "broken-1",
          group_key: "broken-db",
          title: "missing.jpg",
          subtitle: "asset-1",
          owner_label: "Alice",
          owner_hint: "Source owner key: owner-1",
          classification: "missing_confirmed",
          message: "Missing confirmed.",
          summary_path: "/upload/alice/missing.jpg",
          summary_context: null,
          status_reason: "Eligible for cleanup",
          blocked_reason: null,
          actions: ["mark_removed", "ignore"],
          payload: {
            finding_id: "broken-1",
            category_key: "broken-db",
            title: "missing.jpg",
            asset_id: "asset-1",
          },
        },
      ],
    },
    "zero-byte": {
      loaded: true,
      isLoading: false,
      error: null,
      limit: 20,
      offset: 0,
      total: 1,
      items: [
        {
          finding_id: "zero-1",
          group_key: "zero-byte",
          title: "zero.jpg",
          subtitle: "asset-3",
          owner_label: "Echo",
          owner_hint: "Source owner key: owner-3",
          classification: "zero_byte_upload_critical",
          message: "DB-linked zero-byte original.",
          summary_path: "/upload/echo/zero.jpg",
          summary_context: "original_path",
          status_reason: "Only quarantine is allowed.",
          blocked_reason: null,
          actions: ["quarantine", "ignore"],
          payload: {
            finding_id: "zero-1",
            category_key: "zero-byte",
            title: "zero.jpg",
            asset_id: "asset-3",
          },
        },
      ],
    },
    "fuse-hidden": {
      loaded: true,
      isLoading: false,
      error: null,
      limit: 20,
      offset: 0,
      total: 1,
      items: [
        {
          finding_id: "fuse-1",
          group_key: "fuse-hidden",
          title: ".fuse_hidden0001",
          subtitle: "uploads",
          owner_label: "delta",
          owner_hint: null,
          classification: "deletable_orphan",
          message: "Can be deleted directly.",
          summary_path: "/upload/delta/.fuse_hidden0001",
          summary_context: "No open file handles",
          status_reason: "Try deleting the artifact directly.",
          blocked_reason: null,
          actions: ["delete", "ignore"],
          payload: {
            finding_id: "fuse-1",
            category_key: "fuse-hidden",
            title: ".fuse_hidden0001",
          },
        },
      ],
    },
  };

  return {
    actionError: null,
    applyFindingAction: vi.fn().mockResolvedValue(undefined),
    applyBrokenDbAction: vi.fn().mockResolvedValue(undefined),
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
            {
              root_slug: "uploads",
              relative_path: "delta/.fuse_hidden0001",
              absolute_path: "/upload/delta/.fuse_hidden0001",
              file_name: ".fuse_hidden0001",
              size_bytes: 456,
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
    deleteQuarantineItemsPermanently: vi.fn().mockResolvedValue(undefined),
    getGroupPageState: vi.fn((groupKey: string) => pageStateByGroup[groupKey] ?? {
      loaded: false,
      isLoading: false,
      error: null,
      limit: 20,
      offset: 0,
      total: 0,
      items: [],
    }),
    hiddenFindingIds: new Set<string>(),
    ignoreItems: vi.fn().mockResolvedValue(undefined),
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
    loadRemediationFindingDetail: vi.fn().mockResolvedValue(undefined),
    loadRemediationGroupPage: vi.fn().mockResolvedValue(undefined),
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
    quarantineError: null,
    quarantineItems: vi.fn().mockResolvedValue(undefined),
    quarantineState: {
      summary: "1 quarantined finding is currently active.",
    },
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
    refreshRemediation: vi.fn().mockResolvedValue(undefined),
    remediationError: null,
    remediationFindingDetails: {},
    remediationGroups: [
      {
        key: "broken-db",
        title: "DB originals missing in storage",
        description: "Broken original references.",
        count: 1,
      },
      {
        key: "zero-byte",
        title: "Zero-byte files",
        description: "Zero-byte originals and derivatives.",
        count: 1,
      },
      {
        key: "fuse-hidden",
        title: "`.fuse_hidden*` artifacts",
        description: "FUSE artifacts.",
        count: 1,
      },
    ],
    remediationOverview: {
      summary: "Detailed findings loaded.",
    },
    releaseIgnoredItems: vi.fn().mockResolvedValue(undefined),
    restoreQuarantineItems: vi.fn().mockResolvedValue(undefined),
    storageOriginalsMissingInDb: [
      {
        root_slug: "uploads",
        relative_path: "charlie/orphan.jpg",
        absolute_path: "/upload/charlie/orphan.jpg",
        file_name: "orphan.jpg",
        size_bytes: 123,
      },
      {
        root_slug: "uploads",
        relative_path: "delta/.fuse_hidden0001",
        absolute_path: "/upload/delta/.fuse_hidden0001",
        file_name: ".fuse_hidden0001",
        size_bytes: 456,
      },
    ],
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

  function mountPanel(mode: "findings" | "quarantine" | "ignored" = "findings") {
    return mount(CatalogRemediationPanel, {
      props: { mode },
      global: {
        stubs: {
          EmptyState: { template: "<div>{{ title }} {{ message }}</div>", props: ["title", "message"] },
          StatusTag: { template: "<span>{{ status }}</span>", props: ["status"] },
        },
      },
    });
  }

  it("renders findings with server-backed and local cards", async () => {
    const wrapper = mountPanel();
    await nextTick();

    expect(wrapper.text()).toContain("DB originals missing in storage");
    expect(wrapper.text()).toContain("Storage originals missing in DB");
    expect(wrapper.text()).toContain("Alice");
    expect(wrapper.text()).toContain("Delete visible");
    expect(wrapper.text()).toContain("Ignore unstaged visible");
  });

  it("stages and applies actions from the visible page", async () => {
    const wrapper = mountPanel();
    await nextTick();

    const markRemovedButton = wrapper
      .findAll("button")
      .find((button) => button.text() === "Mark removed");
    await markRemovedButton!.trigger("click");
    await nextTick();

    const performButton = wrapper
      .findAll("button")
      .find((button) => button.text() === "Perform staged actions (1)");
    await performButton!.trigger("click");

    expect(store.applyBrokenDbAction).toHaveBeenCalledWith(["asset-1"], "broken_db_cleanup");
  });

  it("loads item detail only when more info is opened", async () => {
    const wrapper = mountPanel();
    await nextTick();

    const moreInfoButton = wrapper
      .findAll("button")
      .find((button) => button.text() === "...more info");
    await moreInfoButton!.trigger("click");

    expect(store.loadRemediationFindingDetail).toHaveBeenCalledWith("broken-db", "broken-1");
  });

  it("renders the quarantine workspace with dedicated operations", async () => {
    const wrapper = mountPanel("quarantine");
    await nextTick();

    expect(wrapper.text()).toContain("Delete permanently");
  });

  it("renders the ignored workspace with release actions", async () => {
    const wrapper = mountPanel("ignored");
    await nextTick();

    expect(wrapper.text()).toContain("Release ignore");
  });
});
