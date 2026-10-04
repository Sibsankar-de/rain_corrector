/** Forecast, forecast run and legend endpoints. */

import { apiClient, type QueryValue } from "@/services/api-client";
import type { Forecast, ForecastDetail, ForecastRun, LegendEntry, Paginated } from "@/types/api";

export interface ForecastFilters {
  districtId?: number[];
  regionId?: number;
  modelVersion?: string;
  minRainfallMm?: number;
  severity?: string;
  issuedFrom?: string;
  issuedTo?: string;
  targetFrom?: string;
  targetTo?: string;
  minLat?: number;
  minLon?: number;
  maxLat?: number;
  maxLon?: number;
  page?: number;
  pageSize?: number;
}

export interface BoundingBox {
  minLat: number;
  minLon: number;
  maxLat: number;
  maxLon: number;
}

export interface GenerateForecastInput {
  modelVersion?: string;
  issuedAt?: string;
  horizonHours?: number;
  stepHours?: number;
  districtIds?: number[];
}

export interface GenerateForecastResult {
  run_uid: string;
  model_version: string;
  issued_at: string;
  forecasts_created: number;
  valid_from: string;
  valid_to: string;
}

function toQuery(filters: ForecastFilters): Record<string, QueryValue> {
  return {
    district_id: filters.districtId,
    region_id: filters.regionId,
    model_version: filters.modelVersion,
    min_rainfall_mm: filters.minRainfallMm,
    severity: filters.severity,
    issued_from: filters.issuedFrom,
    issued_to: filters.issuedTo,
    target_from: filters.targetFrom,
    target_to: filters.targetTo,
    min_lat: filters.minLat,
    min_lon: filters.minLon,
    max_lat: filters.maxLat,
    max_lon: filters.maxLon,
    page: filters.page,
    page_size: filters.pageSize
  };
}

export const forecastService = {
  list(filters: ForecastFilters = {}, signal?: AbortSignal) {
    return apiClient.get<Paginated<Forecast>>("/forecasts", { query: toQuery(filters), signal });
  },

  getById(forecastId: number, signal?: AbortSignal) {
    return apiClient.get<ForecastDetail>(`/forecasts/${forecastId}`, { signal });
  },

  listRuns(
    params: {
      modelVersion?: string;
      issuedFrom?: string;
      issuedTo?: string;
      page?: number;
      pageSize?: number;
    } = {},
    signal?: AbortSignal
  ) {
    return apiClient.get<Paginated<ForecastRun>>("/forecasts/runs", {
      query: {
        model_version: params.modelVersion,
        issued_from: params.issuedFrom,
        issued_to: params.issuedTo,
        page: params.page,
        page_size: params.pageSize
      },
      signal
    });
  },

  getRun(runUid: string, signal?: AbortSignal) {
    return apiClient.get<ForecastRun>(`/forecasts/runs/${encodeURIComponent(runUid)}`, { signal });
  },

  mapForecasts(
    params: { runUid?: string; minRainfallMm?: number } & Partial<BoundingBox> = {},
    signal?: AbortSignal
  ) {
    return apiClient.get<Forecast[]>("/forecasts/map", {
      query: {
        run_uid: params.runUid,
        min_rainfall_mm: params.minRainfallMm,
        min_lat: params.minLat,
        min_lon: params.minLon,
        max_lat: params.maxLat,
        max_lon: params.maxLon
      },
      signal
    });
  },

  legend(signal?: AbortSignal) {
    return apiClient.get<LegendEntry[]>("/forecasts/legend", { signal });
  },

  generate(input: GenerateForecastInput = {}) {
    return apiClient.post<GenerateForecastResult>("/forecasts/generate", {
      model_version: input.modelVersion,
      issued_at: input.issuedAt,
      horizon_hours: input.horizonHours,
      step_hours: input.stepHours,
      district_ids: input.districtIds
    });
  }
};
