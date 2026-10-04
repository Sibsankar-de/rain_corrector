/** Client-side filtering and sorting for map overlays. */

import { useMemo } from "react";

import { SEVERITY_ORDER } from "@/lib/severity";
import type { Forecast, LegendEntry, Severity, Station } from "@/types/api";

export interface MapOverlayOptions {
  forecasts: Forecast[];
  stations: Station[];
  legend: LegendEntry[];
  showForecasts: boolean;
  showStations: boolean;
  activeSeverities: Set<string>;
  minRainfallMm: number;
}

export interface MapOverlay {
  markers: Forecast[];
  stationMarkers: Station[];
  legend: LegendEntry[];
  hiddenBySeverity: number;
  hiddenByThreshold: number;
}

/**
 * The legend defines the colour scale, so filtering uses it as the source of
 * truth rather than a duplicated list of severities in the client.
 */
export function buildMapOverlay(options: MapOverlayOptions): MapOverlay {
  const { forecasts, legend, activeSeverities, minRainfallMm } = options;

  const filtered = forecasts.filter((forecast) => {
    if (!activeSeverities.has(forecast.severity)) return false;
    if (forecast.predicted_rainfall_mm < minRainfallMm) return false;
    return true;
  });

  // Leaflet paints in insertion order, so the smallest markers (light rainfall)
  // are appended last and stay clickable instead of being buried under a
  // heavy-rain district next to them.
  const sorted = [...filtered].sort(
    (a, b) =>
      severityRank(b.severity) - severityRank(a.severity) ||
      b.predicted_rainfall_mm - a.predicted_rainfall_mm
  );

  return {
    markers: options.showForecasts ? sorted : [],
    stationMarkers: options.showStations ? options.stations : [],
    legend,
    hiddenBySeverity:
      forecasts.length - forecasts.filter((f) => activeSeverities.has(f.severity)).length,
    hiddenByThreshold:
      forecasts.filter((f) => activeSeverities.has(f.severity)).length - filtered.length
  };
}

function severityRank(severity: Severity): number {
  const index = SEVERITY_ORDER.indexOf(severity);
  return index === -1 ? SEVERITY_ORDER.length : index;
}

export function useMapOverlay(options: MapOverlayOptions): MapOverlay {
  return useMemo(() => buildMapOverlay(options), [options]);
}

export interface MapSummary {
  visibleDistricts: number;
  maxRainfallMm: number;
  meanRainfallMm: number;
  heavyOrWorse: number;
}

export function summariseOverlay(markers: Forecast[]): MapSummary {
  if (markers.length === 0) {
    return { visibleDistricts: 0, maxRainfallMm: 0, meanRainfallMm: 0, heavyOrWorse: 0 };
  }
  const values = markers.map((m) => m.predicted_rainfall_mm);
  return {
    visibleDistricts: markers.length,
    maxRainfallMm: Math.max(...values),
    meanRainfallMm: values.reduce((total, value) => total + value, 0) / values.length,
    heavyOrWorse: markers.filter((m) => ["heavy", "very_heavy", "extreme"].includes(m.severity))
      .length
  };
}
