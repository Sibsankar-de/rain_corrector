/** KPI row. Every value is read from the dashboard aggregate endpoint. */

import { Cpu, AlertTriangle, ShieldCheck, Bell, Activity, CheckCircle2, TrendingUp, Radio } from "lucide-react";

import { MetricCard } from "@/components/MetricCard";
import { formatDateTime, formatMillimetres, formatNumber, formatScore } from "@/lib/format";
import type { DashboardOverview } from "@/types/api";

export function StatusSummary({ data }: { data: DashboardOverview }) {
  const { summary, verification, status, active_model_version: modelVersion } = data;
  const skill =
    verification.mean_absolute_error_mm > 0
      ? `vs ${formatMillimetres(verification.mean_absolute_error_mm)} verified MAE`
      : "no verified forecasts yet";

  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      <MetricCard
        label="Active model"
        value={modelVersion ?? "none"}
        hint={
          data.model_loaded_version === modelVersion
            ? "Loaded and serving"
            : data.model_loaded_version
              ? `Registry holds ${data.model_loaded_version}`
              : "Not loaded in the API process"
        }
        tone={modelVersion ? "positive" : "critical"}
        icon={<Cpu className="h-4 w-4" />}
      />
      <MetricCard
        label="Districts at risk"
        value={formatNumber(summary.districts_at_risk)}
        hint="Heavy or worse in the latest run"
        tone={summary.districts_at_risk > 0 ? "caution" : "neutral"}
        icon={<AlertTriangle className="h-4 w-4" />}
      />
      <MetricCard
        label="Verified MAE"
        value={formatMillimetres(verification.mean_absolute_error_mm)}
        hint={`${formatNumber(verification.sample_size)} verified forecasts`}
        tone={verification.mean_absolute_error_mm > 0 ? "positive" : "neutral"}
        icon={<ShieldCheck className="h-4 w-4" />}
      />
      <MetricCard
        label="Open alerts"
        value={formatNumber(summary.open_alerts)}
        hint={summary.open_alerts > 0 ? "Awaiting acknowledgement" : "No unresolved alerts"}
        tone={summary.open_alerts > 0 ? "caution" : "positive"}
        icon={<Bell className="h-4 w-4" />}
      />

      <div className="card col-span-2 px-4 py-3.5 lg:col-span-4 bg-surface-raised/90">
        <dl className="grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-3 lg:grid-cols-6">
          <SummaryItem
            label="Latest run"
            value={
              data.latest_forecast_run
                ? formatDateTime(data.latest_forecast_issued_at)
                : "none issued"
            }
          />
          <SummaryItem label="Forecasts issued" value={formatNumber(status.forecasts_issued)} />
          <SummaryItem label="Forecasts verified" value={formatNumber(status.forecasts_verified)} />
          <SummaryItem
            label="Verification skill"
            value={formatScore(verification.critical_success_index)}
            hint={skill}
          />
          <SummaryItem label="Nash-Sutcliffe" value={formatScore(verification.nash_sutcliffe)} />
          <SummaryItem
            label="Latest observation"
            value={status.latest_observation ? formatDateTime(status.latest_observation) : "—"}
          />
        </dl>
      </div>
    </div>
  );
}

function SummaryItem({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="border-l border-edge pl-3 first:border-l-0">
      <dt className="data-label">{label}</dt>
      <dd className="mt-0.5 font-mono text-sm font-semibold tabular-nums text-ink">{value}</dd>
      {hint ? <dd className="text-2xs text-ink-faint truncate">{hint}</dd> : null}
    </div>
  );
}
