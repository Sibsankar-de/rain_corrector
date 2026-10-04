"use client";

/** Model registry page: versions, metadata and promotion controls. */

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { DashboardCard } from "@/components/DashboardCard";
import { DataTable, type DataTableColumn } from "@/components/DataTable";
import { ErrorState, EmptyState, SkeletonTable } from "@/components/states";
import { formatDateTime, formatMillimetres, formatScore } from "@/lib/format";
import { invalidationKeys, queryKeys } from "@/lib/query-keys";
import { modelService } from "@/services";
import type { ModelVersion } from "@/types/api";

import { ModelHealthCard, TrainingRunsCard } from "./ModelHealthCards";

const STATUS_BADGE: Record<string, string> = {
  active: "bg-emerald-50 text-emerald-800 border-emerald-200",
  candidate: "bg-slate-100 text-slate-700 border-slate-200",
  validated: "bg-sky-50 text-sky-800 border-sky-200",
  archived: "bg-slate-50 text-slate-500 border-slate-200",
  rejected: "bg-red-50 text-red-800 border-red-200"
};

export function ModelRegistryView() {
  const queryClient = useQueryClient();
  const [selectedVersion, setSelectedVersion] = useState<string | null>(null);
  const [promotionError, setPromotionError] = useState<string | null>(null);

  const versions = useQuery({
    queryKey: queryKeys.modelVersions({ pageSize: 50 }),
    queryFn: async ({ signal }) => {
      const page = await modelService.versions({ pageSize: 50 }, signal);
      return page.items;
    }
  });

  const runs = useQuery({
    queryKey: queryKeys.trainingRuns(20),
    queryFn: ({ signal }) => modelService.trainingRuns(20, signal)
  });

  const detail = useQuery({
    queryKey: queryKeys.modelVersion(selectedVersion ?? ""),
    queryFn: ({ signal }) => modelService.version(selectedVersion ?? "", signal),
    enabled: selectedVersion !== null
  });

  const promote = useMutation({
    mutationFn: (version: string) => modelService.promote(version, "auto_promote_if_better"),
    onSuccess: () => {
      setPromotionError(null);
      void queryClient.invalidateQueries({ queryKey: invalidationKeys.allModels });
      void queryClient.invalidateQueries({ queryKey: invalidationKeys.allDashboard });
    },
    onError: (error) =>
      setPromotionError(error instanceof Error ? error.message : "Promotion failed.")
  });

  const columns: DataTableColumn<ModelVersion>[] = [
    {
      key: "version",
      header: "Version",
      render: (row) => (
        <div>
          <p className="font-mono text-sm text-ink">{row.version}</p>
          <p className="text-2xs text-ink-faint">{row.model_name}</p>
        </div>
      )
    },
    {
      key: "status",
      header: "Status",
      render: (row) => (
        <span
          className={`rounded-full border px-1.5 py-0.5 text-2xs ${STATUS_BADGE[row.status] ?? ""}`}
        >
          {row.status}
        </span>
      )
    },
    {
      key: "trained",
      header: "Trained",
      render: (row) => (
        <span className="font-mono text-2xs text-ink-muted">{formatDateTime(row.trained_at)}</span>
      )
    },
    {
      key: "features",
      header: "Features",
      align: "right",
      render: (row) => (
        <span className="font-mono tabular-nums text-ink-muted">{row.features.length}</span>
      )
    },
    {
      key: "framework",
      header: "Framework",
      align: "right",
      render: (row) => (
        <span className="font-mono text-2xs text-ink-faint">{row.framework_version}</span>
      )
    },
    {
      key: "actions",
      header: "",
      align: "right",
      render: (row) => (
        <div className="flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={() => setSelectedVersion(row.version)}
            className="btn-secondary py-1 px-2.5 text-2xs"
          >
            Details
          </button>
          <button
            type="button"
            onClick={() => promote.mutate(row.version)}
            disabled={promote.isPending || row.status === "active"}
            className="btn-primary py-1 px-2.5 text-2xs disabled:opacity-40"
          >
            {row.status === "active" ? "Active" : "Promote"}
          </button>
        </div>
      )
    }
  ];

  return (
    <div className="space-y-4">
      <div className="border-b border-edge pb-3">
        <h1 className="text-lg font-bold tracking-tight text-ink sm:text-xl">
          Model Registry & Artifact Lineage
        </h1>
        <p className="text-xs text-ink-muted">
          Immutable model versioning, feature inputs, offline evaluation benchmarks & zero-downtime serving promotion
        </p>
      </div>

      {promotionError ? (
        <div className="rounded-xl border border-amber-200 bg-amber-50 p-3.5" role="alert">
          <p className="text-sm font-semibold text-amber-900">Promotion refused</p>
          <p className="mt-0.5 text-xs text-amber-800">{promotionError}</p>
        </div>
      ) : null}

      <div className="grid gap-4 xl:grid-cols-3">
        <div className="xl:col-span-2">
          <DashboardCard
            title="Model versions"
            description="Artifacts are immutable; promoting a version swaps what the API serves"
            bodyClassName="p-0"
          >
            {versions.isLoading ? (
              <SkeletonTable rows={6} />
            ) : versions.error ? (
              <ErrorState error={versions.error} onRetry={() => versions.refetch()} />
            ) : (versions.data?.length ?? 0) === 0 ? (
              <EmptyState
                title="No model versions registered"
                description="Run scripts/run_training.py to train the first version."
              />
            ) : (
              <DataTable
                columns={columns}
                rows={versions.data ?? []}
                rowKey={(row) => row.version}
                caption="Registered model versions with status, feature count and framework"
              />
            )}
          </DashboardCard>
        </div>

        <div className="space-y-4">
          <DashboardCard title="Version detail" description={selectedVersion ?? "Select a version"}>
            {selectedVersion === null ? (
              <EmptyState
                title="Nothing selected"
                description="Choose a version to inspect its model card."
              />
            ) : detail.isLoading ? (
              <SkeletonTable rows={5} />
            ) : detail.error ? (
              <ErrorState error={detail.error} onRetry={() => detail.refetch()} />
            ) : detail.data ? (
              <ModelCardDetail version={detail.data} />
            ) : null}
          </DashboardCard>
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <div className="xl:col-span-2">
          <TrainingRunsCard runs={runs.data ?? []} />
        </div>
        <ModelHealthCard
          models={(versions.data ?? []).map((version) => ({
            model_name: version.model_name,
            version: version.version,
            status: version.status,
            trained_at: version.trained_at,
            mae_mm: null,
            rmse_mm: null,
            sample_size: 0,
            is_loaded: false
          }))}
        />
      </div>
    </div>
  );
}

