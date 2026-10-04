"use client";

/** Application chrome: responsive sidebar navigation, mobile drawer, header and content region. */

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useState, type ReactNode } from "react";
import {
  LayoutDashboard,
  Map as MapIcon,
  CloudRain,
  ShieldCheck,
  AlertTriangle,
  Cpu,
  Menu,
  X,
  Clock,
  Radio,
  ExternalLink,
  Layers
} from "lucide-react";

import { queryKeys } from "@/lib/query-keys";
import { dashboardService } from "@/services";

interface NavItem {
  href: string;
  label: string;
  description: string;
  icon: typeof LayoutDashboard;
}

const NAV: NavItem[] = [
  {
    href: "/",
    label: "Dashboard",
    description: "Operational summary and key indicators",
    icon: LayoutDashboard
  },
  {
    href: "/map",
    label: "Forecast Map",
    description: "Interactive district precipitation map",
    icon: MapIcon
  },
  {
    href: "/forecasts",
    label: "Forecast Explorer",
    description: "Runs, quantile intervals and lead-times",
    icon: CloudRain
  },
  {
    href: "/verification",
    label: "Verification",
    description: "Forecast vs observation accuracy & skill",
    icon: ShieldCheck
  },
  {
    href: "/alerts",
    label: "Heavy Rain Alerts",
    description: "Active warnings and threshold triggers",
    icon: AlertTriangle
  },
  {
    href: "/models",
    label: "Model Registry",
    description: "Model versions, training runs and lineage",
    icon: Cpu
  }
];

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  // Close mobile drawer on route transition
  useEffect(() => {
    setMobileMenuOpen(false);
  }, [pathname]);

  const readiness = useQuery({
    queryKey: queryKeys.readiness,
    queryFn: ({ signal }) => dashboardService.readiness(signal),
    refetchInterval: 60_000,
    retry: 1
  });

  return (
    <div className="flex min-h-screen flex-col bg-surface text-ink lg:flex-row">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-50 focus:rounded-md focus:bg-brand-700 focus:px-3 focus:py-2 focus:text-sm focus:text-white"
      >
        Skip to content
      </a>

      {/* Desktop Sidebar */}
      <aside className="hidden lg:sticky lg:top-0 lg:z-30 lg:flex lg:h-screen lg:w-64 lg:shrink-0 lg:flex-col lg:border-r lg:border-edge lg:bg-surface-raised">
        <SidebarContent pathname={pathname} readiness={readiness.data} />
      </aside>

      {/* Mobile Header Bar */}
      <header className="sticky top-0 z-40 flex items-center justify-between border-b border-edge bg-surface-raised/95 px-4 py-3 backdrop-blur lg:hidden">
        <div className="flex items-center gap-2.5">
          <button
            type="button"
            onClick={() => setMobileMenuOpen(true)}
            aria-label="Open navigation menu"
            className="flex h-9 w-9 items-center justify-center rounded-lg border border-edge bg-surface-sunken text-ink hover:bg-surface transition"
          >
            <Menu className="h-5 w-5" />
          </button>
          <div className="flex items-center gap-2">
            <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-brand-700 text-white shadow-sm">
              <CloudRain className="h-4 w-4" />
            </span>
            <div>
              <p className="text-xs font-bold leading-none text-ink">Rain Corrector</p>
              <p className="text-[10px] text-ink-faint">Hydrometeorology</p>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <ReadinessBadge readiness={readiness.data} compact />
        </div>
      </header>

      {/* Mobile Drawer Overlay */}
      {mobileMenuOpen ? (
        <div className="fixed inset-0 z-50 lg:hidden" role="dialog" aria-modal="true">
          <div
            className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm transition-opacity"
            onClick={() => setMobileMenuOpen(false)}
            aria-hidden="true"
          />
          <div className="fixed inset-y-0 left-0 flex w-72 max-w-[85vw] flex-col border-r border-edge bg-surface-raised shadow-xl">
            <div className="flex items-center justify-between border-b border-edge px-4 py-3.5">
              <div className="flex items-center gap-2.5">
                <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-700 text-white shadow-sm">
                  <CloudRain className="h-4.5 w-4.5" />
                </span>
                <div>
                  <p className="text-sm font-bold text-ink">Rain Corrector</p>
                  <p className="text-2xs text-ink-faint">Operational Forecasting</p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setMobileMenuOpen(false)}
                aria-label="Close navigation menu"
                className="rounded-lg p-1.5 text-ink-muted hover:bg-surface-sunken hover:text-ink transition"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto px-3 py-4">
              <SidebarNav pathname={pathname} onNavClick={() => setMobileMenuOpen(false)} />
            </div>
            {readiness.data?.model_version ? (
              <div className="border-t border-edge p-3 bg-surface-sunken/40">
                <p className="text-2xs text-ink-faint font-medium">Serving Model</p>
                <p className="font-mono text-xs font-semibold text-brand-700">
                  {readiness.data.model_version}
                </p>
              </div>
            ) : null}
          </div>
        </div>
      ) : null}

      {/* Main Content Area */}
      <div className="flex min-w-0 flex-1 flex-col">
        {/* Top Operational Header (Desktop) */}
        <header className="hidden lg:flex items-center justify-between border-b border-edge bg-surface-raised px-6 py-3">
          <div className="min-w-0">
            <h1 className="text-sm font-semibold tracking-tight text-ink">
              Operational Precipitation Forecasting System
            </h1>
            <p className="text-2xs text-ink-muted">
              ML-enhanced hydrometeorological analysis, 24h accumulation & telemetry verification
            </p>
          </div>

          <div className="flex items-center gap-3">
            <SystemClock />
            <div className="h-4 w-px bg-edge" />
            <ReadinessBadge readiness={readiness.data} />
            {readiness.data?.model_version ? (
              <span className="inline-flex items-center gap-1.5 rounded-md border border-edge bg-surface-sunken px-2.5 py-1 font-mono text-2xs font-medium text-ink-muted">
                <Cpu className="h-3 w-3 text-brand-600" />
                {readiness.data.model_version}
              </span>
            ) : null}
          </div>
        </header>

        <main id="main-content" className="min-w-0 flex-1 px-3 py-4 sm:px-4 sm:py-5 lg:px-6 lg:py-6">
          {children}
        </main>

        <footer className="border-t border-edge bg-surface-raised px-4 py-3 text-2xs text-ink-faint sm:px-6">
          <div className="flex flex-col items-center justify-between gap-2 sm:flex-row">
            <span>
              Rain Corrector · Hydrometeorological Operational Center · Map data &copy; OpenStreetMap contributors
            </span>
            <div className="flex items-center gap-3">
              <span className="inline-flex items-center gap-1">
                <Radio className="h-3 w-3 text-emerald-600 animate-pulse" />
                Live Ingestion Active
              </span>
              <span>CWC / CPCB / IMD Telemetry</span>
            </div>
          </div>
        </footer>
      </div>
    </div>
  );
}

