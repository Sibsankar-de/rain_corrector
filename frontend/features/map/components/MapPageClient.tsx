"use client";

/**
 * Full-screen interactive map page with operational telemetry notes and geodetic inspection hints.
 */

import dynamic from "next/dynamic";
import { Info, MapPin, Radio, ShieldCheck } from "lucide-react";

const MapView = dynamic(() => import("./MapView").then((module) => module.MapView), {
  ssr: false,
  loading: () => (
    <div className="card flex h-[36rem] items-center justify-center text-sm text-ink-muted bg-surface-sunken/40">
      <div className="flex items-center gap-2">
        <span className="h-4 w-4 animate-spin rounded-full border-2 border-brand-600 border-t-transparent" />
        <span>Initializing Hydrometeorological Map…</span>
      </div>
    </div>
  )
});

export function MapPageClient() {
  return (
    <div className="space-y-4">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 border-b border-edge pb-3">
        <div>
          <h1 className="text-lg font-bold tracking-tight text-ink sm:text-xl">
            Interactive Precipitation Map
          </h1>
          <p className="text-xs text-ink-muted">
            Geospatial hydrometeorology, quantile forecast bands, telemetry gauge stations & coordinate inspection
          </p>
        </div>

        <div className="flex items-center gap-2">
          <span className="inline-flex items-center gap-1.5 rounded-full border border-sky-200 bg-sky-50 px-2.5 py-1 text-2xs font-semibold text-sky-800">
            <Radio className="h-3 w-3 text-sky-600 animate-pulse" />
            25 Districts · 75 Gauge Stations
          </span>
        </div>
      </div>

      {/* Main Map View */}
      <MapView className="h-[32rem] sm:h-[38rem] lg:h-[42rem] shadow-sm" />

      {/* Operational Instructions & Metadata Footer */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <div className="card p-3 bg-surface-raised/80">
          <div className="flex items-center gap-2 text-xs font-semibold text-ink">
            <CrosshairIcon className="h-4 w-4 text-brand-600" />
            <span>Click-Anywhere Inspection</span>
          </div>
          <p className="mt-1 text-2xs text-ink-muted">
            Tap or click anywhere on the map canvas to calculate distance to the nearest monitored district, fetch its latest ML rainfall forecast, and locate the closest gauge telemetry station.
          </p>
        </div>

        <div className="card p-3 bg-surface-raised/80">
          <div className="flex items-center gap-2 text-xs font-semibold text-ink">
            <MapPin className="h-4 w-4 text-emerald-600" />
            <span>Complete Basin Coverage</span>
          </div>
          <p className="mt-1 text-2xs text-ink-muted">
            Displays all monitored district centroids across Maharashtra. Color-coded circular bands show IMD severity categories from Light (&lt;2.5mm) to Extreme (&gt;15.6mm).
          </p>
        </div>

        <div className="card p-3 bg-surface-raised/80 sm:col-span-2 lg:col-span-1">
          <div className="flex items-center gap-2 text-xs font-semibold text-ink">
            <Info className="h-4 w-4 text-sky-600" />
            <span>Cartographic Attribution</span>
          </div>
          <p className="mt-1 text-2xs text-ink-muted">
            Map tiles served by OpenStreetMap. All predictions driven by the active registered hydrometeorological correction model version.
          </p>
        </div>
      </div>
    </div>
  );
}

function CrosshairIcon({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none" stroke="currentColor" strokeWidth="2">
      <circle cx="12" cy="12" r="8" />
      <line x1="12" y1="2" x2="12" y2="6" />
      <line x1="12" y1="18" x2="12" y2="22" />
      <line x1="2" y1="12" x2="6" y2="12" />
      <line x1="18" y1="12" x2="22" y2="12" />
    </svg>
  );
}
