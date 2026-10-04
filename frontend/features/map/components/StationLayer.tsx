/** Hydrological and telemetry station layer with distinct telemetry markers. */

import { CircleMarker, Popup, Tooltip } from "react-leaflet";

import type { Station } from "@/types/api";

export interface StationLayerProps {
  stations: Station[];
  onSelectStation?: (station: Station) => void;
}

export function StationLayer({ stations, onSelectStation }: StationLayerProps) {
  return (
    <>
      {stations.map((station) => (
        <CircleMarker
          key={station.id}
          center={[station.latitude, station.longitude]}
          radius={4}
          pathOptions={{
            color: "#1e3a8a",
            weight: 1.5,
            fillColor: "#38bdf8",
            fillOpacity: 0.95
          }}
          eventHandlers={
            onSelectStation
              ? {
                  click: (e) => {
                    e.originalEvent?.stopPropagation();
                    onSelectStation(station);
                  }
                }
              : undefined
          }
        >
          <Tooltip direction="top" offset={[0, -5]}>
            <div className="font-sans text-2xs">
              <span className="font-semibold text-slate-900">{station.name}</span>
              <span className="mx-1 text-slate-400">·</span>
              <span className="font-mono text-slate-600">{station.code}</span>
            </div>
          </Tooltip>

          <Popup>
            <div className="min-w-48 p-2.5 text-slate-800 text-xs">
              <p className="font-bold text-slate-900">{station.name}</p>
              <p className="font-mono text-2xs text-slate-500 mt-0.5">{station.code}</p>
              <div className="mt-2 space-y-1 border-t border-slate-100 pt-2 text-2xs">
                <div className="flex justify-between">
                  <span className="text-slate-500">Elevation</span>
                  <span className="font-mono font-medium">{station.elevation_m ?? "—"} m</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Coordinates</span>
                  <span className="font-mono font-medium">
                    {station.latitude.toFixed(3)}°N, {station.longitude.toFixed(3)}°E
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Telemetry Status</span>
                  <span className="font-semibold text-emerald-600">Active</span>
                </div>
              </div>
            </div>
          </Popup>
        </CircleMarker>
      ))}
    </>
  );
}
