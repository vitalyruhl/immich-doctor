<template>
  <aside class="app-sidebar" :class="{ 'app-sidebar--collapsed': collapsed }">
    <div class="app-sidebar__brand">
      <div class="app-sidebar__logo">ID</div>
      <div v-if="!collapsed">
        <strong>immich-doctor</strong>
        <p>Operational UI</p>
      </div>
    </div>

    <nav class="app-sidebar__nav" aria-label="Primary">
      <RouterLink
        v-for="item in NAVIGATION_ITEMS"
        :key="item.label"
        class="app-sidebar__link"
        :class="{ 'is-active': isActive(item.to.name) }"
        :aria-label="collapsed ? item.label : undefined"
        :to="item.to"
        :title="collapsed ? item.label : undefined"
      >
        <i :class="item.icon" />
        <div v-if="!collapsed">
          <span>{{ item.label }}</span>
          <small>{{ item.description }}</small>
        </div>
      </RouterLink>
    </nav>
  </aside>
</template>

<script setup lang="ts">
import { RouterLink, useRoute } from "vue-router";
import { NAVIGATION_ITEMS } from "@/constants/navigation";

const route = useRoute();

defineProps<{
  collapsed: boolean;
}>();

function isActive(routeName: string): boolean {
  const currentRouteName = String(route.name ?? "");
  if (routeName === "consistency" && currentRouteName.startsWith("consistency")) {
    return true;
  }
  return routeName === currentRouteName;
}
</script>
