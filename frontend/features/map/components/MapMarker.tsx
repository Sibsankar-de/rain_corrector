/** District marker coloured by forecast severity with operational styling. */

import { CircleMarker, Popup, Tooltip } from "react-leaflet";

import { formatDateTime, formatMillimetres } from "@/lib/format";
import { severityStyle } from "@/lib/severity";
import type { Forecast } from "@/types/api";

export interface MapMarkerProps {
  forecast: Forecast;
  selected?: boolean;
  onSelect?: (forecast: Forecast) => void;
}

const HIT_RADIUS: Record<string, number> = {
  none: 6,
  light: 7,
  moderate: 9,
  heavy: 11,
  very_heavy: 13,
  extreme: 15
};

export function MapMarker({ forecast, selected = false, onSelect }: MapMarkerProps) {
  const district = forecast.district;
  if (!district) return null;

  const style = severityStyle(forecast.severity);
  const position: [number, number] = [district.centroid_lat, district.centroid_lon];
  const baseRadius = HIT_RADIUS[forecast.severity] ?? 9;
  const radius = baseRadius + (selected ? 4 : 0);
  const isHighRisk = ["heavy", "very_heavy", "extreme"].includes(forecast.severity);

  return (
    <>
      {/* High-risk or selected outer halo */}
      {(isHighRisk || selected) && (
        <CircleMarker
          center={position}
          radius={radius + (selected ? 6 : 4)}
          pathOptions={{
            color: selected ? "#1e293b" : style.color,
            weight: selected ? 2 : 1,
            fillColor: style.color,
            fillOpacity: selected ? 0.35 : 0.2,
            dashArray: selected ? "3, 3" : undefined
          }}
          interactive={false}
        />
      )}

      {/* Main interactive marker */}
      <CircleMarker
        center={position}
        radius={radius}
        pathOptions={{
          color: selected ? "#0f172a" : "#ffffff",
          weight: selected ? 2.5 : 1.5,
          fillColor: style.color,
          fillOpacity: 0.95
        }}
        eventHandlers={
          onSelect
            ? {
                click: (e) => {
                  e.originalEvent?.stopPropagation();
                  onSelect(forecast);
                }
              }
            : undefined
        }
      >
        <Tooltip direction="top" offset={[0, -radius]} opacity={0.95}>
          <div className="font-sans px-1 py-0.5 text-xs">
            <span className="font-semibold text-slate-900">{district.name}</span>
            <span className="mx-1 text-slate-400">·</span>
            <span className="font-mono font-medium text-slate-800">
              {formatMillimetres(forecast.predicted_rainfall_mm)}
            </span>
            <span className="mx-1 text-slate-400">·</span>
            <span className="font-medium" style={{ color: style.color }}>
              {style.label}
            </span>
          </div>
        </Tooltip>

        <Popup>
          <div className="min-w-60 p-3.5 text-slate-800">
            <div className="flex items-start justify-between gap-2 border-b border-slate-100 pb-2">
              <div>
                <p className="text-sm font-bold text-slate-900">{district.name}</p>
                <p className="font-mono text-2xs text-slate-500">
                  Code: {district.code} · {district.centroid_lat.toFixed(3)}°N,{" "}
                  {district.centroid_lon.toFixed(3)}°E
                </p>
              </div>
              <span
                className="inline-flex rounded-full px-2 py-0.5 text-2xs font-semibold"
                style={{
                  backgroundColor: `${style.color}20`,
                  color: style.color,
                  border: `1px solid ${style.color}40`
                }}
              >
                {style.label}
              </span>
            </div>

            <dl className="mt-2.5 space-y-1.5 text-xs">
              <div className="flex items-baseline justify-between gap-3">
                <dt className="text-slate-500">Predicted 24h Rainfall</dt>
                <dd className="font-mono text-base font-bold tabular-nums text-slate-900">
                  {formatMillimetres(forecast.predicted_rainfall_mm)}
                </dd>
              </div>

              {forecast.lower_bound_mm !== null && forecast.upper_bound_mm !== null ? (
                <div className="flex items-baseline justify-between gap-3">
                  <dt className="text-slate-500">Confidence Band (P10–P90)</dt>
                  <dd className="font-mono text-xs tabular-nums text-slate-700">
                    {formatMillimetres(forecast.lower_bound_mm)} –{" "}
                    {formatMillimetres(forecast.upper_bound_mm)}
                  </dd>
                </div>
              ) : null}

              {forecast.predicted_probability !== null ? (
                <div className="flex items-baseline justify-between gap-3">
                  <dt className="text-slate-500">Rain Probability</dt>
                  <dd className="font-mono text-xs tabular-nums text-slate-700">
                    {(forecast.predicted_probability * 100).toFixed(0)}%
                  </dd>
                </div>
              ) : null}

              <div className="flex items-baseline justify-between gap-3 pt-1 border-t border-slate-100">
                <dt className="text-slate-500">Target Valid Until</dt>
                <dd className="font-mono text-2xs text-slate-600">
                  {formatDateTime(forecast.target_time)}
                </dd>
              </div>

              <div className="flex items-baseline justify-between gap-3">
                <dt className="text-slate-500">Active ML Model</dt>
                <dd className="font-mono text-2xs font-semibold text-brand-700">
                  {forecast.model_version}
                </dd>
              </div>
            </dl>
          </div>
        </Popup>
      </CircleMarker>
    </>
  );
}
