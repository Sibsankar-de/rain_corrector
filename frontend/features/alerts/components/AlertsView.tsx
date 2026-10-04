"use client";

/** Alerts page: full alert list with status and severity filters. */

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Bell, Filter, ShieldAlert } from "lucide-react";

import { DataTable, type DataTableColumn } from "@/components/DataTable";
import { DataTablePagination } from "@/components/DataTablePagination";
import { ErrorState, EmptyState, SkeletonTable } from "@/components/states";
import { formatDateTime, formatMillimetres, formatNumber } from "@/lib/format";
import { invalidationKeys, queryKeys } from "@/lib/query-keys";
import { ALERT_SEVERITY_STYLES } from "@/lib/severity";
import { alertService, type AlertFilters } from "@/services";
import type { Alert } from "@/types/api";

const STATUSES = ["", "open", "acknowledged", "resolved"] as const;
const SEVERITIES = ["", "info", "warning", "severe", "critical"] as const;

export function AlertsView() {
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [status, setStatus] = useState<string>("open");
  const [severity, setSeverity] = useState<string>("");

  const filters: AlertFilters = {
    page,
    pageSize,
    status: status || undefined,
    severity: severity || undefined
  };
  const alerts = useQuery({
    queryKey: queryKeys.alerts(filters),
    queryFn: ({ signal }) => alertService.list(filters, signal)
  });
  const summary = useQuery({
    queryKey: queryKeys.alertSummary,
    queryFn: ({ signal }) => alertService.summary(signal)
  });

  const update = useMutation({
    mutationFn: ({ id, next }: { id: number; next: string }) => alertService.updateStatus(id, next),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: invalidationKeys.allAlerts });
      void queryClient.invalidateQueries({ queryKey: invalidationKeys.allDashboard });
    }
  });

  const columns: DataTableColumn<Alert>[] = [
    {
      key: "title",
      header: "Alert",
      render: (row) => {
        const style = ALERT_SEVERITY_STYLES[row.severity] ?? ALERT_SEVERITY_STYLES.info!;
        return (
          <div className="min-w-0 py-0.5">
            <div className="flex flex-wrap items-center gap-2">
              <span
                className={`h-2 w-2 shrink-0 rounded-full ${style.dotClass}`}
                aria-hidden="true"
              />
              <p className="truncate font-semibold text-ink">{row.title}</p>
              <span
                className={`shrink-0 rounded-full border px-2 py-0.5 text-2xs font-semibold ${style.badgeClass}`}
              >
                {style.label}
              </span>
            </div>
            <p className="mt-1 text-xs text-ink-muted">{row.message}</p>
          </div>
        );
      }
    },
    {
      key: "district",
      header: "District",
      render: (row) => (
        <div>
          <p className="text-sm font-medium text-ink">
            {row.district_name ?? `District ${row.district_id}`}
          </p>
          <p className="font-mono text-2xs text-ink-faint">
            threshold {formatMillimetres(row.threshold_mm)}
          </p>
        </div>
      )
    },
    {
      key: "window",
      header: "Valid window",
      render: (row) => (
        <div className="font-mono text-2xs text-ink-muted">
          <p>{formatDateTime(row.valid_from)}</p>
          <p className="text-ink-faint">→ {formatDateTime(row.valid_to)}</p>
        </div>
      )
    },
    {
      key: "status",
      header: "Status",
      render: (row) => (
        <select
          value={row.status}
          disabled={update.isPending}
          onChange={(event) => update.mutate({ id: row.id, next: event.target.value })}
          className="rounded-lg border border-edge bg-surface-raised px-2.5 py-1 text-xs font-medium text-ink focus:border-brand-500 focus:ring-1 focus:ring-brand-500 disabled:opacity-50"
          aria-label={`Status for ${row.title}`}
        >
          <option value="open">open</option>
          <option value="acknowledged">acknowledged</option>
          <option value="resolved">resolved</option>
        </select>
      )
    }
  ];

  const summaryEntries = Object.entries(summary.data ?? {});

  return (
    <div className="space-y-4">
      {/* Page Title */}
      <div className="border-b border-edge pb-3">
        <h1 className="text-lg font-bold tracking-tight text-ink sm:text-xl">
          Hydrometeorological Alerts
        </h1>
        <p className="text-xs text-ink-muted">
          Automated threshold triggers, district warning status & operator acknowledgements
        </p>
      </div>

      {/* Summary KPI chips */}
      {summaryEntries.length > 0 ? (
        <div className="flex flex-wrap gap-2.5">
          {summaryEntries.map(([key, count]) => {
            const style = ALERT_SEVERITY_STYLES[key] ?? ALERT_SEVERITY_STYLES.info!;
            return (
              <div key={key} className="card flex items-center gap-2 px-3.5 py-2">
                <span className={`h-2.5 w-2.5 rounded-full ${style.dotClass}`} aria-hidden="true" />
                <span className="text-xs font-medium text-ink-muted">{style.label}:</span>
                <span className="font-mono text-sm font-bold tabular-nums text-ink">{count}</span>
              </div>
            );
          })}
        </div>
      ) : null}

      <div className="card">
        <header className="card-header bg-surface-raised">
          <div>
            <h2 className="card-title">Active Alerts Register</h2>
            <p className="mt-0.5 text-xs text-ink-muted">
              {formatNumber(alerts.data?.meta.total ?? 0)} matching alert events
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <label className="flex items-center gap-1.5 text-2xs text-ink-muted">
              <span>Status</span>
              <select
                value={status}
                onChange={(event) => {
                  setStatus(event.target.value);
                  setPage(1);
                }}
                className="rounded-lg border border-edge bg-surface-raised px-2 py-1 text-2xs font-medium text-ink"
              >
                {STATUSES.map((value) => (
                  <option key={value || "all"} value={value}>
                    {value || "All"}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex items-center gap-1.5 text-2xs text-ink-muted">
              <span>Severity</span>
              <select
                value={severity}
                onChange={(event) => {
                  setSeverity(event.target.value);
                  setPage(1);
                }}
                className="rounded-lg border border-edge bg-surface-raised px-2 py-1 text-2xs font-medium text-ink"
              >
                {SEVERITIES.map((value) => (
                  <option key={value || "all"} value={value}>
                    {value || "All"}
                  </option>
                ))}
              </select>
            </label>
          </div>
        </header>

        {alerts.isLoading ? (
          <SkeletonTable rows={8} />
        ) : alerts.error ? (
          <ErrorState error={alerts.error} onRetry={() => alerts.refetch()} />
        ) : (alerts.data?.items.length ?? 0) === 0 ? (
          <EmptyState
            title="No alerts match these filters"
            description="Alerts are automatically generated when forecast models predict heavy or extreme rainfall."
          />
        ) : (
          <>
            <DataTable
              columns={columns}
              rows={alerts.data?.items ?? []}
              rowKey={(row) => String(row.id)}
              caption="Heavy rainfall alerts with district, validity window and status"
            />
            {alerts.data ? (
              <DataTablePagination
                page={alerts.data.meta.page}
                pageSize={alerts.data.meta.page_size}
                total={alerts.data.meta.total}
                totalPages={alerts.data.meta.total_pages}
                onPageChange={setPage}
                onPageSizeChange={(size) => {
                  setPageSize(size);
                  setPage(1);
                }}
                disabled={alerts.isFetching}
              />
            ) : null}
          </>
        )}
      </div>
    </div>
  );
}
