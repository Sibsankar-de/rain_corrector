"use client";

/** Verification skill summary with lead-time and severity breakdowns. */

import { useState } from "react";

import { DashboardCard } from "@/components/DashboardCard";
import { formatDateTime, formatMillimetres, formatScore } from "@/lib/format";
import { severityStyle } from "@/lib/severity";
import type { MetricGroup, VerificationMetrics } from "@/types/api";

import { HitRateChart, SkillByLeadChart } from "./ForecastChart";

export interface VerificationCardProps {
  metrics: VerificationMetrics;
  eventThresholdMm?: number;
}

type Tab = "overview" | "lead" | "severity";

export function VerificationCard({ metrics, eventThresholdMm = 15 }: VerificationCardProps) {
  const [tab, setTab] = useState<Tab>("overview");

  return (
    <DashboardCard
      title="Forecast verification"
      description={
        metrics.sample_size > 0
          ? `${metrics.sample_size.toLocaleString("en-GB")} verified forecasts · heavy event at ${eventThresholdMm} mm`
          : "No verified forecasts in this window"
      }
      actions={<TabSwitch value={tab} onChange={setTab} />}
      bodyClassName={tab === "overview" ? "space-y-4" : ""}
    >
      {metrics.sample_size === 0 ? (
        <p className="py-6 text-center text-sm text-ink-muted">
          Verification runs once a forecast target period has passed and an observation exists.
        </p>
      ) : tab === "overview" ? (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <ScoreTile label="MAE" value={formatMillimetres(metrics.mean_absolute_error_mm)} />
            <ScoreTile label="RMSE" value={formatMillimetres(metrics.rmse_mm)} />
            <ScoreTile
              label="Bias"
              value={formatMillimetres(metrics.bias_mm)}
              hint={biasHint(metrics.bias_mm)}
            />
            <ScoreTile label="NSE" value={formatScore(metrics.nash_sutcliffe)} />
          </div>
          <HitRateChart hitRate={metrics.hit_rate} falseAlarmRatio={metrics.false_alarm_ratio} />
          <p className="text-2xs text-ink-faint">
            Bias is forecast minus observed; a positive value means the model over-forecasts.
            Computed {formatDateTime(metrics.computed_at)}.
          </p>
        </div>
      ) : tab === "lead" ? (
        <SkillByLeadChart data={metrics.by_lead_bucket} thresholdMm={eventThresholdMm} />
      ) : (
        <GroupTable groups={metrics.by_severity} />
      )}
    </DashboardCard>
  );
}

function TabSwitch({ value, onChange }: { value: Tab; onChange: (tab: Tab) => void }) {
  const tabs: { key: Tab; label: string }[] = [
    { key: "overview", label: "Overview" },
    { key: "lead", label: "By lead time" },
    { key: "severity", label: "By severity" }
  ];
  return (
    <div className="flex rounded border border-edge p-0.5" role="tablist">
      {tabs.map((tab) => (
        <button
          key={tab.key}
          type="button"
          role="tab"
          aria-selected={value === tab.key}
          onClick={() => onChange(tab.key)}
          className={`rounded px-2 py-1 text-2xs font-medium ${
            value === tab.key ? "bg-brand-600 text-white" : "text-ink-muted hover:bg-surface-sunken"
          }`}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}

function ScoreTile({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded border border-edge bg-surface-sunken px-3 py-2">
      <p className="data-label">{label}</p>
      <p className="mt-0.5 font-mono text-lg tabular-nums text-ink">{value}</p>
      {hint ? <p className="text-2xs text-ink-faint">{hint}</p> : null}
    </div>
  );
}

function biasHint(bias: number | null): string | undefined {
  if (bias === null || Math.abs(bias) < 0.5) return "near unbiased";
  return bias > 0 ? "over-forecasting" : "under-forecasting";
}

/** Lead-time buckets read as-is; severity keys map to their display label. */
function groupLabel(group: string): string {
  return group.includes("-") && group.endsWith("h")
    ? group
    : (severityStyle(group)?.label ?? group);
}

function GroupTable({ groups }: { groups: Record<string, MetricGroup> }) {
  const rows = Object.entries(groups);
  if (rows.length === 0) {
    return <p className="py-6 text-center text-sm text-ink-muted">No grouped results available.</p>;
  }
  return (
    <div className="scrollbar-thin overflow-x-auto">
      <table className="w-full text-sm min-w-[340px]">
        <thead>
          <tr className="border-b border-edge">
            <th scope="col" className="data-label px-2 py-2 text-left font-medium">
              Group
            </th>
            <th scope="col" className="data-label px-2 py-2 text-right font-medium">
              n
            </th>
            <th scope="col" className="data-label px-2 py-2 text-right font-medium">
              MAE
            </th>
            <th scope="col" className="data-label px-2 py-2 text-right font-medium">
              RMSE
            </th>
            <th scope="col" className="data-label px-2 py-2 text-right font-medium">
              Bias
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([group, values]) => (
            <tr key={group} className="border-b border-edge last:border-0 hover:bg-surface-sunken/50 transition">
              <td className="px-2 py-2 text-ink font-medium">{groupLabel(group)}</td>
              <td className="px-2 py-2 text-right font-mono tabular-nums text-ink-muted">
                {values.sample_size.toLocaleString("en-GB")}
              </td>
              <td className="px-2 py-2 text-right font-mono tabular-nums text-ink font-semibold">
                {formatMillimetres(values.mean_absolute_error_mm)}
              </td>
              <td className="px-2 py-2 text-right font-mono tabular-nums text-ink">
                {formatMillimetres(values.rmse_mm)}
              </td>
              <td className="px-2 py-2 text-right font-mono tabular-nums text-ink-muted">
                {formatMillimetres(values.bias_mm)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
