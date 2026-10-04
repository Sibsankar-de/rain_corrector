/** Reusable card container with a consistent header and body. */

import type { ReactNode } from "react";

export interface DashboardCardProps {
  title: string;
  description?: string;
  actions?: ReactNode;
  footer?: ReactNode;
  className?: string;
  bodyClassName?: string;
  children: ReactNode;
}

export function DashboardCard({
  title,
  description,
  actions,
  footer,
  className = "",
  bodyClassName = "",
  children
}: DashboardCardProps) {
  return (
    <section className={`card flex flex-col ${className}`} aria-label={title}>
      <header className="card-header">
        <div className="min-w-0">
          <h2 className="card-title">{title}</h2>
          {description ? <p className="mt-0.5 text-xs text-ink-muted">{description}</p> : null}
        </div>
        {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
      </header>
      <div className={`card-body flex-1 ${bodyClassName}`}>{children}</div>
      {footer ? (
        <footer className="border-t border-edge px-4 py-2 text-xs text-ink-muted">{footer}</footer>
      ) : null}
    </section>
  );
}
