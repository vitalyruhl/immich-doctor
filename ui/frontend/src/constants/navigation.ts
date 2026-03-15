export interface NavigationItem {
  label: string;
  icon: string;
  to: {
    name: string;
  };
  description: string;
}

export const NAVIGATION_ITEMS: NavigationItem[] = [
  {
    label: "Dashboard",
    icon: "pi pi-home",
    to: { name: "dashboard" },
    description: "Operational overview and safety posture.",
  },
  {
    label: "Runtime / Health",
    icon: "pi pi-heart",
    to: { name: "runtime" },
    description: "Runtime readiness and health checks.",
  },
  {
    label: "Consistency",
    icon: "pi pi-check-square",
    to: { name: "consistency" },
    description: "Category-first consistency validation and repair.",
  },
  {
    label: "Database",
    icon: "pi pi-database",
    to: { name: "database" },
    description: "Database diagnostics and performance checks.",
  },
  {
    label: "Storage",
    icon: "pi pi-folder",
    to: { name: "storage" },
    description: "Storage paths, mounts, and readiness.",
  },
  {
    label: "Backup",
    icon: "pi pi-box",
    to: { name: "backup" },
    description: "Backup workflows and target readiness.",
  },
  {
    label: "Reports / Logs",
    icon: "pi pi-file",
    to: { name: "reports" },
    description: "Operation reports, downloadable logs, and history.",
  },
  {
    label: "Settings",
    icon: "pi pi-cog",
    to: { name: "settings" },
    description: "Operational configuration placeholders.",
  },
];
