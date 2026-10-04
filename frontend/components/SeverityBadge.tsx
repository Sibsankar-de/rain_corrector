/** Severity badge and dot. */

import { severityStyle } from "@/lib/severity";

export function SeverityBadge({
  severity,
  className = ""
}: {
  severity: string;
  className?: string;
}) {
  const style = severityStyle(severity);
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-2xs font-medium ${style.badgeClass} ${className}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${style.dotClass}`} aria-hidden="true" />
      {style.label}
    </span>
  );
}

export function SeverityDot({ severity, title }: { severity: string; title?: string }) {
  const style = severityStyle(severity);
  return (
    <span
      className={`inline-block h-2 w-2 rounded-full ${style.dotClass}`}
      title={title ?? style.label}
    />
  );
}
