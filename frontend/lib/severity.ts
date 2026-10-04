/** Severity presentation tokens shared by the map, charts, tables and legend. */

import type { Severity } from "@/types/api";

export interface SeverityStyle {
  label: string;
  color: string;
  textClass: string;
  badgeClass: string;
  dotClass: string;
}

export const SEVERITY_ORDER: Severity[] = [
  "none",
  "light",
  "moderate",
  "heavy",
  "very_heavy",
  "extreme"
];

export const SEVERITY_STYLES: Record<Severity, SeverityStyle> = {
  none: {
    label: "No rain",
    color: "#e2e8f0",
    textClass: "text-slate-500",
    badgeClass: "bg-slate-100 text-slate-700 border-slate-200",
    dotClass: "bg-slate-300"
  },
  light: {
    label: "Light",
    color: "#60a5fa",
    textClass: "text-blue-500",
    badgeClass: "bg-blue-50 text-blue-700 border-blue-200",
    dotClass: "bg-blue-400"
  },
  moderate: {
    label: "Moderate",
    color: "#2563eb",
    textClass: "text-blue-700",
    badgeClass: "bg-blue-100 text-blue-800 border-blue-200",
    dotClass: "bg-blue-600"
  },
  heavy: {
    label: "Heavy",
    color: "#7c3aed",
    textClass: "text-violet-700",
    badgeClass: "bg-violet-50 text-violet-800 border-violet-200",
    dotClass: "bg-violet-600"
  },
  very_heavy: {
    label: "Very heavy",
    color: "#c026d3",
    textClass: "text-fuchsia-700",
    badgeClass: "bg-fuchsia-50 text-fuchsia-800 border-fuchsia-200",
    dotClass: "bg-fuchsia-600"
  },
  extreme: {
    label: "Extremely heavy",
    color: "#b91c1c",
    textClass: "text-red-700",
    badgeClass: "bg-red-50 text-red-800 border-red-200",
    dotClass: "bg-red-700"
  }
};

const UNKNOWN_SEVERITY: SeverityStyle = {
  label: "Unknown",
  color: "#94a3b8",
  textClass: "text-slate-500",
  badgeClass: "bg-slate-100 text-slate-700 border-slate-200",
  dotClass: "bg-slate-400"
};

export function severityStyle(severity: string | null | undefined): SeverityStyle {
  if (!severity) return UNKNOWN_SEVERITY;
  return SEVERITY_STYLES[severity as Severity] ?? UNKNOWN_SEVERITY;
}

export const ALERT_SEVERITY_STYLES: Record<
  string,
  { label: string; badgeClass: string; dotClass: string }
> = {
  info: {
    label: "Info",
    badgeClass: "bg-sky-50 text-sky-800 border-sky-200",
    dotClass: "bg-sky-500"
  },
  warning: {
    label: "Warning",
    badgeClass: "bg-amber-50 text-amber-900 border-amber-200",
    dotClass: "bg-amber-500"
  },
  severe: {
    label: "Severe",
    badgeClass: "bg-orange-50 text-orange-900 border-orange-200",
    dotClass: "bg-orange-600"
  },
  critical: {
    label: "Critical",
    badgeClass: "bg-red-50 text-red-900 border-red-200",
    dotClass: "bg-red-600"
  }
};
