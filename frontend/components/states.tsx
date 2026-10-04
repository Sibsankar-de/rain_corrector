/** Loading, error and empty state primitives. */

import type { ReactNode } from "react";

import { ApiError } from "@/services/api-client";

export function LoadingState({ label = "Loading data…" }: { label?: string }) {
  return (
    <div
      className="flex items-center justify-center gap-2 py-10 text-sm text-ink-muted"
      role="status"
      aria-live="polite"
    >
      <span
        className="h-4 w-4 animate-spin rounded-full border-2 border-edge border-t-brand-600"
        aria-hidden="true"
      />
      <span>{label}</span>
    </div>
  );
}

export function SkeletonTable({ rows = 5 }: { rows?: number }) {
  return (
    <div className="space-y-2 p-4" aria-hidden="true">
      {Array.from({ length: rows }, (_, index) => (
        <div key={index} className="h-8 animate-pulse rounded bg-surface-sunken" />
      ))}
    </div>
  );
}

function describe(error: unknown): { message: string; requestId: string | null } {
  if (error instanceof ApiError) {
    return { message: error.userMessage, requestId: error.requestId };
  }
  if (error instanceof Error) return { message: error.message, requestId: null };
  return { message: "An unexpected error occurred.", requestId: null };
}

export function ErrorState({
  error,
  title = "Unable to load data",
  onRetry
}: {
  error: unknown;
  title?: string;
  onRetry?: () => void;
}) {
  const { message, requestId } = describe(error);
  return (
    <div className="m-4 rounded-card border border-red-200 bg-red-50 p-4" role="alert">
      <p className="text-sm font-semibold text-red-900">{title}</p>
      <p className="mt-1 text-sm text-red-800">{message}</p>
      {onRetry ? (
        <button
          type="button"
          onClick={onRetry}
          className="mt-3 rounded border border-red-300 bg-white px-2.5 py-1 text-xs font-medium text-red-800 hover:bg-red-100"
        >
          Retry
        </button>
      ) : null}
      {requestId ? (
        <p className="mt-2 font-mono text-2xs text-red-700/80">request id: {requestId}</p>
      ) : null}
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action
}: {
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-4 py-12 text-center">
      <div className="flex h-9 w-9 items-center justify-center rounded-full bg-surface-sunken text-ink-faint">
        <svg viewBox="0 0 20 20" className="h-5 w-5" fill="currentColor" aria-hidden="true">
          <path d="M10 2a8 8 0 100 16 8 8 0 000-16zm0 1.5a6.5 6.5 0 110 13 6.5 6.5 0 010-13zM9 5.5v5a1 1 0 002 0v-5a1 1 0 10-2 0zm0 7.25a1 1 0 100 2 1 1 0 000-2z" />
        </svg>
      </div>
      <p className="text-sm font-medium text-ink">{title}</p>
      {description ? <p className="max-w-md text-xs text-ink-muted">{description}</p> : null}
      {action}
    </div>
  );
}
