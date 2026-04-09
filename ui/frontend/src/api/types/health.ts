import type { HealthState } from "./common";

export type HealthSource = "immich" | "db" | "storage" | "backup" | "runtime" | "consistency";

export interface HealthItem {
  id: string;
  title: string;
  status: HealthState;
  summary: string;
  details: string;
  updatedAt: string;
  blocking: boolean;
  source: HealthSource | string;
}

export interface HealthOverviewResponse {
  generatedAt: string;
  overallStatus: HealthState;
  items: HealthItem[];
}
