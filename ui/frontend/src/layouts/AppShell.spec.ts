import { mount } from "@vue/test-utils";
import { reactive } from "vue";
import AppShell from "./AppShell.vue";

const appStore = reactive({
  sidebarCollapsed: false,
  toggleSidebar: vi.fn(),
});

vi.mock("@/stores/app", () => ({
  useAppStore: () => appStore,
}));

vi.mock("vue-router", () => ({
  RouterLink: {
    name: "RouterLink",
    props: ["to", "title", "ariaLabel"],
    template: `
      <a :href="typeof to === 'string' ? to : '#' " :title="title" :aria-label="ariaLabel">
        <slot />
      </a>
    `,
  },
  RouterView: {
    name: "RouterView",
    template: "<div />",
  },
  useRoute: () => ({
    name: "settings",
    meta: {
      title: "Settings",
      section: "Operations",
    },
  }),
}));

describe("AppShell", () => {
  beforeEach(() => {
    appStore.sidebarCollapsed = false;
    appStore.toggleSidebar.mockReset();
  });

  it("keeps the expanded shell and shows navigation text by default", () => {
    const wrapper = mount(AppShell);

    expect(wrapper.classes()).not.toContain("app-shell--compact");
    expect(wrapper.text()).toContain("Settings");
    expect(wrapper.text()).toContain("Operational configuration placeholders.");
  });

  it("switches the shell into compact mode and keeps collapsed navigation accessible", () => {
    appStore.sidebarCollapsed = true;

    const wrapper = mount(AppShell);

    expect(wrapper.classes()).toContain("app-shell--compact");
    expect(wrapper.text()).not.toContain("Operational configuration placeholders.");

    const settingsLink = wrapper
      .findAll(".app-sidebar__link")
      .find((link) => link.attributes("title") === "Settings");

    expect(settingsLink).toBeTruthy();
    expect(settingsLink?.attributes("aria-label")).toBe("Settings");
  });
});
