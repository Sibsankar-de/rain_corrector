import type { Metadata } from "next";

import { ModelRegistryView } from "@/features/models/components/ModelRegistryView";

export const metadata: Metadata = { title: "Models" };

export default function ModelsPage() {
  return <ModelRegistryView />;
}
