/** Dashboard data hooks. */

import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { config } from "@/lib/config";
import { queryKeys } from "@/lib/query-keys";
import { alertService, dashboardService, modelService } from "@/services";
import type { Alert, DashboardOverview, ModelVersion, TrainingRun } from "@/types/api";

export function useDashboard(lookbackDays = 7): UseQueryResult<DashboardOverview> {
  return useQuery({
    queryKey: queryKeys.dashboard(lookbackDays),
    queryFn: ({ signal }) => dashboardService.overview(lookbackDays, signal),
    refetchInterval: config.pollingIntervalMs
  });
}

export function useModelVersions(): UseQueryResult<ModelVersion[]> {
  return useQuery({
    queryKey: queryKeys.modelVersions({ pageSize: 20 }),
    queryFn: async ({ signal }) => {
      const page = await modelService.versions({ pageSize: 20 }, signal);
      return page.items;
    },
    staleTime: 5 * 60_000
  });
}

export function useTrainingRuns(limit = 10): UseQueryResult<TrainingRun[]> {
  return useQuery({
    queryKey: queryKeys.trainingRuns(limit),
    queryFn: ({ signal }) => modelService.trainingRuns(limit, signal),
    staleTime: 5 * 60_000
  });
}

export function useOpenAlerts(limit = 20): UseQueryResult<Alert[]> {
  return useQuery({
    queryKey: queryKeys.alerts({ status: "open", pageSize: limit }),
    queryFn: async ({ signal }) => {
      const page = await alertService.list({ status: "open", pageSize: limit }, signal);
      return page.items;
    },
    refetchInterval: config.pollingIntervalMs
  });
}
