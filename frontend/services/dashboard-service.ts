/** Dashboard and health endpoints. */

import { apiClient } from "@/services/api-client";
import type { DashboardOverview } from "@/types/api";

export interface HealthStatus {
  status: string;
  app: string;
  environment: string;
  version: string;
  checked_at: string;
}

export interface ReadinessStatus extends HealthStatus {
  database: string;
  model_loaded: boolean;
  model_version: string | null;
  available_model_versions: string[];
}

export const dashboardService = {
  overview(lookbackDays = 7, signal?: AbortSignal) {
    return apiClient.get<DashboardOverview>("/dashboard/overview", {
      query: { lookback_days: lookbackDays },
      signal
    });
  },

  health(signal?: AbortSignal) {
    return apiClient.get<HealthStatus>("/health", { signal });
  },

  readiness(signal?: AbortSignal) {
    return apiClient.get<ReadinessStatus>("/health/ready", { signal });
  }
};
