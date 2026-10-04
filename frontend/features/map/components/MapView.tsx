"use client";

/**
 * Interactive forecast map with coordinate-based inspection,
 * complete location plotting, nearest-district lookup, and responsive mobile controls.
 */

import { useEffect, useMemo, useState } from "react";
import { CircleMarker, Tooltip, useMap, useMapEvents } from "react-leaflet";
import {
  Crosshair,
  Filter,
  Layers,
  MapPin,
  Radio,
  SlidersHorizontal,
  X,
  CloudRain,
  Navigation,
  Compass
} from "lucide-react";

import { ErrorState, LoadingState } from "@/components/states";
import { formatCoordinates, haversineDistanceKm } from "@/lib/geo";
import { formatDateTime, formatMillimetres } from "@/lib/format";
import { SEVERITY_ORDER, severityStyle } from "@/lib/severity";
import { forecastService } from "@/services";
import type { DistrictSummary, Forecast, Station } from "@/types/api";

import { BaseMap } from "./BaseMap";
import { MapControls } from "./MapControls";
import { MapLegend } from "./MapLegend";
import { MapMarker } from "./MapMarker";
import { StationLayer } from "./StationLayer";
import {
  useAllDistricts,
  useForecastRuns,
  useMapForecasts,
  useSeverityLegend,
  useStations
} from "../hooks/useMapData";
import { summariseOverlay, useMapOverlay } from "../utils/overlay";

const EMPTY_SEVERITIES = new Set<string>(SEVERITY_ORDER);

export interface InspectionData {
  clickedLat: number;
  clickedLon: number;
  nearestDistrict: DistrictSummary | null;
  distanceDistrictKm: number | null;
  nearestStation: Station | null;
  distanceStationKm: number | null;
  forecast: Forecast | null;
  isLoadingForecast?: boolean;
}

