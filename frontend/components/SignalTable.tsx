"use client";

import Link from "next/link";
import type { SignalOut } from "@/lib/types";
import { formatPrice } from "@/lib/format";
import { ConfidenceBadge, TypeBadge } from "./Badges";

function EventFlags({ signal }: { signal: SignalOut }) {
  const flags = (signal.event_flags ?? {}) as Record<string, unknown>;
  const earningsDays = flags.earnings_in_days as number | null | undefined;
  const macroRisk = flags.macro_risk as boolean | undefined;

  return (
    <span className="inline-flex flex-wrap gap-1">
      {typeof earningsDays === "number" && earningsDays <= 7 && (
        <span className="rounded bg-amber-500/15 px-1.5 py-0.5 text-[11px] text-amber-300" title="Earnings within 7 days">
          ERN {earningsDays}d
        </span>
      )}
      {macroRisk && (
        <span className="rounded bg-orange-500/15 px-1.5 py-0.5 text-[11px] text-orange-300" title="High-impact macro event near">
          MACRO
        </span>
      )}
      {!earningsDays && !macroRisk && <span className="text-slate-600">—</span>}
    </span>
  );
}

function EntryCell({ signal }: { signal: SignalOut }) {
  if (signal.type === "PUT" && signal.option_recommendation) {
    const o = signal.option_recommendation;
    return (
      <div>
        <div className="font-mono text-sm">{formatPrice(o.premium)}</div>
        <div className="text-[11px] text-slate-400">P{formatPrice(o.strike)} put</div>
      </div>
    );
  }
  return <div className="font-mono text-sm">{formatPrice(signal.entry)}</div>;
}

export function SignalTable({ signals }: { signals: SignalOut[] }) {
  return (
    <div className="hidden overflow-x-auto rounded-xl border border-slate-800 md:block">
      <table className="w-full min-w-[760px] text-left text-sm">
        <thead className="border-b border-slate-800 bg-slate-900/80 text-xs uppercase tracking-wide text-slate-400">
          <tr>
            <th className="px-4 py-3">Ticker</th>
            <th className="px-4 py-3">Type</th>
            <th className="px-4 py-3">Entry / Option</th>
            <th className="px-4 py-3">Target</th>
            <th className="px-4 py-3">Stop</th>
            <th className="px-4 py-3">Confidence</th>
            <th className="px-4 py-3">Events</th>
            <th className="px-4 py-3">Sector</th>
            <th className="px-4 py-3"></th>
          </tr>
        </thead>
        <tbody>
          {signals.map((s) => (
            <tr key={s.id} className="border-b border-slate-800/60 hover:bg-slate-900/40">
              <td className="px-4 py-3">
                <Link href={`/signals/${s.id}`} className="font-semibold text-emerald-400 hover:underline">
                  {s.ticker}
                </Link>
                <div className="text-[11px] text-slate-500">{s.name}</div>
              </td>
              <td className="px-4 py-3">
                <TypeBadge type={s.type} />
              </td>
              <td className="px-4 py-3">
                <EntryCell signal={s} />
              </td>
              <td className="px-4 py-3 font-mono">{formatPrice(s.target)}</td>
              <td className="px-4 py-3 font-mono">{formatPrice(s.stop)}</td>
              <td className="px-4 py-3">
                <ConfidenceBadge value={s.confidence} />
              </td>
              <td className="px-4 py-3">
                <EventFlags signal={s} />
              </td>
              <td className="px-4 py-3 text-slate-400">{s.sector ?? "—"}</td>
              <td className="px-4 py-3 text-right">
                <Link href={`/signals/${s.id}`} className="text-xs text-slate-400 hover:text-white">
                  Chart →
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
