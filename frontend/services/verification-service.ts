/** Verification endpoints: results, aggregated metrics and job runs. */

import { apiClient, type QueryValue } from "@/services/api-client";
import type { Paginated, VerificationMetrics, VerificationResult } from "@/types/api";

export interface VerificationFilters {
  modelVersion?: string;
  districtIds?: number[];
  status?: string;
  start?: string;
  end?: string;
  page?: number;
  pageSize?: number;
}

export interface RunVerificationInput {
  modelVersion?: string;
  districtIds?: number[];
  lookbackDays?: number;
  force?: boolean;
}

export interface RunVerificationResult {
  batch_uid: string;
  candidates_considered: number;
  forecasts_verified: number;
  forecasts_pending: number;
  metrics: VerificationMetrics | null;
  started_at: string;
  finished_at: string | null;
}

export const verificationService = {
  results(filters: VerificationFilters = {}, signal?: AbortSignal) {
    const query: Record<string, QueryValue> = {
      model_version: filters.modelVersion,
      district_id: filters.districtIds,
      status: filters.status,
      start: filters.start,
      end: filters.end,
      page: filters.page,
      page_size: filters.pageSize
    };
    return apiClient.get<Paginated<VerificationResult>>("/verification/results", { query, signal });
  },

  metrics(
    filters: Pick<VerificationFilters, "modelVersion" | "districtIds" | "start" | "end"> = {},
    signal?: AbortSignal
  ) {
    return apiClient.get<VerificationMetrics>("/verification/metrics", {
      query: {
        model_version: filters.modelVersion,
        district_id: filters.districtIds,
        start: filters.start,
        end: filters.end
      },
      signal
    });
  },

  forForecast(forecastId: number, signal?: AbortSignal) {
    return apiClient.get<VerificationResult>(`/verification/forecast/${forecastId}`, { signal });
  },

  batches(limit = 20, signal?: AbortSignal) {
    return apiClient.get<Record<string, unknown>[]>("/verification/batches", {
      query: { limit },
      signal
    });
  },

  run(input: RunVerificationInput = {}) {
    return apiClient.post<RunVerificationResult>("/verification/run", {
      model_version: input.modelVersion,
      district_ids: input.districtIds,
      lookback_days: input.lookbackDays,
      force: input.force
    });
  }
};
