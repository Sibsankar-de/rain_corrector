/** Alert endpoints. */

import { apiClient, type QueryValue } from "@/services/api-client";
import type { Alert, Paginated } from "@/types/api";

export interface AlertFilters {
  status?: string;
  severity?: string;
  districtIds?: number[];
  validAt?: string;
  page?: number;
  pageSize?: number;
}

export const alertService = {
  list(filters: AlertFilters = {}, signal?: AbortSignal) {
    const query: Record<string, QueryValue> = {
      status: filters.status,
      severity: filters.severity,
      district_id: filters.districtIds,
      valid_at: filters.validAt,
      page: filters.page,
      page_size: filters.pageSize
    };
    return apiClient.get<Paginated<Alert>>("/alerts", { query, signal });
  },

  summary(signal?: AbortSignal) {
    return apiClient.get<Record<string, number>>("/alerts/summary", { signal });
  },

  get(alertId: number, signal?: AbortSignal) {
    return apiClient.get<Alert>(`/alerts/${alertId}`, { signal });
  },

  updateStatus(alertId: number, status: string, apiKey?: string) {
    return apiClient.patch<Alert>(`/alerts/${alertId}`, { status }, { apiKey });
  }
};
