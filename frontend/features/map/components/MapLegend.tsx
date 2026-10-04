/** Legend for the rainfall severity scale, driven by the API legend endpoint. */

import { formatMillimetres } from "@/lib/format";
import { SEVERITY_STYLES } from "@/lib/severity";
import type { LegendEntry } from "@/types/api";

export interface MapLegendProps {
  entries: LegendEntry[];
  activeSeverities?: Set<string>;
  onToggle?: (severity: string) => void;
  className?: string;
}

function bandLabel(entry: LegendEntry): string {
  if (entry.max_mm === null) return `≥ ${formatMillimetres(entry.min_mm)}`;
  return `${formatMillimetres(entry.min_mm)} – ${formatMillimetres(entry.max_mm)}`;
}

export function MapLegend({ entries, activeSeverities, onToggle, className = "" }: MapLegendProps) {
  return (
    <div
      className={`rounded-card border border-edge bg-surface-raised/95 p-3 shadow-sm backdrop-blur ${className}`}
    >
      <p className="data-label mb-2">Predicted 24h rainfall</p>
      <ul className="space-y-1">
        {entries.map((entry) => {
          const interactive = Boolean(onToggle);
          const active = activeSeverities ? activeSeverities.has(entry.severity) : true;
          const style = SEVERITY_STYLES[entry.severity];
          const content = (
            <>
              <span
                className="mt-0.5 h-2.5 w-6 shrink-0 rounded-sm"
                style={{ backgroundColor: entry.color }}
                aria-hidden="true"
              />
              <span className="min-w-0 flex-1 truncate font-medium text-ink">
                {style?.label ?? entry.label}
              </span>
              <span className="font-mono text-2xs tabular-nums text-ink-muted">
                {bandLabel(entry)}
              </span>
            </>
          );

          return (
            <li key={entry.severity}>
              {interactive ? (
                <button
                  type="button"
                  onClick={() => onToggle?.(entry.severity)}
                  aria-pressed={active}
                  className={`flex w-full items-center gap-2 rounded px-1.5 py-1 text-left text-2xs transition hover:bg-surface-sunken ${
                    active ? "opacity-100" : "opacity-40"
                  }`}
                >
                  {content}
                </button>
              ) : (
                <div className="flex items-center gap-2 px-1.5 py-1 text-2xs">{content}</div>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
