/** Data hooks for the map feature. */

import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { queryKeys } from "@/lib/query-keys";
import { forecastService, locationService, type BoundingBox } from "@/services";
import type { DistrictSummary, Forecast, ForecastRun, LegendEntry, Station } from "@/types/api";

export interface MapRunParams {
  runUid?: string;
  minRainfallMm?: number;
}

export function useMapForecasts(params: MapRunParams = {}): UseQueryResult<Forecast[]> {
  return useQuery({
    queryKey: queryKeys.mapForecasts(params),
    queryFn: ({ signal }) => forecastService.mapForecasts(params, signal),
    staleTime: 60_000
  });
}

export function useForecastRuns(limit = 20): UseQueryResult<{ items: ForecastRun[] }> {
  return useQuery({
    queryKey: queryKeys.forecastRuns({ limit }),
    queryFn: async ({ signal }) => {
      const page = await forecastService.listRuns({ pageSize: limit }, signal);
      return { items: page.items };
    },
    staleTime: 5 * 60_000
  });
}

export function useSeverityLegend(): UseQueryResult<LegendEntry[]> {
  return useQuery({
    queryKey: queryKeys.legend,
    queryFn: ({ signal }) => forecastService.legend(signal),
    staleTime: 30 * 60_000
  });
}

export function useStations(): UseQueryResult<Station[]> {
  return useQuery({
    queryKey: queryKeys.stations(),
    queryFn: ({ signal }) => locationService.stations(undefined, signal),
    staleTime: 10 * 60_000
  });
}

export function useDistrictsInBox(
  bounds: BoundingBox
): UseQueryResult<{ items: { id: number }[] }> {
  return useQuery({
    queryKey: queryKeys.districts(bounds),
    queryFn: ({ signal }) => locationService.districtsInBox(bounds, signal),
    staleTime: 10 * 60_000
  });
}

export function useAllDistricts(): UseQueryResult<DistrictSummary[]> {
  return useQuery({
    queryKey: ["locations", "districts", "all"],
    queryFn: async ({ signal }) => {
      let page = await locationService.districts({ page: 1, pageSize: 200 }, signal);
      const all = [...page.items];
      let currentPage = 1;
      while (page.meta.has_next && all.length < page.meta.total) {
        currentPage += 1;
        page = await locationService.districts({ page: currentPage, pageSize: 200 }, signal);
        all.push(...page.items);
      }
      return all;
    },
    staleTime: 30 * 60_000
  });
}

