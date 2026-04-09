import { mount } from "@vue/test-utils";
import { nextTick } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { CatalogValidationReport, CatalogWorkflowJobRecord } from "@/api/types/catalog";
import CatalogConsistencyPanel from "./CatalogConsistencyPanel.vue";

function createStore() {
  return {
    catalogJob: {
      jobId: null,
      jobType: "catalog_consistency_validation",
      state: "pending",
      summary: "Catalog consistency is waiting for a committed catalog scan.",
      createdAt: "2026-04-09T12:00:00+00:00",
      updatedAt: "2026-04-09T12:00:00+00:00",
      startedAt: null,
      completedAt: null,
      cancelRequested: false,
      error: null,
      result: {},
    } as CatalogWorkflowJobRecord | null,
    catalogReport: null as CatalogValidationReport | null,
    catalogJobError: null,
    isCatalogLoading: false,
    isCatalogStarting: false,
    loadCatalogJob: vi.fn().mockImplementation(async () => store.catalogJob),
    startCatalog: vi.fn().mockResolvedValue(undefined),
  };
}

let store = createStore();

vi.mock("@/stores/consistency", () => ({
  useConsistencyStore: () => store,
}));

async function settle(): Promise<void> {
  await Promise.resolve();
  await nextTick();
  await Promise.resolve();
  await nextTick();
}

describe("CatalogConsistencyPanel", () => {
  beforeEach(() => {
    store = createStore();
    vi.clearAllMocks();
  });

  it("auto-starts the workflow when no cached report exists yet", async () => {
    mount(CatalogConsistencyPanel, {
      global: {
        stubs: {
          EmptyState: { template: "<div><slot /></div>", props: ["title", "message"] },
          StatusTag: { template: "<span>{{ status }}</span>", props: ["status"] },
        },
      },
    });

    await settle();

    expect(store.loadCatalogJob).toHaveBeenCalled();
    expect(store.startCatalog).toHaveBeenCalledWith(false);
  });

  it("renders report counts and allows manual rescans", async () => {
    store.catalogJob = {
      jobId: "catalog-consistency-1",
      jobType: "catalog_consistency_validation",
      state: "completed",
      summary: "Catalog consistency completed.",
      createdAt: "2026-04-09T12:00:00+00:00",
      updatedAt: "2026-04-09T12:01:00+00:00",
      startedAt: "2026-04-09T12:00:00+00:00",
      completedAt: "2026-04-09T12:01:00+00:00",
      cancelRequested: false,
      error: null,
      result: {},
    };
    store.catalogReport = {
      domain: "consistency.catalog",
      action: "validate",
      status: "FAIL",
      summary: "Catalog consistency found mismatches.",
      generated_at: "2026-04-09T12:01:00+00:00",
      checks: [],
      sections: [
        {
          name: "DB_ORIGINALS_MISSING_ON_STORAGE",
          status: "fail",
          rows: [{ asset_id: "asset-1", asset_name: "missing.jpg", database_path: "/usr/src/app/upload/upload/user-a/missing.jpg" }],
        },
        {
          name: "STORAGE_ORIGINALS_MISSING_IN_DB",
          status: "warn",
          rows: [{ root_slug: "uploads", relative_path: "user-a/lonely.jpg" }],
        },
        {
          name: "ORPHAN_DERIVATIVES_WITHOUT_ORIGINAL",
          status: "warn",
          rows: [{ asset_id: "asset-1", derivative_type: "preview" }],
        },
        {
          name: "ZERO_BYTE_FILES",
          status: "fail",
          rows: [{ root_slug: "uploads", relative_path: "user-a/zero.jpg" }],
        },
        {
          name: "UNMAPPED_DATABASE_PATHS",
          status: "warn",
          rows: [{ asset_id: "asset-2", database_path: "/usr/src/app/upload/thumbs/x.webp" }],
        },
      ],
      metrics: [],
      recommendations: [],
      metadata: {
        latestScanCommittedAt: "2026-04-09T12:00:00+00:00",
        snapshotBasis: [
          {
            rootSlug: "uploads",
            snapshotId: 7,
            generation: 2,
            committedAt: "2026-04-09T12:00:00+00:00",
          },
        ],
        totals: {
          dbOriginalsMissingOnStorage: 1,
          storageOriginalsMissingInDb: 1,
          orphanDerivativesWithoutOriginal: 1,
          zeroByteFiles: 1,
          unmappedDatabasePaths: 1,
        },
        truncated: {},
      },
    };

    const wrapper = mount(CatalogConsistencyPanel, {
      global: {
        stubs: {
          EmptyState: { template: "<div><slot /></div>", props: ["title", "message"] },
          StatusTag: { template: "<span>{{ status }}</span>", props: ["status"] },
        },
      },
    });

    await settle();

    expect(wrapper.text()).toContain("Catalog-backed storage compare");
    expect(wrapper.text()).toContain("DB not found in snapshot");
    expect(wrapper.text()).toContain("missing.jpg");
    expect(wrapper.text()).toContain("/usr/src/app/upload/upload/user-a/missing.jpg");

    const button = wrapper
      .findAll("button")
      .find((candidate) => candidate.text() === "Rescan consistency");
    expect(button).toBeTruthy();

    await button!.trigger("click");
    expect(store.startCatalog).toHaveBeenCalledWith(true);
  });

  it("shows stale rebuild messaging without rendering stale report tables", async () => {
    store.catalogJob = {
      jobId: null,
      jobType: "catalog_consistency_validation",
      state: "pending",
      summary: "Catalog consistency needs a rebuild because the storage index changed.",
      createdAt: "2026-04-09T12:00:00+00:00",
      updatedAt: "2026-04-09T12:02:00+00:00",
      startedAt: null,
      completedAt: null,
      cancelRequested: false,
      error: null,
      result: {
        stale: true,
        staleReason: "catalog_scan_updated",
        previousCompareGeneratedAt: "2026-04-09T12:01:00+00:00",
        latestScanCommittedAt: "2026-04-09T12:02:00+00:00",
      },
    };
    store.catalogReport = null;

    const wrapper = mount(CatalogConsistencyPanel, {
      global: {
        stubs: {
          EmptyState: { template: "<div>{{ title }} {{ message }}</div>", props: ["title", "message"] },
          StatusTag: { template: "<span>{{ status }}</span>", props: ["status"] },
        },
      },
    });

    await settle();

    expect(wrapper.text()).toContain("Catalog compare is rebuilding");
    expect(wrapper.text()).toContain("The last compare is stale");
    expect(wrapper.text()).not.toContain("DB not found in snapshot");
  });
});
