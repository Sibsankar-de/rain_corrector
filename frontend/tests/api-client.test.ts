import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, request } from "@/services/api-client";

const originalFetch = globalThis.fetch;

function mockFetch(response: Response | (() => Response | Promise<Response>)) {
  const impl = typeof response === "function" ? response : () => Promise.resolve(response);
  globalThis.fetch = vi.fn(impl) as unknown as typeof fetch;
}

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" }
  });
}

describe("request", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it("returns the parsed body on success", async () => {
    mockFetch(jsonResponse(200, { status: "ok" }));
    await expect(request<{ status: string }>("/health")).resolves.toEqual({ status: "ok" });
  });

  it("turns a structured error envelope into an ApiError", async () => {
    const envelope = {
      error: { code: "not_found", message: "Forecast 7 does not exist.", details: null },
      request_id: "abc123",
      timestamp: "2026-09-28T00:00:00Z"
    };
    // A Response body is single-use, so each call needs a fresh instance.
    mockFetch(() => jsonResponse(404, envelope));

    await expect(request("/forecasts/7")).rejects.toBeInstanceOf(ApiError);
    await expect(request("/forecasts/7")).rejects.toMatchObject({
      status: 404,
      code: "not_found",
      message: "Forecast 7 does not exist.",
      requestId: "abc123"
    });
  });

  it("falls back to a generic error when the body is not an envelope", async () => {
    mockFetch(new Response("<html>gateway</html>", { status: 502 }));
    await expect(request("/forecasts")).rejects.toMatchObject({
      status: 502,
      code: "unknown_error"
    });
  });

  it("reports a network failure as code network_error with status 0", async () => {
    mockFetch(() => Promise.reject(new TypeError("Failed to fetch")));
    await expect(request("/health")).rejects.toMatchObject({ code: "network_error", status: 0 });
  });

  it("serialises array query parameters as repeated keys", async () => {
    mockFetch(jsonResponse(200, { items: [], meta: {} }));
    await request("/forecasts", { query: { district_id: [1, 2], page: 1 } });

    const called = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
    const url = new URL(called.mock.calls[0]![0] as string);
    expect(url.searchParams.getAll("district_id")).toEqual(["1", "2"]);
    expect(url.searchParams.get("page")).toBe("1");
  });

  it("omits empty query values instead of sending blanks", async () => {
    mockFetch(jsonResponse(200, { items: [], meta: {} }));
    await request("/forecasts", { query: { severity: "", region_id: undefined, min_lat: null } });

    const called = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
    const url = new URL(called.mock.calls[0]![0] as string);
    expect([...url.searchParams.keys()]).toHaveLength(0);
  });

  it("sends the API key header when supplied", async () => {
    mockFetch(jsonResponse(200, {}));
    await request("/models/promote", { method: "POST", body: {}, apiKey: "rck_secret" });

    const called = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
    const init = called.mock.calls[0]![1] as RequestInit;
    expect((init.headers as Headers).get("X-API-Key")).toBe("rck_secret");
    expect((init.headers as Headers).get("Content-Type")).toBe("application/json");
  });
});
