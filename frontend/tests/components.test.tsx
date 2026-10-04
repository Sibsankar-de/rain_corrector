import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";

import type { LegendEntry } from "@/types/api";

import { createQueryClient } from "@/lib/query-client";

const originalFetch = globalThis.fetch;

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" }
  });
}

function renderWithQuery(ui: ReactNode) {
  const client = createQueryClient();
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

const legend: LegendEntry[] = [
  { label: "light", severity: "light", color: "#60a5fa", min_mm: 0.1, max_mm: 2.5 },
  { label: "moderate", severity: "moderate", color: "#2563eb", min_mm: 2.5, max_mm: 7.6 },
  { label: "heavy", severity: "heavy", color: "#7c3aed", min_mm: 7.6, max_mm: 15.6 }
];

async function importMapComponents() {
  const [legendModule, markerModule, pageModule] = await Promise.all([
    import("@/features/map/components/MapLegend"),
    import("@/features/map/components/MapMarker"),
    import("@/components/DateRangeSelector")
  ]);
  return { legendModule, markerModule, pageModule };
}

describe("MapLegend", () => {
  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it("renders one row per severity band from the API legend", async () => {
    const { legendModule } = await importMapComponents();
    renderWithQuery(<legendModule.MapLegend entries={legend} />);

    expect(await screen.findByText("Light")).toBeDefined();
    expect(screen.getByText("Moderate")).toBeDefined();
    expect(screen.getByText("Heavy")).toBeDefined();
    expect(screen.getByText("0.1 mm – 2.5 mm")).toBeDefined();
  });

  it("reports toggles for a severity the user clicks", async () => {
    const { legendModule } = await importMapComponents();
    const onToggle = vi.fn();
    renderWithQuery(<legendModule.MapLegend entries={legend} onToggle={onToggle} />);

    await userEvent.click(await screen.findByRole("button", { name: /heavy/i }));
    expect(onToggle).toHaveBeenCalledWith("heavy");
  });

  it("dims severity bands that are filtered off", async () => {
    const { legendModule } = await importMapComponents();
    renderWithQuery(
      <legendModule.MapLegend
        entries={legend}
        activeSeverities={new Set(["light"])}
        onToggle={() => {}}
      />
    );

    const lightButton = await screen.findByRole("button", { name: /light/i });
    const heavyButton = screen.getByRole("button", { name: /heavy/i });

    expect(lightButton.getAttribute("aria-pressed")).toBe("true");
    expect(heavyButton.getAttribute("aria-pressed")).toBe("false");
  });
});

describe("DataTablePagination", () => {
  it("disables previous on the first page and next on the last", async () => {
    const { DataTablePagination } = await import("@/components/DataTablePagination");
    const onPageChange = vi.fn();

    renderWithQuery(
      <DataTablePagination
        page={1}
        pageSize={20}
        total={45}
        totalPages={3}
        onPageChange={onPageChange}
      />
    );

    const previous = screen.getByRole("button", { name: "Previous" }) as HTMLButtonElement;
    const next = screen.getByRole("button", { name: "Next" }) as HTMLButtonElement;

    expect(previous.disabled).toBe(true);
    expect(next.disabled).toBe(false);
    expect(screen.getByText("1–20 of 45")).toBeDefined();

    await userEvent.click(next);
    expect(onPageChange).toHaveBeenCalledWith(2);
  });

  it("reports a zero row count plainly", async () => {
    const { DataTablePagination } = await import("@/components/DataTablePagination");
    renderWithQuery(
      <DataTablePagination
        page={1}
        pageSize={20}
        total={0}
        totalPages={0}
        onPageChange={() => {}}
      />
    );
    expect(screen.getByText("No rows")).toBeDefined();
  });
});

describe("DateRangeSelector", () => {
  it("emits the new range when a preset is chosen", async () => {
    const { pageModule } = await importMapComponents();
    const onChange = vi.fn();
    const today = new Date().toISOString().slice(0, 10);

    renderWithQuery(
      <pageModule.DateRangeSelector
        start="2026-01-01"
        end="2026-01-31"
        onChange={onChange}
        presets={[{ label: "7d", days: 7 }]}
      />
    );

    const sevenDays = new Date();
    sevenDays.setUTCDate(sevenDays.getUTCDate() - 7);

    await userEvent.click(screen.getByRole("button", { name: "7d" }));
    expect(onChange).toHaveBeenCalledWith({
      start: sevenDays.toISOString().slice(0, 10),
      end: today
    });
  });
});

describe("ApiError surfacing", () => {
  it("shows the API message and request id in an error state", async () => {
    const { ErrorState } = await import("@/components/states");
    const { ApiError } = await import("@/services/api-client");

    renderWithQuery(
      <ErrorState
        error={new ApiError(503, "model_unavailable", "No model is loaded.", null, "req-xyz")}
        title="Unable to load data"
      />
    );

    expect(screen.getByRole("alert")).toBeDefined();
    expect(screen.getByText("No model is loaded.")).toBeDefined();
    expect(screen.getByText(/req-xyz/)).toBeDefined();
  });
});

describe("DashboardStatusSummary", () => {
  it("renders counters and reflects the loaded model", async () => {
    const { StatusSummary } = await import("@/features/dashboard/components/StatusSummary");

    renderWithQuery(
      <StatusSummary
        data={{
          generated_at: "2026-09-28T00:00:00Z",
          active_model_version: "v002",
          model_loaded_version: "v001",
          latest_forecast_run: "fr_v001_20260928T0000Z",
          latest_forecast_issued_at: "2026-09-28T00:00:00Z",
          status: {
            forecasts_issued: 10,
            forecasts_verified: 8,
            forecasts_pending: 2,
            latest_observation: "2026-09-27T00:00:00Z",
            evaluated_at: "2026-09-28T00:00:00Z"
          },
          summary: {
            forecasts_last_7d: 10,
            districts_at_risk: 1,
            open_alerts: 1,
            observed_rainfall_mm_7d: 120
          },
          verification: {
            sample_size: 8,
            mean_error_mm: 1,
            mean_absolute_error_mm: 4.2,
            rmse_mm: 6,
            bias_mm: 0.5,
            nash_sutcliffe: 0.2,
            brier_score: 0.3,
            hit_rate: 0.8,
            false_alarm_ratio: 0.1,
            detection_score: 0.7,
            critical_success_index: 0.6,
            by_lead_bucket: {},
            by_severity: {},
            computed_at: "2026-09-28T00:00:00Z"
          },
          severity_distribution: [],
          top_risk_districts: [],
          observed_rainfall_series: [],
          forecast_vs_observed_series: [],
          alerts: [],
          legend,
          models: [],
          meta: {}
        }}
      />
    );

    expect(screen.getByText("Active model")).toBeDefined();
    expect(screen.getByText("v002")).toBeDefined();
    // Mismatch between the registered and loaded versions must be visible.
    expect(screen.getByText("Registry holds v001")).toBeDefined();
    expect(screen.getByText("4.2 mm")).toBeDefined();
  });
});

describe("api integration", () => {
  it("fetches the dashboard overview through the service layer", async () => {
    globalThis.fetch = vi.fn(() =>
      Promise.resolve(jsonResponse({ generated_at: "2026-09-28T00:00:00Z", summary: {} }))
    ) as unknown as typeof fetch;

    const { dashboardService } = await import("@/services/dashboard-service");
    const overview = await dashboardService.overview(14);

    const called = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
    const url = new URL(called.mock.calls[0]![0] as string);
    expect(url.pathname).toContain("/dashboard/overview");
    expect(url.searchParams.get("lookback_days")).toBe("14");
    await waitFor(() => expect(overview.generated_at).toBe("2026-09-28T00:00:00Z"));
  });
});

describe("InspectorCard", () => {
  const sampleDistrict = {
    id: 4,
    code: "MH-NAS",
    name: "Nashik",
    region_id: 1,
    centroid_lat: 20.011,
    centroid_lon: 73.79,
    population: 6107187
  };

  const sampleStation = {
    id: 10,
    code: "ST-NAS-1",
    name: "Nashik Telemetry Station",
    district_id: 4,
    latitude: 20.0,
    longitude: 73.8,
    elevation_m: 560,
    is_active: true
  };

  const sampleForecast = {
    id: 754,
    run_id: 31,
    district_id: 4,
    target_time: "2025-12-30T00:00:00Z",
    lead_time_hours: 24,
    predicted_rainfall_mm: 14.6,
    predicted_probability: 0.85,
    lower_bound_mm: 10.2,
    upper_bound_mm: 19.5,
    severity: "heavy" as const,
    status: "issued" as const,
    issued_at: "2025-12-29T00:00:00Z",
    model_version: "v005",
    district: sampleDistrict
  };

  it("renders rainfall prediction, confidence interval, and model version", async () => {
    const { InspectorCard } = await import("@/features/map/components/MapView");
    render(
      <InspectorCard
        data={{
          clickedLat: 20.015,
          clickedLon: 73.795,
          nearestDistrict: sampleDistrict,
          distanceDistrictKm: 0.8,
          nearestStation: sampleStation,
          distanceStationKm: 2.1,
          forecast: sampleForecast,
          isLoadingForecast: false
        }}
        onClose={() => {}}
        onFocusDistrict={() => {}}
      />
    );

    expect(screen.getByText("Nashik")).toBeDefined();
    expect(screen.getByText("(MH-NAS)")).toBeDefined();
    expect(screen.getByText("14.6 mm")).toBeDefined();
    expect(screen.getByText(/10.2 mm – 19.5 mm/)).toBeDefined();
    expect(screen.getByText("v005")).toBeDefined();
    expect(screen.getByText("Heavy")).toBeDefined();
    expect(screen.getByText(/0.8 km away/)).toBeDefined();
    expect(screen.getByText("Nashik Telemetry Station")).toBeDefined();
  });

  it("renders loading indicator when prediction is being fetched", async () => {
    const { InspectorCard } = await import("@/features/map/components/MapView");
    render(
      <InspectorCard
        data={{
          clickedLat: 20.015,
          clickedLon: 73.795,
          nearestDistrict: sampleDistrict,
          distanceDistrictKm: 0.8,
          nearestStation: null,
          distanceStationKm: null,
          forecast: null,
          isLoadingForecast: true
        }}
        onClose={() => {}}
        onFocusDistrict={() => {}}
      />
    );

    expect(screen.getByText(/Fetching latest forecast for Nashik/)).toBeDefined();
  });

  it("renders fallback message when no forecast is available", async () => {
    const { InspectorCard } = await import("@/features/map/components/MapView");
    render(
      <InspectorCard
        data={{
          clickedLat: 20.015,
          clickedLon: 73.795,
          nearestDistrict: sampleDistrict,
          distanceDistrictKm: 0.8,
          nearestStation: null,
          distanceStationKm: null,
          forecast: null,
          isLoadingForecast: false
        }}
        onClose={() => {}}
        onFocusDistrict={() => {}}
      />
    );

    expect(
      screen.getByText("No active forecast recorded for this district in selected run.")
    ).toBeDefined();
  });
});
