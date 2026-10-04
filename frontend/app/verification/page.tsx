import type { Metadata } from "next";

import { VerificationView } from "@/features/verification/components/VerificationView";

export const metadata: Metadata = { title: "Verification" };

export default function VerificationPage() {
  return <VerificationView />;
}
