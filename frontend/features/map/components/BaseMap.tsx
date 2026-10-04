/**
 * Base map surface.
 *
 * Uses OpenStreetMap raster tiles exclusively. The provider is configuration
 * driven through `NEXT_PUBLIC_MAP_TILE_URL`, so any OSM-compatible provider can
 * be substituted without touching this component. No API key is used and none
 * is exposed to the browser.
 */

import type { ReactNode } from "react";
import { MapContainer, TileLayer } from "react-leaflet";
import type { LatLngBoundsExpression } from "leaflet";

import { config } from "@/lib/config";

export const INDIA_CENTER: [number, number] = [22.5, 79.0];
export const INDIA_BOUNDS: LatLngBoundsExpression = [
  [6.0, 68.0],
  [36.5, 97.5]
];

export interface BaseMapProps {
  children?: ReactNode;
  center?: [number, number];
  zoom?: number;
  bounds?: LatLngBoundsExpression;
  className?: string;
  ariaLabel?: string;
}

export function BaseMap({
  children,
  center = INDIA_CENTER,
  zoom = 5,
  bounds,
  className = "h-96 w-full",
  ariaLabel = "Rainfall forecast map of India"
}: BaseMapProps) {
  return (
    <div className={`relative overflow-hidden rounded-card border border-edge ${className}`}>
      <span className="sr-only" role="img" aria-label={ariaLabel}>
        {ariaLabel}
      </span>
      <MapContainer
        center={center}
        zoom={zoom}
        minZoom={4}
        maxZoom={config.map.maxZoom}
        bounds={bounds}
        scrollWheelZoom
        className="h-full w-full"
        attributionControl
      >
        <TileLayer
          url={config.map.tileUrl}
          attribution={config.map.attribution}
          maxZoom={config.map.maxZoom}
          crossOrigin=""
        />
        {children}
      </MapContainer>
    </div>
  );
}
