"use client";

import { useState, type ReactNode } from "react";

/**
 * A collapsible section: click the header to expand/collapse the body.
 * Used throughout the app so long pages can be tidied by the user.
 */
export function Collapsible({
  title,
  subtitle,
  children,
  defaultOpen = true,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <section className="overflow-hidden rounded-xl border border-slate-800 bg-slate-900/60">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left transition hover:bg-slate-800/40"
      >
        <span className="flex min-w-0 items-center gap-2">
          <span className="text-sm font-semibold">{title}</span>
          {subtitle && <span className="truncate text-xs text-slate-400">{subtitle}</span>}
        </span>
        <svg
          className={`h-4 w-4 shrink-0 text-slate-400 transition-transform duration-200 ${
            open ? "rotate-180" : ""
          }`}
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          aria-hidden="true"
        >
          <path d="M6 9l6 6 6-6" />
        </svg>
      </button>
      {open && <div className="border-t border-slate-800 px-4 py-4">{children}</div>}
    </section>
  );
}
