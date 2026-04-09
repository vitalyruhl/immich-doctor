import { mount } from "@vue/test-utils";
import { nextTick } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";
import SettingsView from "./SettingsView.vue";

function createStore() {
  return {
    overview: {
      generatedAt: "2026-04-09T10:00:00+00:00",
      schemaVersion: "v1",
      capabilityState: "PARTIAL",
      summary: "Settings overview loaded.",
      capabilities: [],
      sections: [],
    },
    sections: [],
    capabilities: [],
    capabilitySummary: "Settings overview loaded.",
    capabilityState: "PARTIAL",
    isLoading: false,
    mocked: false,
    testbedDump: null as null | {
      enabled: boolean;
      canImport: boolean;
      defaultPath: string | null;
      defaultFormat: string;
      initMode: string;
      autoImportOnEmpty: boolean;
      summary: string;
    },
    testbedImportResult: null as null | {
      summary: string;
      classification: string;
      effectivePath: string;
      meaningfulErrorCount: number;
    },
    isImporting: false,
    importError: null as string | null,
    load: vi.fn().mockResolvedValue(undefined),
    triggerTestbedDumpImport: vi.fn().mockResolvedValue(null),
  };
}

let store = createStore();

vi.mock("@/stores/settings", () => ({
  useSettingsStore: () => store,
}));

function mountView() {
  return mount(SettingsView, {
    global: {
      stubs: {
        PageHeader: { template: "<div class='page-header-stub' />" },
        LoadingState: { template: "<div class='loading-stub' />" },
        EmptyState: { template: "<div class='empty-stub' />" },
        CapabilityTag: { template: "<span class='capability-tag-stub'>{{ state }}</span>", props: ["state"] },
      },
    },
  });
}

async function settle() {
  await Promise.resolve();
  await nextTick();
}

describe("SettingsView", () => {
  beforeEach(() => {
    store = createStore();
    vi.clearAllMocks();
  });

  it("keeps the testbed import control hidden outside the testbed context", async () => {
    const wrapper = mountView();
    await settle();

    expect(wrapper.text()).not.toContain("Testbed dump reload");
  });

  it("prefills and submits the testbed import form in dev-testbed mode", async () => {
    store.testbedDump = {
      enabled: true,
      canImport: true,
      defaultPath: "C:\\Temp\\immich-testdata\\db\\full\\immich.sql",
      defaultFormat: "auto",
      initMode: "FROM_DUMP",
      autoImportOnEmpty: true,
      summary: "The testbed can auto-load the configured dump into an empty database.",
    };

    const wrapper = mountView();
    await settle();

    expect(wrapper.text()).toContain("Testbed dump reload");
    const pathInput = wrapper.get('input[type="text"]');
    expect((pathInput.element as HTMLInputElement).value).toBe(
      "C:\\Temp\\immich-testdata\\db\\full\\immich.sql",
    );

    const submitButton = wrapper
      .findAll("button")
      .find((button) => button.text().includes("Reload testbed DB"));
    expect(submitButton).toBeTruthy();
    expect((submitButton!.element as HTMLButtonElement).disabled).toBe(true);

    await wrapper.get('input[type="checkbox"]').setValue(true);
    await settle();
    expect((submitButton!.element as HTMLButtonElement).disabled).toBe(false);

    await submitButton!.trigger("click");
    await settle();

    expect(store.triggerTestbedDumpImport).toHaveBeenCalledWith({
      path: "C:\\Temp\\immich-testdata\\db\\full\\immich.sql",
      format: "auto",
      force: true,
    });
  });
});
