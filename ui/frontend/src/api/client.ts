import type { ApiErrorPayload, ApiResponse } from "./types/common";

export class ApiClientError extends Error {
  public readonly payload: ApiErrorPayload;

  public constructor(payload: ApiErrorPayload) {
    super(payload.message);
    this.payload = payload;
  }
}

const DEFAULT_TIMEOUT_MS = 8000;

export async function request<TData>(
  path: string,
  init?: RequestInit,
  timeoutMs = DEFAULT_TIMEOUT_MS,
): Promise<ApiResponse<TData>> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  const baseUrl = import.meta.env.VITE_API_BASE_URL?.trim() || "/api";

  try {
    const response = await fetch(`${baseUrl}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(init?.headers ?? {}),
      },
      signal: controller.signal,
    });

    if (!response.ok) {
      throw new ApiClientError({
        code: "http_error",
        message: `Request failed with status ${response.status}.`,
        status: response.status,
      });
    }

    return (await response.json()) as ApiResponse<TData>;
  } catch (error) {
    if (error instanceof ApiClientError) {
      throw error;
    }

    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiClientError({
        code: "timeout",
        message: "Request timed out.",
      });
    }

    throw new ApiClientError({
      code: "network_error",
      message: "Request failed.",
      details: error instanceof Error ? error.message : String(error),
    });
  } finally {
    window.clearTimeout(timeout);
  }
}