function SidebarContent({
  pathname,
  readiness
}: {
  pathname: string;
  readiness:
    | { status: string; database: string; model_version: string | null; model_loaded: boolean }
    | undefined;
}) {
  return (
    <div className="flex h-full flex-col">
      {/* Brand Header */}
      <div className="flex items-center gap-3 border-b border-edge px-5 py-4">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-brand-700 text-white shadow-sm ring-1 ring-brand-800/10">
          <CloudRain className="h-5 w-5" />
        </span>
        <div className="min-w-0">
          <p className="truncate text-sm font-bold tracking-tight text-ink">Rain Corrector</p>
          <p className="truncate text-2xs text-ink-muted">Disaster Management Portal</p>
        </div>
      </div>

      {/* Navigation List */}
      <div className="flex-1 overflow-y-auto px-3 py-4">
        <SidebarNav pathname={pathname} />
      </div>

      {/* System Status Pill Box */}
      <div className="border-t border-edge p-3 bg-surface-sunken/30">
        <div className="rounded-lg border border-edge bg-surface-raised p-2.5 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-2xs font-semibold uppercase tracking-wider text-ink-faint">
              Engine Status
            </span>
            <span
              className={`h-2 w-2 rounded-full ${
                readiness?.model_loaded ? "bg-emerald-500" : "bg-amber-500"
              }`}
            />
          </div>
          <p className="mt-1 font-mono text-2xs font-medium text-ink">
            {readiness?.model_version ? `Model: ${readiness.model_version}` : "Model: Standby"}
          </p>
          <p className="mt-0.5 text-[10px] text-ink-muted">
            {readiness?.database === "ok" ? "DB telemetry connected" : "Connecting…"}
          </p>
        </div>
      </div>
    </div>
  );
}

