import { mount } from "@vue/test-utils";
import { nextTick } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ConsistencyView from "./ConsistencyView.vue";

function createStore(): any {
  return {
    catalogJob: {
      jobId: "catalog-consistency-1",
      jobType: "catalog_consistency_validation",
      state: "completed",
      summary: "Catalog consistency completed.",
      createdAt: "2026-04-10T08:00:00+00:00",
      updatedAt: "2026-04-10T08:01:00+00:00",
      startedAt: "2026-04-10T08:00:00+00:00",
      completedAt: "2026-04-10T08:01:00+00:00",
      cancelRequested: false,
      error: null,
      result: {},
    },
    catalogReport: {
      summary: "Catalog snapshot loaded.",
    },
    catalogJobError: null,
    isLoading: false,
    load: vi.fn().mockResolvedValue(undefined),
  };
}

let store = createStore();

vi.mock("@/stores/consistency", () => ({
  useConsistencyStore: () => store,
}));

function mountView() {
  return mount(ConsistencyView, {
    global: {
      stubs: {
        PageHeader: { template: "<div class='page-header-stub'>header</div>" },
        CatalogConsistencyPanel: { template: "<div class='catalog-consistency-panel-stub'>catalog-panel</div>" },
        CatalogRemediationPanel: { template: "<div class='catalog-remediation-panel-stub'>remediation-panel</div>" },
        DisclaimerBanner: { template: "<div class='disclaimer-stub'>disclaimer</div>" },
        LoadingState: { template: "<div class='loading-stub'>loading</div>" },
        ErrorState: { template: "<div class='error-stub'>error</div>" },
      },
    },
  });
}

async function settle() {
  await Promise.resolve();
  await nextTick();
}

describe("ConsistencyView", () => {
  beforeEach(() => {
    store = createStore();
    vi.clearAllMocks();
  });

  it("loads the catalog workflow once on mount and renders only the catalog-based UI", async () => {
    const wrapper = mountView();
    await settle();

    expect(store.load).toHaveBeenCalled();
    expect(wrapper.text()).toContain("catalog-panel");
    expect(wrapper.text()).toContain("remediation-panel");
    expect(wrapper.text()).not.toContain("Scan summary");
    expect(wrapper.text()).not.toContain("Preview and apply");
    expect(wrapper.text()).not.toContain("Findings review");
    expect(wrapper.text()).not.toContain("Repair readiness");
  });

  it("does not show a timeout error state when a cached catalog report already exists", async () => {
    store.catalogJobError = "Request timed out.";
    store.catalogReport = {
      summary: "Catalog snapshot loaded.",
    };

    const wrapper = mountView();
    await settle();

    expect(wrapper.text()).toContain("catalog-panel");
    expect(wrapper.text()).not.toContain("error");
  });

  it("shows the initial error state only when no cached catalog report exists", async () => {
    store.catalogReport = null;
    store.catalogJob = null;
    store.catalogJobError = "Request timed out.";

    const wrapper = mountView();
    await settle();

    expect(wrapper.text()).toContain("error");
  });
});
