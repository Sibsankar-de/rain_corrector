/** Map layer toggles, district quick-jump, and severity filters. */

import { formatDateTime } from "@/lib/format";
import { SEVERITY_STYLES, SEVERITY_ORDER } from "@/lib/severity";
import type { DistrictSummary, ForecastRun } from "@/types/api";
import { Layers, Search, SlidersHorizontal, X } from "lucide-react";

export interface MapControlsProps {
  showStations: boolean;
  onToggleStations: (value: boolean) => void;
  showStationsLayer: boolean;
  onToggleStationsLayer: (value: boolean) => void;
  activeSeverities: Set<string>;
  onToggleSeverity: (severity: string) => void;
  runs: ForecastRun[];
  selectedRunUid?: string;
  onSelectRun: (runUid: string | undefined) => void;
  disabled?: boolean;
  districts?: DistrictSummary[];
  selectedDistrictId?: number;
  onSelectDistrict?: (districtId: number | undefined) => void;
  onCloseMobile?: () => void;
}

function Toggle({
  checked,
  onChange,
  label,
  disabled
}: {
  checked: boolean;
  onChange: (value: boolean) => void;
  label: string;
  disabled?: boolean;
}) {
  return (
    <label
      className={`flex items-center gap-2 text-2xs font-medium text-slate-700 transition ${
        disabled ? "opacity-50 cursor-not-allowed" : "cursor-pointer hover:text-slate-900"
      }`}
    >
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(event) => onChange(event.target.checked)}
        className="h-3.5 w-3.5 rounded border-slate-300 text-brand-700 focus:ring-brand-500 cursor-pointer"
      />
      {label}
    </label>
  );
}

export function MapControls({
  showStations,
  onToggleStations,
  showStationsLayer,
  onToggleStationsLayer,
  activeSeverities,
  onToggleSeverity,
  runs,
  selectedRunUid,
  onSelectRun,
  disabled = false,
  districts = [],
  selectedDistrictId,
  onSelectDistrict,
  onCloseMobile
}: MapControlsProps) {
  return (
    <div className="space-y-3.5 rounded-xl border border-edge bg-surface-raised/95 p-3.5 shadow-md backdrop-blur-md">
      <div className="flex items-center justify-between border-b border-edge/80 pb-2">
        <div className="flex items-center gap-1.5 text-xs font-semibold text-ink">
          <SlidersHorizontal className="h-3.5 w-3.5 text-brand-600" />
          <span>Map Controls</span>
        </div>
        {onCloseMobile ? (
          <button
            type="button"
            onClick={onCloseMobile}
            className="sm:hidden rounded p-1 text-ink-muted hover:bg-surface-sunken"
            aria-label="Close controls"
          >
            <X className="h-4 w-4" />
          </button>
        ) : null}
      </div>

      {/* District Jump Selector */}
      {districts.length > 0 && onSelectDistrict ? (
        <div>
          <label htmlFor="map-district-select" className="data-label mb-1 flex items-center gap-1">
            <Search className="h-3 w-3 text-ink-faint" />
            Jump to District
          </label>
          <select
            id="map-district-select"
            value={selectedDistrictId ?? ""}
            disabled={disabled}
            onChange={(event) => {
              const val = event.target.value ? Number(event.target.value) : undefined;
              onSelectDistrict(val);
            }}
            className="w-full rounded-lg border border-edge bg-surface-raised px-2.5 py-1.5 text-xs text-ink focus:border-brand-500 focus:ring-1 focus:ring-brand-500 disabled:opacity-50"
          >
            <option value="">Select a district…</option>
            {districts.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name} ({d.code})
              </option>
            ))}
          </select>
        </div>
      ) : null}

      {/* Forecast Run Selector */}
      <div>
        <label htmlFor="map-run-select" className="data-label mb-1 block">
          Forecast Run Issuance
        </label>
        <select
          id="map-run-select"
          value={selectedRunUid ?? ""}
          disabled={disabled || runs.length === 0}
          onChange={(event) => onSelectRun(event.target.value || undefined)}
          className="w-full rounded-lg border border-edge bg-surface-raised px-2.5 py-1.5 text-xs text-ink focus:border-brand-500 focus:ring-1 focus:ring-brand-500 disabled:opacity-50 font-mono"
        >
          <option value="">Latest Run (Default)</option>
          {runs.map((run) => (
            <option key={run.run_uid} value={run.run_uid}>
              {formatDateTime(run.issued_at)}
            </option>
          ))}
        </select>
      </div>

      {/* Layers */}
      <div className="space-y-2 border-t border-edge/80 pt-2.5">
        <p className="data-label flex items-center gap-1">
          <Layers className="h-3 w-3 text-ink-faint" />
          Map Layers
        </p>
        <div className="space-y-1.5 pl-0.5">
          <Toggle
            checked={showStations}
            onChange={onToggleStations}
            label="Show district forecast markers"
            disabled={disabled}
          />
          <Toggle
            checked={showStationsLayer}
            onChange={onToggleStationsLayer}
            label="Show rain telemetry stations"
            disabled={disabled}
          />
        </div>
      </div>

      {/* Severity Filter */}
      <div className="border-t border-edge/80 pt-2.5">
        <p className="data-label mb-1.5">Severity Filter</p>
        <div className="flex flex-wrap gap-1">
          {SEVERITY_ORDER.map((severity) => {
            const style = SEVERITY_STYLES[severity];
            const active = activeSeverities.has(severity);
            return (
              <button
                key={severity}
                type="button"
                disabled={disabled}
                aria-pressed={active}
                onClick={() => onToggleSeverity(severity)}
                className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-2xs font-medium transition disabled:opacity-50 ${
                  active
                    ? style.badgeClass
                    : "border-edge bg-surface-raised text-ink-faint opacity-60"
                }`}
              >
                <span className={`h-1.5 w-1.5 rounded-full ${style.dotClass}`} aria-hidden="true" />
                {style.label}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
