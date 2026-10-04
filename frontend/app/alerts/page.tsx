import type { Metadata } from "next";

import { AlertsView } from "@/features/alerts/components/AlertsView";

export const metadata: Metadata = { title: "Alerts" };

export default function AlertsPage() {
  return <AlertsView />;
}
