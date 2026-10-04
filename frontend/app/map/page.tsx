import type { Metadata } from "next";

import { MapPageClient } from "@/features/map/components/MapPageClient";

export const metadata: Metadata = { title: "Map" };

export default function MapPage() {
  return <MapPageClient />;
}
