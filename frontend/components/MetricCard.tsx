/** Headline metric tile used across the dashboard. */

import type { ReactNode } from "react";

export interface MetricCardProps {
  label: string;
  value: string;
  unit?: string;
  hint?: ReactNode;
  tone?: "neutral" | "positive" | "caution" | "critical";
  icon?: ReactNode;
}

const TONE_TEXT: Record<NonNullable<MetricCardProps["tone"]>, string> = {
  neutral: "text-ink",
  positive: "text-emerald-700",
  caution: "text-amber-700",
  critical: "text-red-700"
};

const TONE_BG: Record<NonNullable<MetricCardProps["tone"]>, string> = {
  neutral: "bg-surface-sunken text-ink-muted",
  positive: "bg-emerald-50 text-emerald-700 border-emerald-100",
  caution: "bg-amber-50 text-amber-700 border-amber-100",
  critical: "bg-red-50 text-red-700 border-red-100"
};

export function MetricCard({ label, value, unit, hint, tone = "neutral", icon }: MetricCardProps) {
  return (
    <div className="card group relative overflow-hidden px-4 py-3.5 transition hover:border-slate-300">
      <div className="flex items-start justify-between gap-2">
        <p className="data-label">{label}</p>
        {icon ? (
          <span className={`flex h-7 w-7 items-center justify-center rounded-lg border border-transparent ${TONE_BG[tone]}`}>
            {icon}
          </span>
        ) : null}
      </div>
      <p className={`mt-1 font-mono text-2xl font-bold tracking-tight tabular-nums ${TONE_TEXT[tone]}`}>
        {value}
        {unit ? <span className="ml-1 text-sm font-normal text-ink-faint">{unit}</span> : null}
      </p>
      {hint ? <p className="mt-1 text-xs text-ink-muted truncate">{hint}</p> : null}
    </div>
  );
}
