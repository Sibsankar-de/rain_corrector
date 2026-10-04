/**
 * Centralised API client.
 *
 * Every network call in the application goes through `apiClient.request`.
 * Features never call `fetch` directly, which keeps error normalisation,
 * timeouts, auth headers and query serialisation in one place.
 */

import { config } from "@/lib/config";
import { apiErrorEnvelopeSchema } from "@/lib/schemas";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: unknown;
  readonly requestId: string | null;

  constructor(
    status: number,
    code: string,
    message: string,
    details: unknown,
    requestId: string | null
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
    this.requestId = requestId;
  }

  get isNotFound(): boolean {
    return this.status === 404;
  }

  get isValidationError(): boolean {
    return this.status === 422;
  }

  get isUnavailable(): boolean {
    return this.status === 503;
  }

  /** Message safe to show a user: the API never returns a stack trace. */
  get userMessage(): string {
    return this.message;
  }
}

export type QueryValue = string | number | boolean | null | undefined | (string | number)[];

export interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  query?: Record<string, QueryValue>;
  body?: unknown;
  signal?: AbortSignal;
  timeoutMs?: number;
  apiKey?: string;
}

const DEFAULT_TIMEOUT_MS = 20_000;

function buildUrl(path: string, query?: Record<string, QueryValue>): string {
  const base = config.apiBaseUrl.replace(/\/$/, "");
  const suffix = path.startsWith("/") ? path : `/${path}`;
  const url = new URL(`${base}${suffix}`);

  for (const [key, value] of Object.entries(query ?? {})) {
    if (value === undefined || value === null || value === "") continue;
    if (Array.isArray(value)) {
      for (const entry of value) {
        url.searchParams.append(key, String(entry));
      }
    } else {
      url.searchParams.set(key, String(value));
    }
  }
  return url.toString();
}

function buildHeaders(options: RequestOptions): Headers {
  const headers = new Headers({ Accept: "application/json" });
  if (options.body !== undefined) headers.set("Content-Type", "application/json");
  if (options.apiKey) headers.set("X-API-Key", options.apiKey);
  return headers;
}

function toApiError(status: number, payload: unknown, fallback: string): ApiError {
  const parsed = apiErrorEnvelopeSchema.safeParse(payload);
  if (parsed.success) {
    return new ApiError(
      status,
      parsed.data.error.code,
      parsed.data.error.message,
      parsed.data.error.details ?? null,
      parsed.data.request_id ?? null
    );
  }
  return new ApiError(status, "unknown_error", fallback, null, null);
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), options.timeoutMs ?? DEFAULT_TIMEOUT_MS);

  if (options.signal) {
    if (options.signal.aborted) controller.abort();
    else options.signal.addEventListener("abort", () => controller.abort(), { once: true });
  }

  try {
    const response = await fetch(buildUrl(path, options.query), {
      method: options.method ?? "GET",
      headers: buildHeaders(options),
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: controller.signal
    });

    const payload: unknown = await response.json().catch(() => null);

    if (!response.ok) {
      throw toApiError(
        response.status,
        payload,
        `Request to ${path} failed with ${response.status}.`
      );
    }
    return payload as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiError(408, "request_timeout", "The request to the API timed out.", null, null);
    }
    throw new ApiError(
      0,
      "network_error",
      "Could not reach the Rain Corrector API. Check that the backend is running.",
      null,
      null
    );
  } finally {
    clearTimeout(timeout);
  }
}

export const apiClient = {
  get: <T>(path: string, options: Omit<RequestOptions, "method" | "body"> = {}) =>
    request<T>(path, { ...options, method: "GET" }),
  post: <T>(path: string, body?: unknown, options: Omit<RequestOptions, "method"> = {}) =>
    request<T>(path, { ...options, method: "POST", body }),
  patch: <T>(path: string, body?: unknown, options: Omit<RequestOptions, "method"> = {}) =>
    request<T>(path, { ...options, method: "PATCH", body })
};

export type ApiClient = typeof apiClient;
