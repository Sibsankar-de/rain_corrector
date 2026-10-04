"use client";

/** Forecast exploration: filter, page, inspect detail and lead-time values. */

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { CloudRain, Filter, SlidersHorizontal, X, Clock, Layers } from "lucide-react";

import { DashboardCard } from "@/components/DashboardCard";
import { DataTable, type DataTableColumn } from "@/components/DataTable";
import { DataTablePagination } from "@/components/DataTablePagination";
import { SeverityBadge } from "@/components/SeverityBadge";
import { ErrorState, EmptyState, SkeletonTable } from "@/components/states";
import { formatDateTime, formatMillimetres, formatNumber } from "@/lib/format";
import { queryKeys } from "@/lib/query-keys";
import { SEVERITY_ORDER, severityStyle } from "@/lib/severity";
import { forecastService, type ForecastFilters } from "@/services";
import type { Forecast, ForecastDetail } from "@/types/api";

export function ForecastExplorer() {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [severity, setSeverity] = useState<string>("");
  const [minRainfall, setMinRainfall] = useState(0);
  const [selected, setSelected] = useState<ForecastDetail | null>(null);

  const filters: ForecastFilters = useMemo(
    () => ({
      page,
      pageSize,
      severity: severity || undefined,
      minRainfallMm: minRainfall > 0 ? minRainfall : undefined
    }),
    [page, pageSize, severity, minRainfall]
  );

  const forecasts = useQuery({
    queryKey: queryKeys.forecasts(filters),
    queryFn: ({ signal }) => forecastService.list(filters, signal)
  });

  const detail = useQuery({
    queryKey: queryKeys.forecast(selected?.id ?? 0),
    queryFn: ({ signal }) => forecastService.getById(selected?.id ?? 0, signal),
    enabled: selected !== null
  });

  const columns: DataTableColumn<Forecast>[] = [
    {
      key: "district",
      header: "District",
      render: (row) => (
        <div className="min-w-0">
          <p className="truncate font-semibold text-ink">
            {row.district?.name ?? `District ${row.district_id}`}
          </p>
          <p className="font-mono text-2xs text-ink-faint">{row.district?.code}</p>
        </div>
      )
    },
    {
      key: "forecast",
      header: "Predicted 24h",
      align: "right",
      render: (row) => (
        <div>
          <p className="font-mono font-bold tabular-nums text-ink">
            {formatMillimetres(row.predicted_rainfall_mm)}
          </p>
          {row.lower_bound_mm !== null && row.upper_bound_mm !== null ? (
            <p className="font-mono text-2xs text-ink-faint">
              {formatMillimetres(row.lower_bound_mm)}–{formatMillimetres(row.upper_bound_mm)}
            </p>
          ) : null}
        </div>
      )
    },
    {
      key: "severity",
      header: "Category",
      render: (row) => <SeverityBadge severity={row.severity} />
    },
    {
      key: "target",
      header: "Target period",
      render: (row) => (
        <span className="font-mono text-xs text-ink-muted">{formatDateTime(row.target_time)}</span>
      )
    },
    {
      key: "status",
      header: "Status",
      render: (row) => (
        <span className="inline-flex rounded-md bg-surface-sunken px-2 py-0.5 text-2xs font-medium text-ink-muted">
          {row.status.replace(/_/g, " ")}
        </span>
      )
    },
    {
      key: "model",
      header: "Model",
      align: "right",
      render: (row) => (
        <span className="font-mono text-2xs font-medium text-brand-700">{row.model_version}</span>
      )
    }
  ];

  return (
    <div className="space-y-4">
      <div className="border-b border-edge pb-3">
        <h1 className="text-lg font-bold tracking-tight text-ink sm:text-xl">
          Forecast Exploration & Quantiles
        </h1>
        <p className="text-xs text-ink-muted">
          Query district-level forecasts across model runs, inspect prediction intervals and lead-time step breakdowns
        </p>
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <div className="xl:col-span-2">
          <DashboardCard
            title="Forecast detail"
            description={`${formatNumber(forecasts.data?.meta.total ?? 0)} matching forecasts`}
            bodyClassName="p-0"
            actions={
              <div className="flex flex-wrap items-center gap-2">
                <label className="flex items-center gap-1.5 text-2xs text-ink-muted">
                  <Filter className="h-3 w-3 text-ink-faint" />
                  <span>Category</span>
                  <select
                    value={severity}
                    onChange={(event) => {
                      setSeverity(event.target.value);
                      setPage(1);
                    }}
                    className="rounded-lg border border-edge bg-surface-raised px-2 py-1 text-2xs font-medium text-ink"
                  >
                    <option value="">All</option>
                    {SEVERITY_ORDER.map((value) => (
                      <option key={value} value={value}>
                        {severityStyle(value).label}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="flex items-center gap-1.5 text-2xs text-ink-muted">
                  <span>Min mm</span>
                  <input
                    type="number"
                    min={0}
                    step={0.5}
                    value={minRainfall}
                    onChange={(event) => {
                      setMinRainfall(Math.max(0, Number(event.target.value) || 0));
                      setPage(1);
                    }}
                    className="w-16 rounded-lg border border-edge bg-surface-raised px-2 py-1 font-mono text-2xs text-ink"
                  />
                </label>
              </div>
            }
            footer={
              forecasts.data ? (
                <DataTablePagination
                  page={forecasts.data.meta.page}
                  pageSize={forecasts.data.meta.page_size}
                  total={forecasts.data.meta.total}
                  totalPages={forecasts.data.meta.total_pages}
                  onPageChange={setPage}
                  onPageSizeChange={(size) => {
                    setPageSize(size);
                    setPage(1);
                  }}
                  disabled={forecasts.isFetching}
                />
              ) : null
            }
          >
            {forecasts.isLoading ? (
              <SkeletonTable rows={8} />
            ) : forecasts.error ? (
              <ErrorState error={forecasts.error} onRetry={() => forecasts.refetch()} />
            ) : (forecasts.data?.items.length ?? 0) === 0 ? (
              <EmptyState
                title="No forecasts match these filters"
                description="Widen the rainfall threshold or clear the category filter."
              />
            ) : (
              <DataTable
                columns={columns}
                rows={forecasts.data?.items ?? []}
                rowKey={(row) => String(row.id)}
                caption="Forecasts with predicted rainfall, category, target period and model version"
                onRowClick={(row) => setSelected(row as ForecastDetail)}
              />
            )}
          </DashboardCard>
        </div>

        <div className="space-y-4">
          <DashboardCard
            title="Selected forecast"
            description={
              selected
                ? `${selected.district?.name ?? "District"} · ${selected.model_version}`
                : "Pick a row to inspect"
            }
          >
            {selected === null ? (
              <EmptyState
                title="Nothing selected"
                description="Select a forecast row from the table to see its lead-time steps and confidence bands."
              />
            ) : detail.isLoading ? (
              <SkeletonTable rows={4} />
            ) : detail.error ? (
              <ErrorState error={detail.error} onRetry={() => detail.refetch()} />
            ) : detail.data ? (
              <ForecastDetailPanel detail={detail.data} />
            ) : null}
          </DashboardCard>
        </div>
      </div>
    </div>
  );
}

function ForecastDetailPanel({ detail }: { detail: ForecastDetail }) {
  const style = severityStyle(detail.severity);

  return (
    <div className="space-y-3.5">
      <div className="rounded-xl border border-edge/80 bg-surface-sunken/40 p-3">
        <div className="flex items-start justify-between">
          <div>
            <p className="text-xs font-bold text-ink">{detail.district?.name ?? "District"}</p>
            <p className="font-mono text-2xs text-ink-faint">
              {detail.district?.centroid_lat.toFixed(3)}°N, {detail.district?.centroid_lon.toFixed(3)}°E
            </p>
          </div>
          <span
            className="rounded-full px-2 py-0.5 text-2xs font-semibold"
            style={{
              backgroundColor: `${style.color}20`,
              color: style.color,
              border: `1px solid ${style.color}40`
            }}
          >
            {style.label}
          </span>
        </div>

        <div className="mt-2">
          <p className="text-2xs font-semibold uppercase tracking-wider text-ink-faint">
            Predicted 24h Accumulation
          </p>
          <p className="font-mono text-2xl font-bold tabular-nums text-ink">
            {formatMillimetres(detail.predicted_rainfall_mm)}
          </p>
        </div>

        {detail.lower_bound_mm !== null && detail.upper_bound_mm !== null ? (
          <div className="mt-1 flex items-center justify-between text-2xs text-ink-muted">
            <span>Quantile Interval (P10–P90)</span>
            <span className="font-mono font-medium text-ink">
              {formatMillimetres(detail.lower_bound_mm)} – {formatMillimetres(detail.upper_bound_mm)}
            </span>
          </div>
        ) : null}
      </div>

      <dl className="grid grid-cols-2 gap-2 text-xs">
        <div className="rounded-lg border border-edge bg-surface-raised p-2">
          <dt className="data-label">Lead time</dt>
          <dd className="font-mono font-semibold tabular-nums text-ink mt-0.5">
            {detail.lead_time_hours.toFixed(0)} h
          </dd>
        </div>
        <div className="rounded-lg border border-edge bg-surface-raised p-2">
          <dt className="data-label">Model</dt>
          <dd className="font-mono font-semibold text-brand-700 mt-0.5">
            {detail.model_version}
          </dd>
        </div>
        <div className="col-span-2 rounded-lg border border-edge bg-surface-raised p-2">
          <dt className="data-label">Target Validity Window</dt>
          <dd className="font-mono text-xs text-ink mt-0.5">
            {formatDateTime(detail.target_time)}
          </dd>
        </div>
      </dl>

      <div>
        <p className="data-label mb-2 flex items-center gap-1">
          <Clock className="h-3 w-3 text-ink-faint" />
          Lead-time steps
        </p>
        {detail.values.length === 0 ? (
          <p className="text-xs text-ink-muted italic">
            This run has a single headline horizon and no sub-daily step breakdown.
          </p>
        ) : (
          <ul className="space-y-1.5">
            {detail.values.map((value) => (
              <li
                key={value.id}
                className="flex items-center justify-between gap-2 rounded-md border border-edge bg-surface-raised px-2.5 py-1.5 text-xs"
              >
                <span className="font-mono text-2xs text-ink-muted">
                  {formatDateTime(value.step_start)} → {formatDateTime(value.step_end)}
                </span>
                <span className="font-mono font-semibold tabular-nums text-ink">
                  {formatMillimetres(value.predicted_rainfall_mm)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>

      <p className="text-2xs text-ink-faint">
        Step values sum to the headline horizon total. Verification scores this forecast once the
        target period has passed and an observation exists.
      </p>
    </div>
  );
}
