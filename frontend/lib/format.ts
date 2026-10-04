/**
 * Display formatting.
 *
 * `en-GB` is used throughout because rainfall figures in this domain are
 * published with a decimal point and the platform is metric.
 */

const MILLIMETRES = new Intl.NumberFormat("en-GB", {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1
});

const INTEGER = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 0 });

const DATE_TIME = new Intl.DateTimeFormat("en-GB", {
  day: "2-digit",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
  timeZone: "UTC"
});

const DATE = new Intl.DateTimeFormat("en-GB", {
  day: "2-digit",
  month: "short",
  year: "numeric",
  timeZone: "UTC"
});

const DAY = new Intl.DateTimeFormat("en-GB", {
  day: "2-digit",
  month: "short",
  timeZone: "UTC"
});

function isPresent(value: number | null | undefined): value is number {
  return value !== null && value !== undefined && Number.isFinite(value);
}

export function formatMillimetres(value: number | null | undefined, digits = 1): string {
  if (!isPresent(value)) return "—";
  return `${digits === 1 ? MILLIMETRES.format(value) : value.toFixed(digits)} mm`;
}

export function formatNumber(value: number | null | undefined, digits = 0): string {
  if (!isPresent(value)) return "—";
  if (digits === 0) return INTEGER.format(value);
  return value.toLocaleString("en-GB", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits
  });
}

/** Unitless skill scores span several orders of magnitude, so 3 decimals. */
export function formatScore(value: number | null | undefined): string {
  if (!isPresent(value)) return "—";
  return value.toFixed(3);
}

export function formatPercent(value: number | null | undefined, digits = 0): string {
  if (!isPresent(value)) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : `${DATE_TIME.format(date)} UTC`;
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : DATE.format(date);
}

export function formatDay(value: string | Date): string {
  const date = typeof value === "string" ? new Date(value) : value;
  return Number.isNaN(date.getTime()) ? "—" : DAY.format(date);
}

export function formatRelativeTime(value: string | null | undefined, now = new Date()): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";

  const deltaSeconds = Math.round((date.getTime() - now.getTime()) / 1000);
  const absolute = Math.abs(deltaSeconds);
  const formatter = new Intl.RelativeTimeFormat("en-GB", { numeric: "auto" });

  if (absolute < 60) return formatter.format(deltaSeconds, "second");
  if (absolute < 3600) return formatter.format(Math.round(deltaSeconds / 60), "minute");
  if (absolute < 86_400) return formatter.format(Math.round(deltaSeconds / 3600), "hour");
  return formatter.format(Math.round(deltaSeconds / 86_400), "day");
}

export function toIsoDate(value: Date): string {
  return value.toISOString().slice(0, 10);
}

export function leadTimeLabel(hours: number): string {
  if (hours < 24) return `+${Math.round(hours)}h`;
  return `+${(hours / 24).toFixed(hours % 24 === 0 ? 0 : 1)}d`;
}
