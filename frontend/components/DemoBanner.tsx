import Link from "next/link";

/**
 * Shown whenever the API returned the synthetic demo dataset — i.e. the viewer
 * is not signed in. Real signals are only ever served to a signed-in admin.
 */
export function DemoBanner({ className = "" }: { className?: string }) {
  return (
    <div
      className={`flex flex-wrap items-center gap-x-2 gap-y-1 rounded-xl border border-sky-500/30 bg-sky-500/5 px-4 py-3 text-xs text-sky-200 ${className}`}
    >
      <span className="rounded bg-sky-500/20 px-1.5 py-0.5 font-semibold uppercase tracking-wide">
        Demo
      </span>
      <span>
        You are viewing a <strong>synthetic sample</strong> generated from simulated market data —
        not live signals.
      </span>
      <Link href="/login" className="underline hover:text-white">
        Sign in as admin
      </Link>
      <span className="text-sky-300/60">to see the live shortlist.</span>
    </div>
  );
}
