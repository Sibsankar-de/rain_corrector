/**
 * Public runtime configuration.
 *
 * Only variables prefixed with NEXT_PUBLIC_ reach the browser, so nothing
 * secret can be read here. The map tile provider is fully configuration
 * driven: switching to a different OpenStreetMap-compatible provider means
 * changing NEXT_PUBLIC_MAP_TILE_URL, not the code.
 */

const DEFAULT_API_BASE_URL = "http://localhost:8000/api/v1";
const DEFAULT_TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const DEFAULT_ATTRIBUTION =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';

function readNumber(value: string | undefined, fallback: number): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function readString(value: string | undefined, fallback: string): string {
  return value && value.trim().length > 0 ? value.trim() : fallback;
}

export const config = {
  apiBaseUrl: readString(process.env.NEXT_PUBLIC_API_BASE_URL, DEFAULT_API_BASE_URL),
  map: {
    tileUrl: readString(process.env.NEXT_PUBLIC_MAP_TILE_URL, DEFAULT_TILE_URL),
    attribution: readString(process.env.NEXT_PUBLIC_MAP_ATTRIBUTION, DEFAULT_ATTRIBUTION),
    providerName: readString(process.env.NEXT_PUBLIC_MAP_TILE_PROVIDER, "OpenStreetMap Standard"),
    maxZoom: readNumber(process.env.NEXT_PUBLIC_MAP_MAX_ZOOM, 19)
  },
  pollingIntervalMs: readNumber(process.env.NEXT_PUBLIC_POLL_INTERVAL_MS, 60_000)
} as const;

export type AppConfig = typeof config;
