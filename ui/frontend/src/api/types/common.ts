export type HealthState = "ok" | "warning" | "error" | "unknown";

export interface ApiErrorPayload {
  code: string;
  message: string;
  details?: string;
  status?: number;
}

export interface ApiResponse<TData> {
  data: TData;
  source: "backend" | "mock";
  mocked: boolean;
}
