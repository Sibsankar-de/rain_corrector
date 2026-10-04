/** Geodetic helper functions for coordinate calculations and nearest point lookups. */

export function haversineDistanceKm(
  lat1: number,
  lon1: number,
  lat2: number,
  lon2: number
): number {
  const R = 6371; // Earth radius in kilometers
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLon = ((lon2 - lon1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos((lat1 * Math.PI) / 180) *
      Math.cos((lat2 * Math.PI) / 180) *
      Math.sin(dLon / 2) *
      Math.sin(dLon / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return R * c;
}

export function formatCoordinates(lat: number, lon: number): string {
  const latCard = lat >= 0 ? "N" : "S";
  const lonCard = lon >= 0 ? "E" : "W";
  return `${Math.abs(lat).toFixed(4)}° ${latCard}, ${Math.abs(lon).toFixed(4)}° ${lonCard}`;
}

export interface NearestItem<T> {
  item: T;
  distanceKm: number;
}

export function findNearest<T>(
  targetLat: number,
  targetLon: number,
  items: T[],
  getCoords: (item: T) => [number, number] | null
): NearestItem<T> | null {
  let nearest: NearestItem<T> | null = null;

  for (const item of items) {
    const coords = getCoords(item);
    if (!coords) continue;
    const [lat, lon] = coords;
    const distanceKm = haversineDistanceKm(targetLat, targetLon, lat, lon);
    if (!nearest || distanceKm < nearest.distanceKm) {
      nearest = { item, distanceKm };
    }
  }

  return nearest;
}
