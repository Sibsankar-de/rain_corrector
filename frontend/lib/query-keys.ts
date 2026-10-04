/** TanStack Query key factory. Centralised so invalidation cannot miss a key. */

import type { AlertFilters, ModelVersionFilters, VerificationFilters } from "@/services";
import type { ForecastFilters } from "@/services/forecast-service";

export const queryKeys = {
  health: ["health"] as const,
  readiness: ["readiness"] as const,

  dashboard: (lookbackDays: number) => ["dashboard", { lookbackDays }] as const,

  regions: ["regions"] as const,
  districts: (filters: unknown) => ["districts", filters] as const,
  district: (districtId: number) => ["districts", "detail", districtId] as const,
  stations: (districtId?: number) => ["stations", { districtId }] as const,

  forecasts: (filters: ForecastFilters) => ["forecasts", filters] as const,
  forecast: (forecastId: number) => ["forecasts", "detail", forecastId] as const,
  forecastRuns: (params: unknown) => ["forecasts", "runs", params] as const,
  mapForecasts: (params: unknown) => ["forecasts", "map", params] as const,
  legend: ["forecasts", "legend"] as const,

  verificationResults: (filters: VerificationFilters) =>
    ["verification", "results", filters] as const,
  verificationMetrics: (filters: unknown) => ["verification", "metrics", filters] as const,
  verificationBatches: (limit: number) => ["verification", "batches", limit] as const,

  modelVersions: (filters: ModelVersionFilters) => ["models", "versions", filters] as const,
  activeModel: ["models", "active"] as const,
  modelVersion: (version: string) => ["models", "versions", "detail", version] as const,
  trainingRuns: (limit: number) => ["models", "training-runs", limit] as const,

  alerts: (filters: AlertFilters) => ["alerts", filters] as const,
  alertSummary: ["alerts", "summary"] as const
};

export const invalidationKeys = {
  allForecasts: [["forecasts"]] as const,
  allVerification: [["verification"]] as const,
  allModels: [["models"]] as const,
  allAlerts: [["alerts"]] as const,
  allDashboard: [["dashboard"]] as const
};
