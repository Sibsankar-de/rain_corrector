/** Recharts wrappers for the dashboard. */

"use client";

import {
  Area,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";

import { formatDay, formatMillimetres, formatPercent } from "@/lib/format";
import { SEVERITY_STYLES } from "@/lib/severity";
import type { SeverityDistribution } from "@/types/api";

const AXIS = {
  stroke: "#94a3b8",
  fontSize: 11,
  tickLine: false,
  axisLine: false
} as const;

const TOOLTIP_STYLE = {
  backgroundColor: "#ffffff",
  border: "1px solid #e2e8f0",
  borderRadius: "0.5rem",
  fontSize: "0.75rem",
  boxShadow: "0 4px 12px rgb(15 23 42 / 0.08)"
} as const;

export interface RainfallTrendChartProps {
  data: { timestamp: string; value: number; lower: number | null; upper: number | null }[];
  height?: number;
  showBand?: boolean;
}

/** Mean predicted rainfall per issuance, with the 10th–90th percentile band. */
export function RainfallTrendChart({
  data,
  height = 240,
  showBand = true
}: RainfallTrendChartProps) {
  if (data.length === 0) {
    return <ChartPlaceholder message="No forecast series in this window." height={height} />;
  }

  const rows = data.map((point) => ({
    label: formatDay(point.timestamp),
    forecast: point.value,
    lower: showBand ? point.lower : null,
    upper: showBand ? point.upper : null
  }));

  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: -18 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
        <XAxis dataKey="label" {...AXIS} interval="preserveStartEnd" />
        <YAxis {...AXIS} width={44} unit="" />
        <Tooltip
          contentStyle={TOOLTIP_STYLE}
          formatter={(value: number, name: string) => [formatMillimetres(value), name]}
        />
        <Legend wrapperStyle={{ fontSize: "0.7rem" }} />
        {showBand ? (
          <>
            <Area
              dataKey="upper"
              stroke="none"
              fill="#bfdbfe"
              fillOpacity={0.35}
              name="90th pct"
              isAnimationActive={false}
            />
            <Area
              dataKey="lower"
              stroke="none"
              fill="#ffffff"
              fillOpacity={0.75}
              name="10th pct"
              isAnimationActive={false}
            />
          </>
        ) : null}
        <Line
          type="monotone"
          dataKey="forecast"
          stroke="#2563eb"
          strokeWidth={2}
          dot={false}
          name="Mean forecast"
          isAnimationActive={false}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}

export interface ObservedRainfallChartProps {
  data: { observed_at: string; mean_rainfall_mm: number; total_rainfall_mm: number }[];
  height?: number;
}

export function ObservedRainfallChart({ data, height = 240 }: ObservedRainfallChartProps) {
  if (data.length === 0) {
    return <ChartPlaceholder message="No observations in this window." height={height} />;
  }
  const rows = data.map((item) => ({
    label: formatDay(item.observed_at),
    mean: item.mean_rainfall_mm
  }));

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: -18 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
        <XAxis dataKey="label" {...AXIS} interval="preserveStartEnd" />
        <YAxis {...AXIS} width={44} />
        <Tooltip
          contentStyle={TOOLTIP_STYLE}
          cursor={{ fill: "#f1f5f9" }}
          formatter={(value: number) => [formatMillimetres(value), "District mean"]}
        />
        <Bar
          dataKey="mean"
          fill="#0f766e"
          radius={[3, 3, 0, 0]}
          name="District mean"
          isAnimationActive={false}
        />
      </BarChart>
    </ResponsiveContainer>
  );
}

export interface SeverityDistributionChartProps {
  data: SeverityDistribution[];
  height?: number;
}

