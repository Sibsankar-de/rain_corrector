/** Districts with the highest forecast rainfall in the latest run. */

import { DashboardCard } from "@/components/DashboardCard";
import { EmptyState } from "@/components/states";
import { SeverityBadge } from "@/components/SeverityBadge";
import { formatDateTime, formatMillimetres } from "@/lib/format";
import type { DistrictRiskItem } from "@/types/api";

export interface TopRiskDistrictsProps {
  districts: DistrictRiskItem[];
  onSelect?: (district: DistrictRiskItem) => void;
}

export function TopRiskDistricts({ districts, onSelect }: TopRiskDistrictsProps) {
  const maxRain = districts.length > 0 ? Math.max(...districts.map((d) => d.predicted_rainfall_mm), 1) : 1;

  return (
    <DashboardCard
      title="Districts with the highest forecast"
      description="Latest issuance, ordered by predicted 24h accumulation"
      bodyClassName="p-0"
    >
      {districts.length === 0 ? (
        <EmptyState
          title="No forecasts issued"
          description="Generate a forecast run to populate this list."
        />
      ) : (
        <ul className="divide-y divide-edge">
          {districts.map((district, idx) => {
            const pct = Math.min(100, Math.round((district.predicted_rainfall_mm / maxRain) * 100));
            return (
              <li key={district.district_id}>
                <button
                  type="button"
                  onClick={() => onSelect?.(district)}
                  disabled={!onSelect}
                  className="group flex w-full items-center justify-between gap-3 px-4 py-2.5 text-left transition hover:bg-surface-sunken disabled:cursor-default disabled:hover:bg-transparent"
                >
                  <div className="flex items-center gap-2.5 min-w-0">
                    <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-md bg-surface-sunken font-mono text-2xs font-semibold text-ink-muted">
                      {idx + 1}
                    </span>
                    <div className="min-w-0">
                      <p className="truncate text-xs font-semibold text-ink group-hover:text-brand-800">
                        {district.name}
                      </p>
                      <p className="font-mono text-2xs text-ink-faint">
                        {district.code} · {formatDateTime(district.target_time)}
                      </p>
                    </div>
                  </div>

                  <div className="flex shrink-0 items-center gap-2.5">
                    <div className="text-right">
                      <span className="font-mono text-xs font-bold tabular-nums text-ink">
                        {formatMillimetres(district.predicted_rainfall_mm)}
                      </span>
                      <div className="mt-0.5 h-1 w-14 overflow-hidden rounded-full bg-slate-100">
                        <div
                          className="h-full bg-brand-600 rounded-full"
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                    </div>
                    <SeverityBadge severity={district.severity} />
                  </div>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </DashboardCard>
  );
}
