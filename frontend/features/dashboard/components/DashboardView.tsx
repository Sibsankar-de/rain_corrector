"use client";

/** Dashboard page: status, map, charts, verification, alerts and models. */

import dynamic from "next/dynamic";
import Link from "next/link";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { DashboardCard } from "@/components/DashboardCard";
import { ErrorState } from "@/components/states";
import { invalidationKeys } from "@/lib/query-keys";
import { forecastService } from "@/services";

import {
  ObservedRainfallChart,
  RainfallTrendChart,
  SeverityDistributionChart
} from "./ForecastChart";
import { StatusSummary } from "./StatusSummary";
import { TopRiskDistricts } from "./TopRiskDistricts";
import { VerificationCard } from "./VerificationCard";
import { useDashboard, useOpenAlerts, useTrainingRuns } from "../hooks/useDashboardData";
import { AlertsPanel } from "@/features/alerts/components/AlertsPanel";
import { ModelHealthCard, TrainingRunsCard } from "@/features/models/components/ModelHealthCards";

// Leaflet touches `window` during module evaluation, so the map is client-only.
const MapView = dynamic(() => import("@/features/map/components/MapView").then((m) => m.MapView), {
  ssr: false,
  loading: () => (
    <div className="card flex h-[26rem] items-center justify-center text-sm text-ink-muted">
      Loading map…
    </div>
  )
});

export function DashboardView() {
  const [lookbackDays] = useState(7);
  const queryClient = useQueryClient();
  const dashboard = useDashboard(lookbackDays);
  const alertsQuery = useOpenAlerts(8);
  const trainingRuns = useTrainingRuns(5);

  const generate = useMutation({
    mutationFn: () => forecastService.generate({ horizonHours: 24, stepHours: 24 }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: invalidationKeys.allForecasts });
      void queryClient.invalidateQueries({ queryKey: invalidationKeys.allDashboard });
      void queryClient.invalidateQueries({ queryKey: invalidationKeys.allAlerts });
    }
  });

  if (dashboard.isLoading) {
    return (
      <div className="space-y-4">
        <div className="h-24 animate-pulse rounded-card bg-surface-sunken" />
        <div className="h-96 animate-pulse rounded-card bg-surface-sunken" />
      </div>
    );
  }

  if (dashboard.error || !dashboard.data) {
    return <ErrorState error={dashboard.error} onRetry={() => dashboard.refetch()} />;
  }

  const data = dashboard.data;

  return (
    <div className="space-y-4">
      <StatusSummary data={data} />

      <MapView />

      <div className="grid gap-4 xl:grid-cols-3">
        <DashboardCard
          title="Forecast issuance trend"
          description="Mean predicted 24h rainfall per run, with the 10th–90th percentile band"
        >
          <RainfallTrendChart data={data.forecast_vs_observed_series} />
        </DashboardCard>

        <DashboardCard title="Observed rainfall" description="District mean daily accumulation">
          <ObservedRainfallChart data={data.observed_rainfall_series} />
        </DashboardCard>

        <DashboardCard title="Forecast severity mix" description="All issuances in the window">
          <SeverityDistributionChart data={data.severity_distribution} />
        </DashboardCard>
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <div className="xl:col-span-2">
          <VerificationCard metrics={data.verification} />
        </div>
        <TopRiskDistricts districts={data.top_risk_districts} />
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <div className="xl:col-span-2">
          <AlertsPanel
            alerts={alertsQuery.data ?? []}
            isLoading={alertsQuery.isLoading}
            onGenerateForecast={() => generate.mutate()}
            generating={generate.isPending}
            generateError={generate.error instanceof Error ? generate.error.message : null}
          />
        </div>
        <div className="space-y-4">
          <ModelHealthCard models={data.models} />
          <div>
            <Link
              href="/models"
              className="text-2xs font-medium text-brand-700 underline underline-offset-2 hover:text-brand-900"
            >
              View full model registry
            </Link>
          </div>
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <div className="xl:col-span-2">
          <TrainingRunsCard runs={trainingRuns.data ?? []} />
        </div>
        <DashboardCard
          title="Data provenance"
          description="What the numbers on this page are built from"
        >
          <ul className="space-y-2 text-xs text-ink-muted">
            <li>
              Model{" "}
              <span className="font-mono text-ink">{data.active_model_version ?? "none"}</span>
              {data.model_loaded_version === data.active_model_version
                ? " is loaded and serving forecasts."
                : " is registered but not loaded in the API process."}
            </li>
            <li>
              Verification covers {data.verification.sample_size.toLocaleString("en-GB")} scored
              forecasts.
            </li>
            <li>
              Latest observation:{" "}
              <span className="font-mono text-ink">
                {data.status.latest_observation
                  ? data.status.latest_observation.slice(0, 10)
                  : "none"}
              </span>
              .
            </li>
            <li>
              Records marked <span className="font-mono">synthetic</span> are demo data.
            </li>
          </ul>
        </DashboardCard>
      </div>
    </div>
  );
}
