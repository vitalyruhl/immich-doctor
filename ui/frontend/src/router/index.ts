import { createRouter, createWebHistory, type RouteRecordRaw } from "vue-router";
import BackupView from "@/views/backup/BackupView.vue";
import ConsistencyIgnoredView from "@/views/consistency/ConsistencyIgnoredView.vue";
import ConsistencyQuarantineView from "@/views/consistency/ConsistencyQuarantineView.vue";
import ConsistencyView from "@/views/consistency/ConsistencyView.vue";
import DashboardView from "@/views/dashboard/DashboardView.vue";
import DatabaseView from "@/views/database/DatabaseView.vue";
import ReportsView from "@/views/reports/ReportsView.vue";
import RuntimeView from "@/views/runtime/RuntimeView.vue";
import SettingsView from "@/views/settings/SettingsView.vue";
import StorageEmptyFoldersQuarantineView from "@/views/storage/StorageEmptyFoldersQuarantineView.vue";
import StorageEmptyFoldersView from "@/views/storage/StorageEmptyFoldersView.vue";
import StorageView from "@/views/storage/StorageView.vue";

declare module "vue-router" {
  interface RouteMeta {
    title: string;
    section: string;
    risk?: "read-only" | "mixed" | "mutation";
  }
}

const routes: RouteRecordRaw[] = [
  { path: "/", redirect: { name: "dashboard" } },
  {
    path: "/dashboard",
    name: "dashboard",
    component: DashboardView,
    meta: { title: "Dashboard", section: "Overview", risk: "read-only" },
  },
  {
    path: "/runtime",
    name: "runtime",
    component: RuntimeView,
    meta: { title: "Runtime / Health", section: "Runtime", risk: "read-only" },
  },
  {
    path: "/database",
    name: "database",
    component: DatabaseView,
    meta: { title: "Database", section: "Database", risk: "read-only" },
  },
  {
    path: "/storage",
    name: "storage",
    component: StorageView,
    meta: { title: "Storage", section: "Storage", risk: "mixed" },
  },
  {
    path: "/storage/empty-folders",
    name: "storage-empty-folders",
    component: StorageEmptyFoldersView,
    meta: { title: "Empty Folders", section: "Storage", risk: "mixed" },
  },
  {
    path: "/storage/quarantine",
    name: "storage-empty-folders-quarantine",
    component: StorageEmptyFoldersQuarantineView,
    meta: { title: "Storage Quarantine", section: "Storage", risk: "mutation" },
  },
  {
    path: "/consistency",
    name: "consistency",
    component: ConsistencyView,
    meta: { title: "Consistency", section: "Consistency", risk: "mixed" },
  },
  {
    path: "/consistency/quarantine",
    name: "consistency-quarantine",
    component: ConsistencyQuarantineView,
    meta: { title: "Quarantine", section: "Consistency", risk: "mutation" },
  },
  {
    path: "/consistency/ignored",
    name: "consistency-ignored",
    component: ConsistencyIgnoredView,
    meta: { title: "Ignored Findings", section: "Consistency", risk: "mixed" },
  },
  {
    path: "/backup",
    name: "backup",
    component: BackupView,
    meta: { title: "Backup", section: "Backup", risk: "mixed" },
  },
  {
    path: "/reports",
    name: "reports",
    component: ReportsView,
    meta: { title: "Reports / Logs", section: "Reports", risk: "read-only" },
  },
  {
    path: "/settings",
    name: "settings",
    component: SettingsView,
    meta: { title: "Settings", section: "Settings", risk: "read-only" },
  },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

export default router;