export function MapView({ className = "" }: { className?: string }) {
  const [runUid, setRunUid] = useState<string | undefined>(undefined);
  const [minRainfallMm, setMinRainfallMm] = useState(0);
  const [showForecasts, setShowForecasts] = useState(true);
  const [showStationsLayer, setShowStationsLayer] = useState(false);
  const [showAllDistricts, setShowAllDistricts] = useState(true);
  const [activeSeverities, setActiveSeverities] = useState<Set<string>>(EMPTY_SEVERITIES);
  const [inspection, setInspection] = useState<InspectionData | null>(null);
  const [focusCenter, setFocusCenter] = useState<[number, number] | null>(null);

  // Mobile drawer controls
  const [showMobileControls, setShowMobileControls] = useState(false);
  const [showMobileLegend, setShowMobileLegend] = useState(false);

  const forecastsQuery = useMapForecasts({ runUid });
  const runsQuery = useForecastRuns(20);
  const legendQuery = useSeverityLegend();
  const stationsQuery = useStations();
  const allDistrictsQuery = useAllDistricts();

  const allDistricts = allDistrictsQuery.data ?? [];
  const allStations = stationsQuery.data ?? [];
  const forecasts = forecastsQuery.data ?? [];

  const overlayOptions = useMemo(
    () => ({
      forecasts,
      stations: allStations,
      legend: legendQuery.data ?? [],
      showForecasts,
      showStations: showStationsLayer,
      activeSeverities,
      minRainfallMm
    }),
    [forecasts, allStations, legendQuery.data, showForecasts, showStationsLayer, activeSeverities, minRainfallMm]
  );

  const overlay = useMapOverlay(overlayOptions);
  const summary = summariseOverlay(overlay.markers);
  const isLoading = forecastsQuery.isLoading || legendQuery.isLoading;
  const error = forecastsQuery.error ?? legendQuery.error;

  // Set of district IDs that already have a forecast marker visible in this run
  const forecastedDistrictIds = useMemo(
    () => new Set(overlay.markers.map((m) => m.district?.id).filter(Boolean)),
    [overlay.markers]
  );

  // Remaining districts without active forecast overlay (for complete location plotting)
  const nonForecastedDistricts = useMemo(() => {
    if (!showAllDistricts) return [];
    return allDistricts.filter((d) => !forecastedDistrictIds.has(d.id));
  }, [allDistricts, forecastedDistrictIds, showAllDistricts]);

  const toggleSeverity = (severity: string) => {
    setActiveSeverities((current) => {
      const next = new Set(current);
      if (next.has(severity)) next.delete(severity);
      else next.add(severity);
      return next.size === 0 ? EMPTY_SEVERITIES : next;
    });
  };

  /** Handles arbitrary map canvas click to inspect nearest locations */
  const handleMapClick = async (lat: number, lon: number) => {
    // 1. Candidate pool: allDistricts first, then fallback to district objects in forecasts
    const districtPool =
      allDistricts.length > 0
        ? allDistricts
        : forecasts.map((f) => f.district).filter((d): d is DistrictSummary => Boolean(d));

    // Find nearest district
    let nearestDistrict: DistrictSummary | null = null;
    let minDistrictDist = Infinity;

    for (const d of districtPool) {
      const dist = haversineDistanceKm(lat, lon, d.centroid_lat, d.centroid_lon);
      if (dist < minDistrictDist) {
        minDistrictDist = dist;
        nearestDistrict = d;
      }
    }

    // 2. Find matching forecast for nearest district in current in-memory forecasts
    let matchingForecast: Forecast | null = null;
    if (nearestDistrict) {
      matchingForecast =
        forecasts.find(
          (f) => f.district_id === nearestDistrict!.id || f.district?.id === nearestDistrict!.id
        ) ?? null;
    }

    // 3. Find nearest station
    let nearestStation: Station | null = null;
    let minStationDist = Infinity;

    for (const s of allStations) {
      const dist = haversineDistanceKm(lat, lon, s.latitude, s.longitude);
      if (dist < minStationDist) {
        minStationDist = dist;
        nearestStation = s;
      }
    }

    const needsFetch = Boolean(nearestDistrict && !matchingForecast);

    setInspection({
      clickedLat: lat,
      clickedLon: lon,
      nearestDistrict,
      distanceDistrictKm: nearestDistrict ? minDistrictDist : null,
      nearestStation,
      distanceStationKm: nearestStation ? minStationDist : null,
      forecast: matchingForecast,
      isLoadingForecast: needsFetch
    });

    if (needsFetch && nearestDistrict) {
      try {
        const res = await forecastService.list({ districtId: [nearestDistrict.id], pageSize: 1 });
        const fetched = res.items?.[0] ?? null;
        setInspection((current) => {
          if (!current || current.nearestDistrict?.id !== nearestDistrict!.id) return current;
          return {
            ...current,
            forecast: fetched,
            isLoadingForecast: false
          };
        });
      } catch {
        setInspection((current) => {
          if (!current || current.nearestDistrict?.id !== nearestDistrict!.id) return current;
          return {
            ...current,
            isLoadingForecast: false
          };
        });
      }
    }
  };

  /** Directly select a forecast from its marker */
  const handleSelectForecast = (forecast: Forecast) => {
    if (!forecast.district) return;
    const lat = forecast.district.centroid_lat;
    const lon = forecast.district.centroid_lon;

    // Find nearest station
    let nearestStation: Station | null = null;
    let minStationDist = Infinity;
    for (const s of allStations) {
      const dist = haversineDistanceKm(lat, lon, s.latitude, s.longitude);
      if (dist < minStationDist) {
        minStationDist = dist;
        nearestStation = s;
      }
    }

    setInspection({
      clickedLat: lat,
      clickedLon: lon,
      nearestDistrict: forecast.district,
      distanceDistrictKm: 0,
      nearestStation,
      distanceStationKm: nearestStation ? minStationDist : null,
      forecast
    });
    setFocusCenter([lat, lon]);
  };

  /** Quick jump from district dropdown */
  const handleJumpToDistrict = (districtId: number | undefined) => {
    if (!districtId) return;
    const district = allDistricts.find((d) => d.id === districtId);
    if (!district) return;

    const lat = district.centroid_lat;
    const lon = district.centroid_lon;
    const forecast =
      forecasts.find((f) => f.district_id === districtId || f.district?.id === districtId) ?? null;

    handleMapClick(lat, lon);
    setFocusCenter([lat, lon]);
  };

  return (
    <div className={`card flex flex-col overflow-hidden ${className}`}>
      {/* Header Bar */}
      <header className="card-header bg-surface-raised">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h2 className="card-title">Precipitation & Telemetry Map</h2>
            <span className="inline-flex items-center rounded-md border border-edge bg-surface-sunken px-2 py-0.5 text-2xs font-mono font-medium text-ink-muted">
              {allDistricts.length} Monitored Districts
            </span>
          </div>
          <p className="mt-0.5 text-xs text-ink-muted truncate">
            {isLoading
              ? "Loading hydrometeorological layer…"
              : `${summary.visibleDistricts} districts visible · mean ${summary.meanRainfallMm.toFixed(1)} mm · peak ${summary.maxRainfallMm.toFixed(1)} mm`}
          </p>
        </div>

        {/* Desktop Quick Controls */}
        <div className="flex items-center gap-2 sm:gap-3">
          <label className="hidden sm:flex items-center gap-2 text-2xs text-ink-muted">
            <span className="font-medium">Min rainfall</span>
            <input
              type="number"
              min={0}
              step={0.5}
              value={minRainfallMm}
              onChange={(event) => setMinRainfallMm(Math.max(0, Number(event.target.value) || 0))}
              className="w-16 rounded-md border border-edge bg-surface px-2 py-1 font-mono text-2xs text-ink"
              aria-label="Minimum predicted rainfall in millimetres"
            />
            <span>mm</span>
          </label>

          {/* Mobile Buttons */}
          <button
            type="button"
            onClick={() => setShowMobileControls((v) => !v)}
            className="sm:hidden btn-secondary py-1 px-2.5 text-2xs"
            aria-label="Toggle map controls"
          >
            <SlidersHorizontal className="h-3.5 w-3.5 text-brand-600" />
            <span>Controls</span>
          </button>

          <button
            type="button"
            onClick={() => setShowMobileLegend((v) => !v)}
            className="sm:hidden btn-secondary py-1 px-2.5 text-2xs"
            aria-label="Toggle map legend"
          >
            <Layers className="h-3.5 w-3.5 text-brand-600" />
            <span>Legend</span>
          </button>
        </div>
      </header>

      {/* Main Map Container */}
      {error ? (
        <ErrorState error={error} onRetry={() => forecastsQuery.refetch()} />
      ) : (
        <div className="relative h-[28rem] sm:h-[32rem] lg:h-[36rem] w-full">
          <BaseMap className="h-full w-full rounded-none border-0" ariaLabel="District rainfall forecast map">
            <MapCanvasListener onClick={handleMapClick} />
            <MapFlyTo center={focusCenter} />

            {/* Telemetry stations layer */}
            {showStationsLayer ? (
              <StationLayer
                stations={overlay.stationMarkers}
                onSelectStation={(s) => handleMapClick(s.latitude, s.longitude)}
              />
            ) : null}

            {/* Non-forecasted districts layer (plots ALL locations in region) */}
            {nonForecastedDistricts.map((d) => (
              <CircleMarker
                key={`district-${d.id}`}
                center={[d.centroid_lat, d.centroid_lon]}
                radius={5}
                pathOptions={{
                  color: "#64748b",
                  weight: 1.5,
                  fillColor: "#cbd5e1",
                  fillOpacity: 0.75
                }}
                eventHandlers={{
                  click: (e) => {
                    e.originalEvent?.stopPropagation();
                    handleMapClick(d.centroid_lat, d.centroid_lon);
                  }
                }}
              >
                <Tooltip direction="top" offset={[0, -5]}>
                  <span className="font-sans text-xs">
                    {d.name} ({d.code}) · Monitored District
                  </span>
                </Tooltip>
              </CircleMarker>
            ))}

            {/* Active forecast district markers */}
            {overlay.markers.map((forecast) => (
              <MapMarker
                key={forecast.id}
                forecast={forecast}
                selected={inspection?.forecast?.id === forecast.id}
                onSelect={handleSelectForecast}
              />
            ))}

            {/* Click Inspection Target Crosshair */}
            {inspection ? (
              <CircleMarker
                center={[inspection.clickedLat, inspection.clickedLon]}
                radius={8}
                pathOptions={{
                  color: "#0f172a",
                  weight: 2,
                  fillColor: "#f59e0b",
                  fillOpacity: 0.9,
                  dashArray: "3, 3"
                }}
                interactive={false}
              >
                <Tooltip permanent direction="top" offset={[0, -9]} opacity={0.95}>
                  <div className="font-mono text-2xs font-semibold text-slate-900 bg-white/95 px-1 py-0.5 rounded shadow-sm">
                    Target Pin
                  </div>
                </Tooltip>
              </CircleMarker>
            ) : null}
          </BaseMap>

          {/* Loading overlay */}
          {isLoading ? (
            <div className="absolute inset-0 z-[500] flex items-center justify-center bg-surface-raised/70 backdrop-blur-sm">
              <LoadingState label="Preparing map telemetry…" />
            </div>
          ) : null}

          {/* Desktop Floating Legend (or Mobile toggled) */}
          <div
            className={`absolute left-3 top-3 z-[400] transition ${
              showMobileLegend ? "block" : "hidden sm:block"
            }`}
          >
            <div className="relative">
              <MapLegend
                entries={overlay.legend}
                activeSeverities={activeSeverities}
                onToggle={toggleSeverity}
                className="w-48 sm:w-52"
              />
              {showMobileLegend ? (
                <button
                  type="button"
                  onClick={() => setShowMobileLegend(false)}
                  className="sm:hidden absolute top-2 right-2 rounded p-1 text-ink-faint hover:text-ink"
                  aria-label="Close legend"
                >
                  <X className="h-4 w-4" />
                </button>
              ) : null}
            </div>
          </div>

          {/* Desktop Floating Controls (or Mobile toggled) */}
          <div
            className={`absolute right-3 top-3 z-[400] transition ${
              showMobileControls ? "block" : "hidden sm:block"
            }`}
          >
            <div className="w-64 sm:w-60">
              <MapControls
                showStations={showForecasts}
                onToggleStations={setShowForecasts}
                showStationsLayer={showStationsLayer}
                onToggleStationsLayer={setShowStationsLayer}
                activeSeverities={activeSeverities}
                onToggleSeverity={toggleSeverity}
                runs={runsQuery.data?.items ?? []}
                selectedRunUid={runUid}
                onSelectRun={(value: string | undefined) => {
                  setRunUid(value);
                  setInspection(null);
                }}
                disabled={isLoading}
                districts={allDistricts}
                selectedDistrictId={inspection?.nearestDistrict?.id}
                onSelectDistrict={handleJumpToDistrict}
                onCloseMobile={() => setShowMobileControls(false)}
              />
            </div>
          </div>

          {/* Click Anywhere Inspection Card / Bottom Sheet */}
          {inspection ? (
            <div className="absolute bottom-3 left-3 right-3 sm:right-auto z-[450] sm:w-80">
              <InspectorCard
                data={inspection}
                onClose={() => setInspection(null)}
                onFocusDistrict={() => {
                  if (inspection.nearestDistrict) {
                    setFocusCenter([
                      inspection.nearestDistrict.centroid_lat,
                      inspection.nearestDistrict.centroid_lon
                    ]);
                  }
                }}
              />
            </div>
          ) : null}
        </div>
      )}
    </div>
  );
}

