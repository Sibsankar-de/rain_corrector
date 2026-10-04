import type { Metadata } from "next";

import { ForecastExplorer } from "@/features/forecast/components/ForecastExplorer";

export const metadata: Metadata = { title: "Forecasts" };

export default function ForecastsPage() {
  return <ForecastExplorer />;
}
