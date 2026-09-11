"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { useAuth } from "@/lib/auth";

const PUBLIC_LINKS = [
  { href: "/", label: "Daily View" },
  { href: "/history", label: "History" },
  { href: "/macro", label: "Macro" },
];

const ADMIN_LINKS = [{ href: "/settings", label: "Settings" }];

function NavLink({
  href,
  label,
  active,
}: {
  href: string;
  label: string;
  active: boolean;
}) {
  return (
    <Link
      href={href}
      className={`rounded-lg px-3 py-2 text-sm transition ${
        active ? "bg-slate-800 text-white" : "text-slate-300 hover:bg-slate-800/60"
      }`}
    >
      {label}
    </Link>
  );
}

export function Nav() {
  const pathname = usePathname();
  const { token, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const isAdmin = Boolean(token);
  const links = isAdmin ? [...PUBLIC_LINKS, ...ADMIN_LINKS] : PUBLIC_LINKS;

  return (
    <header className="sticky top-0 z-50 border-b border-slate-800 bg-slate-950/90 backdrop-blur">
      <nav className="mx-auto flex w-full max-w-7xl items-center justify-between gap-3 px-3 py-3 sm:px-6">
        <Link href="/" className="flex min-w-0 items-center gap-2" onClick={() => setOpen(false)}>
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-emerald-600 text-sm font-bold">
            ST
          </span>
          <span className="truncate text-sm font-semibold sm:text-base">Swing Trading Picks</span>
        </Link>

        <div className="flex items-center gap-2">
          {/* Inline links on wider screens */}
          <div className="hidden items-center gap-1 md:flex">
            {links.map((l) => (
              <NavLink key={l.href} href={l.href} label={l.label} active={pathname === l.href} />
            ))}
            {isAdmin ? (
              <button
                onClick={logout}
                className="ml-1 rounded-lg border border-slate-700 px-3 py-2 text-sm text-slate-300 hover:bg-slate-800"
              >
                Log out
              </button>
            ) : (
              <Link
                href="/login"
                className="ml-1 rounded-lg border border-slate-700 px-3 py-2 text-sm text-slate-300 hover:bg-slate-800"
              >
                Admin login
              </Link>
            )}
          </div>

          {/* Hamburger menu — available at every screen size */}
          <div className="relative">
            <button
              type="button"
              aria-label="Open navigation menu"
              aria-expanded={open}
              onClick={() => setOpen((v) => !v)}
              className="flex h-10 w-10 items-center justify-center rounded-lg border border-slate-700 text-slate-300 transition hover:bg-slate-800"
            >
              <svg
                width="20"
                height="20"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                aria-hidden="true"
              >
                {open ? (
                  <path d="M6 6l12 12M18 6L6 18" />
                ) : (
                  <path d="M4 7h16M4 12h16M4 17h16" />
                )}
              </svg>
            </button>

            {open && (
              <>
                {/* Click-outside backdrop */}
                <div
                  className="fixed inset-0 z-40"
                  aria-hidden="true"
                  onClick={() => setOpen(false)}
                />
                <div className="absolute right-0 top-full z-50 mt-2 w-60 overflow-hidden rounded-xl border border-slate-700 bg-slate-900 p-2 shadow-2xl">
                  <div className="px-3 pb-2 pt-1 text-[11px] uppercase tracking-wide text-slate-500">
                    Navigation
                  </div>
                  {links.map((l) => (
                    <Link
                      key={l.href}
                      href={l.href}
                      onClick={() => setOpen(false)}
                      className={`block rounded-lg px-3 py-3 text-sm ${
                        pathname === l.href
                          ? "bg-slate-800 text-white"
                          : "text-slate-300 hover:bg-slate-800/60"
                      }`}
                    >
                      {l.label}
                    </Link>
                  ))}

                  <div className="my-2 border-t border-slate-800" />

                  {isAdmin ? (
                    <button
                      onClick={() => {
                        logout();
                        setOpen(false);
                      }}
                      className="block w-full rounded-lg px-3 py-3 text-left text-sm text-slate-300 hover:bg-slate-800/60"
                    >
                      Log out
                    </button>
                  ) : (
                    <Link
                      href="/login"
                      onClick={() => setOpen(false)}
                      className="block rounded-lg px-3 py-3 text-sm text-slate-300 hover:bg-slate-800/60"
                    >
                      Admin login
                    </Link>
                  )}
                </div>
              </>
            )}
          </div>
        </div>
      </nav>
    </header>
  );
}