function ModelCardDetail({
  version
}: {
  version: Awaited<ReturnType<typeof modelService.version>>;
}) {
  const metrics = version.metrics as
    | { test?: Record<string, { mae_mm?: number; rmse_mm?: number }> }
    | undefined;
  const testScores = metrics?.test ?? {};

  return (
    <div className="space-y-3 text-sm">
      <dl className="grid grid-cols-2 gap-3">
        <div>
          <dt className="data-label">Version</dt>
          <dd className="font-mono text-ink">{version.version}</dd>
        </div>
        <div>
          <dt className="data-label">Status</dt>
          <dd className="text-ink">{version.status}</dd>
        </div>
        <div>
          <dt className="data-label">Trained</dt>
          <dd className="font-mono text-xs text-ink">{formatDateTime(version.trained_at)}</dd>
        </div>
        <div>
          <dt className="data-label">Activated</dt>
          <dd className="font-mono text-xs text-ink">{formatDateTime(version.activated_at)}</dd>
        </div>
        <div>
          <dt className="data-label">Training data</dt>
          <dd className="font-mono text-2xs text-ink-muted">
            {version.training_data_start?.slice(0, 10) ?? "—"} →{" "}
            {version.training_data_end?.slice(0, 10) ?? "—"}
          </dd>
        </div>
        <div>
          <dt className="data-label">Framework</dt>
          <dd className="font-mono text-2xs text-ink-muted">{version.framework_version}</dd>
        </div>
      </dl>

      <div>
        <p className="data-label mb-1.5">Held-out test scores</p>
        {Object.keys(testScores).length === 0 ? (
          <p className="text-xs text-ink-muted">No test scores recorded in the model card.</p>
        ) : (
          <ul className="space-y-1">
            {Object.entries(testScores).map(([name, scores]) => (
              <li key={name} className="flex items-center justify-between text-xs">
                <span className="font-mono text-ink-muted">{name}</span>
                <span className="font-mono tabular-nums text-ink">
                  MAE {formatMillimetres(scores.mae_mm ?? null)} · NSE{" "}
                  {formatScore(scores.rmse_mm ?? null)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div>
        <p className="data-label mb-1.5">Features ({version.features.length})</p>
        <p className="font-mono text-2xs leading-relaxed text-ink-muted">
          {version.features.join(", ")}
        </p>
      </div>

      {version.notes ? <p className="text-2xs text-ink-faint">{version.notes}</p> : null}
    </div>
  );
}
