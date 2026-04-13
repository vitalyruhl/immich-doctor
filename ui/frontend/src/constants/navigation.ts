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
    label: "Empty Folders",
    icon: "pi pi-folder-open",
    to: { name: "storage-empty-folders" },
    description: "Detect empty directories and quarantine them safely.",
  },
  {
    label: "Consistency",
    icon: "pi pi-check-square",
    to: { name: "consistency" },
    description: "Category-first consistency validation and repair.",
  },
  {
    label: "Quarantine",
    icon: "pi pi-inbox",
    to: { name: "consistency-quarantine" },
    description: "Review quarantined consistency findings.",
  },
  {
    label: "Ignored",
    icon: "pi pi-eye-slash",
    to: { name: "consistency-ignored" },
    description: "Manage findings hidden from the active view.",
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
