import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = { title: "Page not found" };

export default function NotFound() {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-20 text-center">
      <p className="font-mono text-3xl font-semibold text-ink">404</p>
      <p className="text-sm text-ink-muted">That page does not exist.</p>
      <Link href="/" className="text-sm font-medium text-brand-700 underline underline-offset-2">
        Back to the dashboard
      </Link>
    </div>
  );
}
