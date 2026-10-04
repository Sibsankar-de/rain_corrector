/** Model health and training history. */

import { DashboardCard } from "@/components/DashboardCard";
import { EmptyState } from "@/components/states";
import { formatDateTime, formatMillimetres, formatNumber } from "@/lib/format";
import type { ModelHealthItem, TrainingRun } from "@/types/api";

const STATUS_BADGE: Record<string, string> = {
  active: "bg-emerald-50 text-emerald-800 border-emerald-200",
  candidate: "bg-slate-100 text-slate-700 border-slate-200",
  validated: "bg-sky-50 text-sky-800 border-sky-200",
  archived: "bg-slate-50 text-slate-500 border-slate-200",
  rejected: "bg-red-50 text-red-800 border-red-200"
};

const RUN_STATUS_BADGE: Record<string, string> = {
  succeeded: "bg-emerald-50 text-emerald-800 border-emerald-200",
  failed: "bg-red-50 text-red-800 border-red-200",
  running: "bg-sky-50 text-sky-800 border-sky-200",
  pending: "bg-slate-100 text-slate-700 border-slate-200"
};

export function ModelHealthCard({ models }: { models: ModelHealthItem[] }) {
  return (
    <DashboardCard
      title="Model registry"
      description="Verification performance of each trained version"
      bodyClassName="p-0"
    >
      {models.length === 0 ? (
        <EmptyState
          title="No model versions"
          description="Run scripts/run_training.py to train and register the first version."
        />
      ) : (
        <ul className="divide-y divide-edge">
          {models.map((model) => (
            <li key={model.version} className="flex items-center justify-between gap-3 px-4 py-2.5">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-sm text-ink">{model.version}</span>
                  <span
                    className={`rounded-full border px-1.5 py-0.5 text-2xs ${
                      STATUS_BADGE[model.status] ?? STATUS_BADGE.candidate
                    }`}
                  >
                    {model.status}
                  </span>
                  {model.is_loaded ? (
                    <span className="rounded-full border border-brand-200 bg-brand-50 px-1.5 py-0.5 text-2xs text-brand-800">
                      serving
                    </span>
                  ) : null}
                </div>
                <p className="mt-0.5 font-mono text-2xs text-ink-faint">
                  trained {formatDateTime(model.trained_at)}
                </p>
              </div>
              <div className="shrink-0 text-right">
                <p className="font-mono text-sm tabular-nums text-ink">
                  {model.mae_mm === null ? "—" : formatMillimetres(model.mae_mm)}
                </p>
                <p className="font-mono text-2xs text-ink-faint">
                  n={formatNumber(model.sample_size)}
                </p>
              </div>
            </li>
          ))}
        </ul>
      )}
    </DashboardCard>
  );
}

export function TrainingRunsCard({ runs }: { runs: TrainingRun[] }) {
  return (
    <DashboardCard
      title="Training runs"
      description="Most recent pipeline executions"
      bodyClassName="p-0"
    >
      {runs.length === 0 ? (
        <EmptyState
          title="No training runs recorded"
          description="Runs appear here once the pipeline completes."
        />
      ) : (
        <ul className="divide-y divide-edge">
          {runs.map((run) => (
            <li key={run.run_id} className="px-4 py-2.5">
              <div className="flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <p className="truncate font-mono text-xs text-ink">{run.run_id}</p>
                  <p className="mt-0.5 text-2xs text-ink-faint">
                    {run.best_model_name ?? "no model selected"}
                    {run.created_model_version ? ` · produced ${run.created_model_version}` : ""}
                    {run.duration_seconds ? ` · ${run.duration_seconds.toFixed(1)}s` : ""}
                  </p>
                </div>
                <span
                  className={`shrink-0 rounded-full border px-1.5 py-0.5 text-2xs ${
                    RUN_STATUS_BADGE[run.status] ?? RUN_STATUS_BADGE.pending
                  }`}
                >
                  {run.status}
                </span>
              </div>
              {run.error_message ? (
                <p className="mt-1 text-2xs text-red-700">{run.error_message.slice(0, 200)}</p>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </DashboardCard>
  );
}
