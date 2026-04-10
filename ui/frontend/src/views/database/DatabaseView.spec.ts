import { mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import DatabaseView from "./DatabaseView.vue";

function createStore() {
  return {
    overview: {
      generatedAt: "2026-04-09T10:00:00+00:00",
      connectivity: {
        status: "ok",
        summary: "Database access works against postgres:5432.",
        details: "Host resolution, TCP reachability, PostgreSQL login, and round-trip query passed.",
        host: "postgres",
        port: 5432,
        databaseName: "immich",
        accessWorks: true,
        error: null,
        engine: "PostgreSQL",
        serverVersion: "14.10",
        serverVersionNum: "140010",
        serverVersionRaw: "PostgreSQL 14.10",
        serverVersionError: null,
      },
      immich: {
        status: "ok",
        summary: "Detected Immich 2.5.6 with schema profile supported.",
        details: "Immich version signal: 2.5.6 (source: version_history, confidence: high).",
        productVersionCurrent: "2.5.6",
        productVersionConfidence: "high",
        productVersionSource: "version_history",
        supportStatus: "supported",
        schemaGenerationKey: "immich_schema:key",
        riskFlags: [],
        notes: [],
      },
      compatibility: {
        status: "ok",
        summary: "Detected Immich 2.5.6, which matches the currently tested validation target.",
        details: "This compatibility signal comes from schema detection plus version_history metadata.",
        testedAgainstImmichVersion: "2.5.6",
      },
      relatedFindings: {
        status: "warning",
        summary: "Consistency findings are waiting for a current storage index.",
        details: "Open the Consistency page for detailed compare rows and repair workflows.",
        route: "/consistency",
      },
      testedAgainstImmichVersion: "2.5.6",
    },
    isLoading: false,
    error: null as string | null,
    load: vi.fn().mockResolvedValue(undefined),
  };
}

let store = createStore();

vi.mock("@/stores/database", () => ({
  useDatabaseStore: () => store,
}));

describe("DatabaseView", () => {
  beforeEach(() => {
    store = createStore();
    vi.clearAllMocks();
  });

  it("renders database connectivity, version, and consistency summary details", async () => {
    const wrapper = mount(DatabaseView, {
      global: {
        stubs: {
          PageHeader: { template: "<div class='page-header-stub' />" },
          DisclaimerBanner: { template: "<div class='disclaimer-stub' />" },
          RiskNotice: { template: "<div class='risk-notice-stub'>{{ message }}</div>", props: ["message"] },
          LoadingState: { template: "<div class='loading-stub' />" },
          ErrorState: { template: "<div class='error-stub' />" },
          StatusTag: { template: "<span class='status-tag-stub'>{{ status }}</span>", props: ["status"] },
          RouterLink: { template: "<a><slot /></a>" },
        },
      },
    });

    await Promise.resolve();

    expect(store.load).toHaveBeenCalled();
    expect(wrapper.text()).toContain("Database access works against postgres:5432.");
    expect(wrapper.text()).toContain("Detected Immich 2.5.6 with schema profile supported.");
    expect(wrapper.text()).toContain("Consistency findings are waiting for a current storage index.");
    expect(wrapper.text()).toContain("Immich 2.5.6");
  });

  it("keeps cached database details visible when a later refresh error exists", async () => {
    store.error = "Request timed out.";

    const wrapper = mount(DatabaseView, {
      global: {
        stubs: {
          PageHeader: { template: "<div class='page-header-stub' />" },
          DisclaimerBanner: { template: "<div class='disclaimer-stub' />" },
          RiskNotice: { template: "<div class='risk-notice-stub'>{{ message }}</div>", props: ["message"] },
          LoadingState: { template: "<div class='loading-stub' />" },
          ErrorState: { template: "<div class='error-stub'>error</div>" },
          StatusTag: { template: "<span class='status-tag-stub'>{{ status }}</span>", props: ["status"] },
          RouterLink: { template: "<a><slot /></a>" },
        },
      },
    });

    await Promise.resolve();

    expect(wrapper.text()).toContain("Database access works against postgres:5432.");
    expect(wrapper.text()).not.toContain("error");
  });
});
