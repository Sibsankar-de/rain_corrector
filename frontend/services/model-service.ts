/** Model registry endpoints: versions, training runs and promotion. */

import { apiClient, type QueryValue } from "@/services/api-client";
import type { ModelVersion, ModelVersionDetail, Paginated, TrainingRun } from "@/types/api";

export interface ModelVersionFilters {
  status?: string;
  page?: number;
  pageSize?: number;
}

export interface PromotionResult {
  activated_version: string;
  previous_version: string | null;
  reloaded: boolean;
  policy: string;
}

export const modelService = {
  versions(filters: ModelVersionFilters = {}, signal?: AbortSignal) {
    const query: Record<string, QueryValue> = {
      status: filters.status,
      page: filters.page,
      page_size: filters.pageSize
    };
    return apiClient.get<Paginated<ModelVersion>>("/models/versions", { query, signal });
  },

  active(signal?: AbortSignal) {
    return apiClient.get<ModelVersion | null>("/models/active", { signal });
  },

  version(version: string, signal?: AbortSignal) {
    return apiClient.get<ModelVersionDetail>(`/models/versions/${encodeURIComponent(version)}`, {
      signal
    });
  },

  trainingRuns(limit = 50, signal?: AbortSignal) {
    return apiClient.get<TrainingRun[]>("/models/training-runs", { query: { limit }, signal });
  },

  policies(signal?: AbortSignal) {
    return apiClient.get<string[]>("/models/policies", { signal });
  },

  promote(targetVersion: string, policy?: string, apiKey?: string) {
    return apiClient.post<PromotionResult>(
      "/models/promote",
      { target_version: targetVersion, policy },
      { apiKey }
    );
  }
};
