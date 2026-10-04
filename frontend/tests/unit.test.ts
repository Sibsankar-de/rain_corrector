import { describe, expect, it } from "vitest";

import { ApiError } from "@/services/api-client";
import { buildMapOverlay, summariseOverlay } from "@/features/map/utils/overlay";
import { formatDateTime, formatMillimetres, formatRelativeTime, toIsoDate } from "@/lib/format";
import { severityStyle } from "@/lib/severity";
import { config } from "@/lib/config";
import type { Forecast, LegendEntry, Station } from "@/types/api";

function forecast(overrides: Partial<Forecast> = {}): Forecast {
  return {
    id: 1,
    run_id: 1,
    district_id: 1,
    target_time: "2026-09-28T00:00:00Z",
    lead_time_hours: 24,
    predicted_rainfall_mm: 5,
    predicted_probability: null,
    lower_bound_mm: 0,
    upper_bound_mm: 10,
    severity: "moderate",
    status: "issued",
    issued_at: "2026-09-27T00:00:00Z",
    model_version: "v001",
    district: {
      id: 1,
      code: "MH-MUM",
      name: "Mumbai Suburban",
      region_id: 1,
      centroid_lat: 19.2183,
      centroid_lon: 72.9781,
      population: 2_335_000
    },
    ...overrides
  };
}

const legend: LegendEntry[] = [
  { label: "light", severity: "light", color: "#60a5fa", min_mm: 0.1, max_mm: 2.5 },
  { label: "moderate", severity: "moderate", color: "#2563eb", min_mm: 2.5, max_mm: 7.6 },
  { label: "heavy", severity: "heavy", color: "#7c3aed", min_mm: 7.6, max_mm: 15.6 }
];

const stations: Station[] = [
  {
    id: 1,
    code: "MH-MUM-ST01",
    name: "Mumbai Gauge 1",
    district_id: 1,
    latitude: 19.2,
    longitude: 72.98,
    elevation_m: 12,
    is_active: true
  }
];

describe("api-client error surface", () => {
  it("classifies a 404 and exposes the request id for support", () => {
    const error = new ApiError(404, "not_found", "Forecast 1 does not exist.", null, "req-123");

    expect(error.isNotFound).toBe(true);
    expect(error.userMessage).toBe("Forecast 1 does not exist.");
    expect(error.requestId).toBe("req-123");
  });

  it("does not treat a 422 as retryable", () => {
    const error = new ApiError(422, "validation_error", "bad page size", null, null);
    expect(error.isValidationError).toBe(true);
    expect(error.isUnavailable).toBe(false);
  });
});

describe("buildMapOverlay", () => {
  const base = {
    forecasts: [
      forecast({ id: 1, severity: "light", predicted_rainfall_mm: 1 }),
      forecast({ id: 2, severity: "moderate", predicted_rainfall_mm: 4 }),
      forecast({ id: 3, severity: "heavy", predicted_rainfall_mm: 12 })
    ],
    stations,
    legend,
    showForecasts: true,
    showStations: false,
    activeSeverities: new Set(["light", "moderate", "heavy"]),
    minRainfallMm: 0
  };

  it("returns every marker when nothing is filtered", () => {
    const overlay = buildMapOverlay(base);
    expect(overlay.markers).toHaveLength(3);
    expect(overlay.hiddenBySeverity).toBe(0);
  });

  it("drops markers whose severity is toggled off", () => {
    const overlay = buildMapOverlay({ ...base, activeSeverities: new Set(["heavy"]) });
    expect(overlay.markers.map((m) => m.id)).toEqual([3]);
    expect(overlay.hiddenBySeverity).toBe(2);
  });

  it("applies the rainfall threshold and reports how many it hid", () => {
    const overlay = buildMapOverlay({ ...base, minRainfallMm: 10 });
    expect(overlay.markers.map((m) => m.id)).toEqual([3]);
    expect(overlay.hiddenByThreshold).toBe(2);
  });

  it("honours the layer toggles independently", () => {
    const noForecasts = buildMapOverlay({ ...base, showForecasts: false, showStations: true });
    expect(noForecasts.markers).toHaveLength(0);
    expect(noForecasts.stationMarkers).toHaveLength(1);
  });

  it("paints small light markers last so they stay clickable under heavy neighbours", () => {
    const overlay = buildMapOverlay(base);
    expect(overlay.markers.map((m) => m.severity)).toEqual(["heavy", "moderate", "light"]);
  });
});

describe("summariseOverlay", () => {
  it("returns zeros for an empty overlay rather than NaN", () => {
    expect(summariseOverlay([])).toEqual({
      visibleDistricts: 0,
      maxRainfallMm: 0,
      meanRainfallMm: 0,
      heavyOrWorse: 0
    });
  });

  it("computes mean, peak and heavy counts", () => {
    const summary = summariseOverlay([
      forecast({ predicted_rainfall_mm: 4, severity: "moderate" }),
      forecast({ predicted_rainfall_mm: 20, severity: "extreme" })
    ]);
    expect(summary.visibleDistricts).toBe(2);
    expect(summary.maxRainfallMm).toBe(20);
    expect(summary.meanRainfallMm).toBe(12);
    expect(summary.heavyOrWorse).toBe(1);
  });
});

describe("formatters", () => {
  it("renders a dash for missing values instead of NaN", () => {
    expect(formatMillimetres(null)).toBe("—");
    expect(formatMillimetres(undefined)).toBe("—");
    expect(formatDateTime(null)).toBe("—");
    expect(formatDateTime("not-a-date")).toBe("—");
  });

  it("formats millimetres with one decimal", () => {
    expect(formatMillimetres(12.34)).toBe("12.3 mm");
  });

  it("formats relative time against an injected reference", () => {
    const now = new Date("2026-09-28T12:00:00Z");
    expect(formatRelativeTime("2026-09-28T11:00:00Z", now)).toContain("hour");
    expect(formatRelativeTime("2026-09-25T12:00:00Z", now)).toContain("day");
  });

  it("serialises dates as ISO calendar days in UTC", () => {
    expect(toIsoDate(new Date("2026-09-28T23:30:00Z"))).toBe("2026-09-28");
  });
});

describe("severityStyle", () => {
  it("returns a style for every known severity", () => {
    expect(severityStyle("heavy").label).toBe("Heavy");
    expect(severityStyle("extreme").color).toBe("#b91c1c");
  });

  it("falls back safely for an unknown or missing severity", () => {
    expect(severityStyle(null).label).toBe("Unknown");
    expect(severityStyle("meteor-shower").label).toBe("Unknown");
  });
});

describe("map configuration", () => {
  it("uses OpenStreetMap tiles by default with no API key", () => {
    expect(config.map.tileUrl).toContain("openstreetmap.org");
    expect(config.map.attribution).toContain("OpenStreetMap");
  });
});
