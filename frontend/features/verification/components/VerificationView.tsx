"use client";

/** Verification page: metrics, per-forecast results and job-triggerable runs. */

import { useMemo, useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Play, ShieldCheck } from "lucide-react";

import { DashboardCard } from "@/components/DashboardCard";
import { DataTable, type DataTableColumn } from "@/components/DataTable";
import { DataTablePagination } from "@/components/DataTablePagination";
import { ErrorState, EmptyState, SkeletonTable } from "@/components/states";
import { formatDateTime, formatMillimetres, formatNumber } from "@/lib/format";
import { invalidationKeys, queryKeys } from "@/lib/query-keys";
import { verificationService, type VerificationFilters } from "@/services";
import type { VerificationResult } from "@/types/api";

import { VerificationCard } from "@/features/dashboard/components/VerificationCard";

export function VerificationView() {
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [statusFilter, setStatusFilter] = useState<string>("verified");

  const filters: VerificationFilters = useMemo(
    () => ({ page, pageSize, status: statusFilter || undefined }),
    [page, pageSize, statusFilter]
  );

  const metrics = useQuery({
    queryKey: queryKeys.verificationMetrics({}),
    queryFn: ({ signal }) => verificationService.metrics({}, signal)
  });

  const results = useQuery({
    queryKey: queryKeys.verificationResults(filters),
    queryFn: ({ signal }) => verificationService.results(filters, signal)
  });

  const batches = useQuery({
    queryKey: queryKeys.verificationBatches(10),
    queryFn: ({ signal }) => verificationService.batches(10, signal),
    enabled: false
  });

  const runVerification = useMutation({
    mutationFn: () => verificationService.run({ lookbackDays: 30 }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: invalidationKeys.allVerification });
      void queryClient.invalidateQueries({ queryKey: invalidationKeys.allDashboard });
      void batches.refetch();
    }
  });

  const columns: DataTableColumn<VerificationResult>[] = [
    {
      key: "forecast",
      header: "Forecast",
      align: "right",
      render: (row) => <span className="font-mono tabular-nums text-ink">#{row.forecast_id}</span>
    },
    {
      key: "forecast_mm",
      header: "Forecast",
      align: "right",
      render: (row) => (
        <span className="font-mono tabular-nums text-ink">
          {formatMillimetres(row.forecast_rainfall_mm)}
        </span>
      )
    },
    {
      key: "observed_mm",
      header: "Observed",
      align: "right",
      render: (row) => (
        <span className="font-mono tabular-nums text-ink">
          {row.observed_rainfall_mm === null ? "—" : formatMillimetres(row.observed_rainfall_mm)}
        </span>
      )
    },
    {
      key: "error",
      header: "Error",
      align: "right",
      render: (row) => (
        <span
          className={`font-mono tabular-nums font-semibold ${
            row.error_mm === null
              ? "text-ink-faint"
              : Math.abs(row.error_mm) <= 2
                ? "text-emerald-700"
                : Math.abs(row.error_mm) <= 7
                  ? "text-amber-700"
                  : "text-red-700"
          }`}
        >
          {row.error_mm === null ? "—" : formatMillimetres(row.error_mm)}
        </span>
      )
    },
    {
      key: "outcome",
      header: "Outcome",
      render: (row) => <VerificationOutcome result={row} />
    },
    {
      key: "observed_at",
      header: "Verified",
      render: (row) => (
        <span className="font-mono text-2xs text-ink-faint">{formatDateTime(row.verified_at)}</span>
      )
    }
  ];

  return (
    <div className="space-y-4">
      {/* Title */}
      <div className="border-b border-edge pb-3">
        <h1 className="text-lg font-bold tracking-tight text-ink sm:text-xl">
          Forecast Verification & Skill Metrics
        </h1>
        <p className="text-xs text-ink-muted">
          Evaluating predictive accuracy against ground telemetry observations (MAE, RMSE, Critical Success Index & Brier score)
        </p>
      </div>

      {metrics.isLoading ? (
        <div className="h-64 animate-pulse rounded-card bg-surface-sunken" />
      ) : metrics.error ? (
        <ErrorState error={metrics.error} onRetry={() => metrics.refetch()} />
      ) : metrics.data ? (
        <VerificationCard metrics={metrics.data} />
      ) : null}

      <div className="grid gap-4 xl:grid-cols-3">
        <div className="xl:col-span-2">
          <DashboardCard
            title="Verification results"
            description={`${formatNumber(results.data?.meta.total ?? 0)} scored forecasts`}
            bodyClassName="p-0"
            actions={
              <label className="flex items-center gap-1.5 text-2xs text-ink-muted">
                <span>Status</span>
                <select
                  value={statusFilter}
                  onChange={(event) => {
                    setStatusFilter(event.target.value);
                    setPage(1);
                  }}
                  className="rounded-lg border border-edge bg-surface-raised px-2 py-1 text-2xs font-medium text-ink"
                >
                  <option value="">All</option>
                  <option value="verified">Verified</option>
                  <option value="missing_observation">Missing observation</option>
                  <option value="pending_observation">Pending</option>
                </select>
              </label>
            }
            footer={
              results.data ? (
                <DataTablePagination
                  page={results.data.meta.page}
                  pageSize={results.data.meta.page_size}
                  total={results.data.meta.total}
                  totalPages={results.data.meta.total_pages}
                  onPageChange={setPage}
                  onPageSizeChange={(size) => {
                    setPageSize(size);
                    setPage(1);
                  }}
                  disabled={results.isFetching}
                />
              ) : null
            }
          >
            {results.isLoading ? (
              <SkeletonTable rows={8} />
            ) : results.error ? (
              <ErrorState error={results.error} onRetry={() => results.refetch()} />
            ) : (results.data?.items.length ?? 0) === 0 ? (
              <EmptyState
                title="No verification results"
                description="Run verification after a forecast target period has elapsed."
              />
            ) : (
              <DataTable
                columns={columns}
                rows={results.data?.items ?? []}
                rowKey={(row) => String(row.id)}
                dense
                caption="Per-forecast verification results with forecast, observed and error values"
              />
            )}
          </DashboardCard>
        </div>

        <DashboardCard
          title="Verification jobs"
          description="Scores forecasts whose target period has passed"
          actions={
            <button
              type="button"
              onClick={() => runVerification.mutate()}
              disabled={runVerification.isPending}
              className="btn-primary py-1 px-2.5 text-2xs"
            >
              {runVerification.isPending ? (
                <>
                  <span className="h-3 w-3 animate-spin rounded-full border border-white border-t-transparent" />
                  <span>Running…</span>
                </>
              ) : (
                <>
                  <Play className="h-3 w-3" />
                  <span>Run now</span>
                </>
              )}
            </button>
          }
          bodyClassName="p-0"
        >
          {runVerification.isSuccess ? (
            <p className="border-b border-emerald-200 bg-emerald-50 px-4 py-2 text-2xs text-emerald-800">
              Scored {runVerification.data.forecasts_verified} forecasts,{" "}
              {runVerification.data.forecasts_pending} still pending.
            </p>
          ) : null}
          {runVerification.error ? (
            <p className="border-b border-red-200 bg-red-50 px-4 py-2 text-2xs text-red-800">
              {runVerification.error.message}
            </p>
          ) : null}

          {batches.data && batches.data.length > 0 ? (
            <ul className="divide-y divide-edge">
              {batches.data.map((batch) => (
                <li key={String(batch.batch_uid)} className="px-4 py-2.5 hover:bg-surface-sunken/40 transition">
                  <p className="font-mono text-2xs font-semibold text-ink">{String(batch.batch_uid)}</p>
                  <p className="mt-0.5 text-2xs text-ink-faint">
                    {String(batch.triggered_by)} · verified {String(batch.forecasts_verified)} ·
                    pending {String(batch.forecasts_pending)} ·{" "}
                    {formatDateTime(String(batch.started_at))}
                  </p>
                </li>
              ))}
            </ul>
          ) : (
            <div className="px-4 py-6 text-center text-xs text-ink-muted">
              Job history loads when verification is first run from this page.
            </div>
          )}
        </DashboardCard>
      </div>
    </div>
  );
}

function VerificationOutcome({ result }: { result: VerificationResult }) {
  if (result.status !== "verified") {
    return <span className="text-xs text-ink-muted">{result.status.replace(/_/g, " ")}</span>;
  }
  if (result.hit)
    return (
      <OutcomeBadge className="border-emerald-200 bg-emerald-50 text-emerald-800 font-semibold">hit</OutcomeBadge>
    );
  if (result.missed)
    return <OutcomeBadge className="border-red-200 bg-red-50 text-red-800 font-semibold">missed</OutcomeBadge>;
  if (result.false_alarm) {
    return (
      <OutcomeBadge className="border-amber-200 bg-amber-50 text-amber-900 font-semibold">
        false alarm
      </OutcomeBadge>
    );
  }
  return (
    <OutcomeBadge className="border-slate-200 bg-slate-100 text-slate-700">no event</OutcomeBadge>
  );
}

function OutcomeBadge({ className, children }: { className: string; children: ReactNode }) {
  return (
    <span className={`rounded-full border px-2 py-0.5 text-2xs ${className}`}>{children}</span>
  );
}
