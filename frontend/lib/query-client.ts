/** TanStack Query client factory. */

import { QueryClient } from "@tanstack/react-query";

import { ApiError } from "@/services/api-client";

/**
 * Retries are disabled for client errors: a 404 or 422 will not become valid by
 * trying again, and retrying them hides the real problem behind a spinner.
 */
export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        gcTime: 5 * 60_000,
        refetchOnWindowFocus: false,
        retry: (failureCount, error) => {
          if (error instanceof ApiError) {
            if (error.status >= 400 && error.status < 500) return false;
            if (error.status === 0 && failureCount < 2) return true;
            return false;
          }
          return failureCount < 2;
        }
      },
      mutations: {
        retry: false
      }
    }
  });
}