function SidebarNav({
  pathname,
  onNavClick
}: {
  pathname: string;
  onNavClick?: () => void;
}) {
  return (
    <nav aria-label="Primary navigation" className="space-y-1">
      {NAV.map((item) => {
        const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
        const Icon = item.icon;
        return (
          <Link
            key={item.href}
            href={item.href}
            onClick={onNavClick}
            aria-current={active ? "page" : undefined}
            className={`group flex items-center gap-3 rounded-lg px-3 py-2.5 text-xs font-medium transition ${
              active
                ? "bg-brand-50 text-brand-900 shadow-sm ring-1 ring-brand-200/80"
                : "text-ink-muted hover:bg-surface-sunken hover:text-ink"
            }`}
          >
            <Icon
              className={`h-4.5 w-4.5 shrink-0 transition ${
                active ? "text-brand-700" : "text-ink-faint group-hover:text-ink"
              }`}
            />
            <div className="min-w-0 flex-1">
              <span className="block truncate font-semibold">{item.label}</span>
              <span
                className={`block truncate text-[11px] font-normal ${
                  active ? "text-brand-800/80" : "text-ink-faint"
                }`}
              >
                {item.description}
              </span>
            </div>
          </Link>
        );
      })}
    </nav>
  );
}

function ReadinessBadge({
  readiness,
  compact = false
}: {
  readiness:
    | { status: string; database: string; model_version: string | null; model_loaded: boolean }
    | undefined;
  compact?: boolean;
}) {
  const degraded = readiness ? readiness.database !== "ok" || !readiness.model_loaded : false;

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-2xs font-medium shadow-sm ${
        degraded
          ? "border-amber-200 bg-amber-50 text-amber-900"
          : "border-emerald-200 bg-emerald-50 text-emerald-800"
      }`}
    >
      <span className="relative flex h-2 w-2">
        <span
          className={`absolute inline-flex h-full w-full rounded-full opacity-75 ${
            degraded ? "bg-amber-400" : "bg-emerald-400 animate-ping"
          }`}
        />
        <span
          className={`relative inline-flex h-2 w-2 rounded-full ${
            degraded ? "bg-amber-500" : "bg-emerald-600"
          }`}
        />
      </span>
      <span>
        {compact
          ? readiness
            ? degraded
              ? "Degraded"
              : "Active"
            : "Checking"
          : readiness
            ? degraded
              ? "Degraded Mode"
              : "System Operational"
            : "Verifying Services"}
      </span>
    </span>
  );
}

function SystemClock() {
  const [time, setTime] = useState<string>("");

  useEffect(() => {
    const update = () => {
      const now = new Date();
      setTime(
        now.toLocaleTimeString("en-GB", {
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
          timeZone: "UTC"
        }) + " UTC"
      );
    };
    update();
    const interval = setInterval(update, 1000);
    return () => clearInterval(interval);
  }, []);

  if (!time) return null;

  return (
    <span className="inline-flex items-center gap-1.5 text-2xs font-mono text-ink-muted">
      <Clock className="h-3 w-3 text-ink-faint" />
      {time}
    </span>
  );
}