/** Handles map panning to given coordinates smoothly */
function MapFlyTo({ center }: { center: [number, number] | null }) {
  const map = useMap();
  useEffect(() => {
    if (center) {
      map.flyTo(center, Math.max(map.getZoom(), 8), { duration: 1 });
    }
  }, [center, map]);
  return null;
}

/** Listens to user clicks anywhere on map canvas */
function MapCanvasListener({ onClick }: { onClick: (lat: number, lon: number) => void }) {
  useMapEvents({
    click: (event) => {
      onClick(event.latlng.lat, event.latlng.lng);
    }
  });
  return null;
}

/** Rich Inspector Card showing details of clicked coordinate or nearest district */
export function InspectorCard({
  data,
  onClose,
  onFocusDistrict
}: {
  data: InspectionData;
  onClose: () => void;
  onFocusDistrict: () => void;
}) {
  const {
    clickedLat,
    clickedLon,
    nearestDistrict,
    distanceDistrictKm,
    nearestStation,
    distanceStationKm,
    forecast
  } = data;

  const style = forecast ? severityStyle(forecast.severity) : null;

  return (
    <div className="rounded-xl border border-edge bg-surface-raised/98 p-3.5 shadow-lg backdrop-blur-md transition">
      {/* Header */}
      <div className="flex items-start justify-between gap-2 border-b border-edge/80 pb-2">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5">
            <MapPin className="h-4 w-4 text-brand-700 shrink-0" />
            <p className="truncate text-sm font-bold text-ink">
              {nearestDistrict ? nearestDistrict.name : "Location Details"}
            </p>
            {nearestDistrict ? (
              <span className="font-mono text-2xs text-ink-faint">({nearestDistrict.code})</span>
            ) : null}
          </div>
          <p className="font-mono text-[11px] text-ink-muted">
            Clicked: {formatCoordinates(clickedLat, clickedLon)}
          </p>
        </div>

        <button
          type="button"
          onClick={onClose}
          aria-label="Close district details"
          className="rounded-lg p-1 text-ink-faint hover:bg-surface-sunken hover:text-ink transition"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* Body details */}
      <div className="mt-2.5 space-y-2 text-xs">
        {/* Distance readout */}
        {distanceDistrictKm !== null && distanceDistrictKm > 0.5 ? (
          <div className="flex items-center justify-between text-2xs text-ink-muted bg-surface-sunken/60 px-2 py-1 rounded">
            <span>Nearest district center</span>
            <span className="font-mono font-semibold text-ink">
              {distanceDistrictKm.toFixed(1)} km away
            </span>
          </div>
        ) : null}

        {/* Forecast readout if available */}
        {data.isLoadingForecast ? (
          <div className="flex items-center justify-center gap-2 rounded-lg border border-edge/80 bg-surface-sunken/40 py-3 px-2 text-2xs text-ink-muted">
            <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-brand-600 border-t-transparent" />
            <span>Fetching latest forecast for {nearestDistrict?.name}…</span>
          </div>
        ) : forecast ? (
          <div className="space-y-1.5 rounded-lg border border-edge/80 bg-surface-sunken/40 p-2.5">
            <div className="flex items-baseline justify-between">
              <span className="text-2xs font-semibold uppercase tracking-wider text-ink-faint">
                24h Predicted Rainfall
              </span>
              {style ? (
                <span
                  className="rounded-full px-2 py-0.5 text-2xs font-bold"
                  style={{
                    backgroundColor: `${style.color}20`,
                    color: style.color,
                    border: `1px solid ${style.color}40`
                  }}
                >
                  {style.label}
                </span>
              ) : null}
            </div>

            <p className="font-mono text-xl font-bold tabular-nums text-ink">
              {formatMillimetres(forecast.predicted_rainfall_mm)}
            </p>

            {forecast.lower_bound_mm !== null && forecast.upper_bound_mm !== null ? (
              <div className="flex items-center justify-between text-2xs text-ink-muted">
                <span>Confidence (P10–P90)</span>
                <span className="font-mono text-ink font-medium">
                  {formatMillimetres(forecast.lower_bound_mm)} –{" "}
                  {formatMillimetres(forecast.upper_bound_mm)}
                </span>
              </div>
            ) : null}

            <div className="flex items-center justify-between text-2xs text-ink-muted pt-1 border-t border-edge/60">
              <span>Model Version</span>
              <span className="font-mono text-brand-700 font-semibold">
                {forecast.model_version}
              </span>
            </div>
          </div>
        ) : (
          <p className="text-2xs text-ink-faint italic py-1">
            No active forecast recorded for this district in selected run.
          </p>
        )}

        {/* Nearest telemetry station */}
        {nearestStation ? (
          <div className="flex items-center justify-between text-2xs text-ink-muted border-t border-edge/80 pt-1.5">
            <div className="flex items-center gap-1">
              <Radio className="h-3 w-3 text-sky-600" />
              <span className="truncate max-w-[150px]">{nearestStation.name}</span>
            </div>
            <span className="font-mono">
              {distanceStationKm !== null ? `~${distanceStationKm.toFixed(1)} km` : ""}
            </span>
          </div>
        ) : null}

        {/* Actions */}
        {nearestDistrict ? (
          <div className="pt-1">
            <button
              type="button"
              onClick={onFocusDistrict}
              className="btn-secondary w-full py-1 text-2xs justify-center"
            >
              <Navigation className="h-3 w-3 text-brand-600" />
              <span>Center Map on {nearestDistrict.name}</span>
            </button>
          </div>
        ) : null}
      </div>
    </div>
  );
}
