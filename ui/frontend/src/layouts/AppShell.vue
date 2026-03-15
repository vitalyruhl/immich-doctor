<template>
  <div class="app-shell">
    <AppSidebar :collapsed="appStore.sidebarCollapsed" />
    <div class="app-shell__content">
      <AppTopbar :title="route.meta.title" @toggle-sidebar="appStore.toggleSidebar" />
      <main class="app-shell__main">
        <AppBreadcrumbs :section="route.meta.section" :title="route.meta.title" />
        <RouterView />
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
import { RouterView, useRoute } from "vue-router";
import AppBreadcrumbs from "@/components/layout/AppBreadcrumbs.vue";
import AppSidebar from "@/components/layout/AppSidebar.vue";
import AppTopbar from "@/components/layout/AppTopbar.vue";
import { useAppStore } from "@/stores/app";

const route = useRoute();
const appStore = useAppStore();
</script>
