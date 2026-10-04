"use client";

/** Alerts panel with acknowledgement, so an operator can close the loop. */

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Check, CloudRain, Play } from "lucide-react";

import { DashboardCard } from "@/components/DashboardCard";
import { EmptyState } from "@/components/states";
import { formatDateTime, formatMillimetres } from "@/lib/format";
import { ALERT_SEVERITY_STYLES } from "@/lib/severity";
import { invalidationKeys } from "@/lib/query-keys";
import { alertService } from "@/services";
import type { Alert } from "@/types/api";

export interface AlertsPanelProps {
  alerts: Alert[];
  isLoading?: boolean;
  onGenerateForecast?: () => void;
  generating?: boolean;
  generateError?: string | null;
}

export function AlertsPanel({
  alerts,
  isLoading = false,
  onGenerateForecast,
  generating = false,
  generateError = null
}: AlertsPanelProps) {
  const queryClient = useQueryClient();

  const acknowledge = useMutation({
    mutationFn: (alertId: number) => alertService.updateStatus(alertId, "acknowledged"),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: invalidationKeys.allAlerts });
      void queryClient.invalidateQueries({ queryKey: invalidationKeys.allDashboard });
    }
  });

  return (
    <DashboardCard
      title="Heavy rainfall alerts"
      description="Derived from forecast severity; acknowledge to clear"
      actions={
        onGenerateForecast ? (
          <button
            type="button"
            onClick={onGenerateForecast}
            disabled={generating}
            className="btn-primary py-1 px-2.5 text-2xs"
          >
            {generating ? (
              <>
                <span className="h-3 w-3 animate-spin rounded-full border border-white border-t-transparent" />
                <span>Generating…</span>
              </>
            ) : (
              <>
                <CloudRain className="h-3.5 w-3.5" />
                <span>Run forecast now</span>
              </>
            )}
          </button>
        ) : null
      }
      bodyClassName="p-0"
    >
      {generateError ? (
        <p className="border-b border-red-200 bg-red-50 px-4 py-2 text-2xs text-red-800">
          {generateError}
        </p>
      ) : null}

      {isLoading ? (
        <p className="px-4 py-8 text-center text-sm text-ink-muted">Loading alerts…</p>
      ) : alerts.length === 0 ? (
        <EmptyState
          title="No open alerts"
          description="Alerts appear when a forecast run predicts heavy rainfall or above for a district."
        />
      ) : (
        <ul className="divide-y divide-edge">
          {alerts.map((alert) => {
            const style = ALERT_SEVERITY_STYLES[alert.severity] ?? ALERT_SEVERITY_STYLES.info!;
            return (
              <li key={alert.id} className="flex flex-col sm:flex-row sm:items-start justify-between gap-3 px-4 py-3 hover:bg-surface-sunken/40 transition">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span
                      className={`h-2 w-2 shrink-0 rounded-full ${style.dotClass}`}
                      aria-hidden="true"
                    />
                    <p className="truncate text-xs font-semibold text-ink">{alert.title}</p>
                    <span
                      className={`shrink-0 rounded-full border px-2 py-0.5 text-2xs font-medium ${style.badgeClass}`}
                    >
                      {style.label}
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-ink-muted">{alert.message}</p>
                  <p className="mt-1 font-mono text-2xs text-ink-faint">
                    {alert.district_name ?? `District ${alert.district_id}`} · valid{" "}
                    {formatDateTime(alert.valid_from)} → {formatDateTime(alert.valid_to)} ·
                    threshold {formatMillimetres(alert.threshold_mm)}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => acknowledge.mutate(alert.id)}
                  disabled={acknowledge.isPending || alert.status !== "open"}
                  className="shrink-0 self-start btn-secondary py-1 px-2.5 text-2xs"
                >
                  {alert.status === "open" ? (
                    <>
                      <Check className="h-3 w-3 text-slate-500" />
                      <span>Acknowledge</span>
                    </>
                  ) : (
                    <span>{alert.status}</span>
                  )}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </DashboardCard>
  );
}
