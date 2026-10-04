/** Location endpoints: regions, districts and stations. */

import { apiClient, type QueryValue } from "@/services/api-client";
import type { BoundingBox } from "@/services/forecast-service";
import type { DistrictDetail, DistrictSummary, Paginated, Region, Station } from "@/types/api";

export interface DistrictFilters {
  regionId?: number;
  search?: string;
  page?: number;
  pageSize?: number;
}

export const locationService = {
  regions(signal?: AbortSignal) {
    return apiClient.get<Region[]>("/locations/regions", { signal });
  },

  districts(filters: DistrictFilters = {}, signal?: AbortSignal) {
    const query: Record<string, QueryValue> = {
      region_id: filters.regionId,
      search: filters.search,
      page: filters.page,
      page_size: filters.pageSize
    };
    return apiClient.get<Paginated<DistrictSummary>>("/locations/districts", { query, signal });
  },

  districtsInBox(bounds: BoundingBox, signal?: AbortSignal) {
    return apiClient.get<Paginated<DistrictSummary>>("/locations/districts", {
      query: {
        min_lat: bounds.minLat,
        min_lon: bounds.minLon,
        max_lat: bounds.maxLat,
        max_lon: bounds.maxLon,
        page_size: 200
      },
      signal
    });
  },

  district(districtId: number, signal?: AbortSignal) {
    return apiClient.get<DistrictDetail>(`/locations/districts/${districtId}`, { signal });
  },

  stations(districtId?: number, signal?: AbortSignal) {
    return apiClient.get<Station[]>("/locations/stations", {
      query: { district_id: districtId },
      signal
    });
  }
};
