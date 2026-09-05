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

function NavLink({ href, label, active, onClick }: { href: string; label: string; active: boolean; onClick?: () => void }) {
  return (
    <Link
      href={href}
      onClick={onClick}
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

  return (
    <header className="sticky top-0 z-50 border-b border-slate-800 bg-slate-950/90 backdrop-blur">
      <nav className="mx-auto flex w-full max-w-7xl items-center justify-between px-3 py-3 sm:px-6">
        <Link href="/" className="flex items-center gap-2" onClick={() => setOpen(false)}>
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-600 text-sm font-bold">
            ST
          </span>
          <span className="text-sm font-semibold sm:text-base">Swing Trading Picks</span>
        </Link>

        {/* Desktop links */}
        <div className="hidden items-center gap-1 md:flex">
          {PUBLIC_LINKS.map((l) => (
            <NavLink key={l.href} href={l.href} label={l.label} active={pathname === l.href} />
          ))}
          {isAdmin &&
            ADMIN_LINKS.map((l) => (
              <NavLink key={l.href} href={l.href} label={l.label} active={pathname === l.href} />
            ))}
          {isAdmin ? (
            <button
              onClick={logout}
              className="ml-2 rounded-lg border border-slate-700 px-3 py-2 text-sm text-slate-300 hover:bg-slate-800"
            >
              Log out
            </button>
          ) : (
            <Link
              href="/login"
              className="ml-2 rounded-lg border border-slate-700 px-3 py-2 text-sm text-slate-300 hover:bg-slate-800"
            >
              Admin login
            </Link>
          )}
        </div>

        {/* Mobile hamburger */}
        <button
          className="flex h-11 w-11 items-center justify-center rounded-lg border border-slate-700 md:hidden"
          aria-label="Toggle menu"
          onClick={() => setOpen((v) => !v)}
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            {open ? (
              <path d="M6 6l12 12M18 6L6 18" />
            ) : (
              <path d="M4 7h16M4 12h16M4 17h16" />
            )}
          </svg>
        </button>
      </nav>

      {open && (
        <div className="border-t border-slate-800 px-3 pb-3 md:hidden">
          {PUBLIC_LINKS.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              onClick={() => setOpen(false)}
              className={`mt-1 block rounded-lg px-3 py-3 text-base ${
                pathname === l.href ? "bg-slate-800 text-white" : "text-slate-300"
              }`}
            >
              {l.label}
            </Link>
          ))}
          {isAdmin &&
            ADMIN_LINKS.map((l) => (
              <Link
                key={l.href}
                href={l.href}
                onClick={() => setOpen(false)}
                className={`mt-1 block rounded-lg px-3 py-3 text-base ${
                  pathname === l.href ? "bg-slate-800 text-white" : "text-slate-300"
                }`}
              >
                {l.label}
              </Link>
            ))}
          {isAdmin ? (
            <button
              onClick={() => {
                logout();
                setOpen(false);
              }}
              className="mt-1 block w-full rounded-lg border border-slate-700 px-3 py-3 text-left text-base text-slate-300"
            >
              Log out
            </button>
          ) : (
            <Link
              href="/login"
              onClick={() => setOpen(false)}
              className="mt-1 block rounded-lg border border-slate-700 px-3 py-3 text-left text-base text-slate-300"
            >
              Admin login
            </Link>
          )}
        </div>
      )}
    </header>
  );
}