export function SeverityDistributionChart({ data, height = 200 }: SeverityDistributionChartProps) {
  if (data.length === 0) {
    return <ChartPlaceholder message="No forecasts issued yet." height={height} />;
  }

  const rows = data.map((entry) => ({
    label: SEVERITY_STYLES[entry.severity]?.label ?? entry.severity,
    count: entry.count,
    fill: SEVERITY_STYLES[entry.severity]?.color ?? "#94a3b8"
  }));

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 16, bottom: 0, left: 8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" horizontal={false} />
        <XAxis type="number" {...AXIS} allowDecimals={false} />
        <YAxis type="category" dataKey="label" {...AXIS} width={92} />
        <Tooltip
          contentStyle={TOOLTIP_STYLE}
          cursor={{ fill: "#f1f5f9" }}
          formatter={(value: number) => [value.toLocaleString("en-GB"), "Forecasts"]}
        />
        <Bar dataKey="count" radius={[0, 3, 3, 0]} isAnimationActive={false}>
          {rows.map((row) => (
            <Cell key={row.label} fill={row.fill} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

export interface SkillByLeadChartProps {
  data: Record<string, { sample_size: number; mean_absolute_error_mm: number; rmse_mm: number }>;
  height?: number;
  thresholdMm?: number;
}

/** MAE and RMSE per lead-time bucket; the event threshold is drawn for context. */
export function SkillByLeadChart({ data, height = 220, thresholdMm = 15 }: SkillByLeadChartProps) {
  const rows = Object.entries(data).map(([bucket, values]) => ({
    label: bucket,
    mae: values.mean_absolute_error_mm,
    rmse: values.rmse_mm
  }));

  if (rows.length === 0) {
    return <ChartPlaceholder message="No verified forecasts in this window." height={height} />;
  }

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: -18 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
        <XAxis dataKey="label" {...AXIS} />
        <YAxis {...AXIS} width={44} />
        <Tooltip
          contentStyle={TOOLTIP_STYLE}
          cursor={{ fill: "#f1f5f9" }}
          formatter={(value: number, name: string) => [formatMillimetres(value), name]}
        />
        <Legend wrapperStyle={{ fontSize: "0.7rem" }} />
        <ReferenceLine
          y={thresholdMm}
          stroke="#b91c1c"
          strokeDasharray="4 3"
          label={{ value: "heavy event", position: "right", fontSize: 10, fill: "#b91c1c" }}
        />
        <Bar
          dataKey="mae"
          fill="#2563eb"
          radius={[3, 3, 0, 0]}
          name="MAE"
          isAnimationActive={false}
        />
        <Bar
          dataKey="rmse"
          fill="#93c5fd"
          radius={[3, 3, 0, 0]}
          name="RMSE"
          isAnimationActive={false}
        />
      </BarChart>
    </ResponsiveContainer>
  );
}

export interface HitRateChartProps {
  hitRate: number | null;
  falseAlarmRatio: number | null;
  height?: number;
}

export function HitRateChart({ hitRate, falseAlarmRatio, height = 120 }: HitRateChartProps) {
  const rows = [
    { label: "Hit rate", value: hitRate, color: "#16a34a" },
    { label: "False alarm", value: falseAlarmRatio, color: "#d97706" }
  ];
  const hasData = hitRate !== null || falseAlarmRatio !== null;

  if (!hasData) {
    return <ChartPlaceholder message="No verification results yet." height={height} />;
  }

  return (
    <div className="space-y-2">
      {rows.map((row) => (
        <div key={row.label}>
          <div className="flex items-baseline justify-between text-2xs">
            <span className="text-ink-muted">{row.label}</span>
            <span className="font-mono tabular-nums text-ink">{formatPercent(row.value)}</span>
          </div>
          <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-surface-sunken">
            <div
              className="h-full rounded-full"
              style={{
                width: `${Math.min(Math.max((row.value ?? 0) * 100, 0), 100)}%`,
                backgroundColor: row.color
              }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

function ChartPlaceholder({ message, height }: { message: string; height: number }) {
  return (
    <div
      className="flex items-center justify-center rounded border border-dashed border-edge text-xs text-ink-muted"
      style={{ height }}
    >
      {message}
    </div>
  );
}
