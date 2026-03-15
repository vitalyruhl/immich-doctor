import type { HealthState } from "./common";

export interface HealthItem {
  id: string;
  title: string;
  status: HealthState;
  summary: string;
  details: string;
  updatedAt: string;
  blocking: boolean;
  source: string;
}

export interface HealthOverviewResponse {
  items: HealthItem[];
  mocked: boolean;
}
