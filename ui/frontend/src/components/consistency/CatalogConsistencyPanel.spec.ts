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
      summary: "No catalog consistency validation has been started yet.",
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

  it("loads cached job state without auto-starting a new compare", async () => {
    mount(CatalogConsistencyPanel, {
      global: {
        stubs: {
          EmptyState: { template: "<div>{{ title }} {{ message }}</div>", props: ["title", "message"] },
          StatusTag: { template: "<span>{{ status }}</span>", props: ["status"] },
        },
      },
    });

    await settle();

    expect(store.loadCatalogJob).toHaveBeenCalled();
    expect(store.startCatalog).not.toHaveBeenCalled();
  });

  it("renders summary cards from the cached report and offers explicit rerun only", async () => {
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
      sections: [],
      metrics: [],
      recommendations: [],
      metadata: {
        latestScanCommittedAt: "2026-04-09T12:00:00+00:00",
        totals: {
          dbOriginalsMissingOnStorage: 1,
          storageOriginalsMissingInDb: 2,
          orphanDerivativesWithoutOriginal: 3,
          zeroByteFiles: 4,
          unmappedDatabasePaths: 5,
        },
      },
    };

    const wrapper = mount(CatalogConsistencyPanel, {
      global: {
        stubs: {
          EmptyState: { template: "<div>{{ title }} {{ message }}</div>", props: ["title", "message"] },
          StatusTag: { template: "<span>{{ status }}</span>", props: ["status"] },
        },
      },
    });

    await settle();

    expect(wrapper.text()).toContain("Catalog-backed consistency snapshot");
    expect(wrapper.text()).toContain("DB missing in storage");
    expect(wrapper.text()).toContain("Storage missing in DB");
    expect(wrapper.text()).not.toContain("No findings for");

    const button = wrapper
      .findAll("button")
      .find((candidate) => candidate.text() === "Run new compare");
    expect(button).toBeTruthy();

    await button!.trigger("click");
    expect(store.startCatalog).toHaveBeenCalledWith(true);
  });

  it("shows stale snapshot messaging without hiding the explicit start control", async () => {
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

    const wrapper = mount(CatalogConsistencyPanel, {
      global: {
        stubs: {
          EmptyState: { template: "<div>{{ title }} {{ message }}</div>", props: ["title", "message"] },
          StatusTag: { template: "<span>{{ status }}</span>", props: ["status"] },
        },
      },
    });

    await settle();

    expect(wrapper.text()).toContain("Catalog compare is stale");
    expect(wrapper.text()).toContain("A new compare must be started explicitly.");
    expect(wrapper.text()).toContain("Start consistency");
  });
});
