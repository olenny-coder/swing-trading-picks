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
    <span className="flex flex-wrap gap-1">
      {typeof earningsDays === "number" && earningsDays <= 7 && (
        <span className="rounded bg-amber-500/15 px-1.5 py-0.5 text-[11px] text-amber-300">
          ERN {earningsDays}d
        </span>
      )}
      {macroRisk && (
        <span className="rounded bg-orange-500/15 px-1.5 py-0.5 text-[11px] text-orange-300">MACRO</span>
      )}
    </span>
  );
}

export function SignalCard({ signal }: { signal: SignalOut }) {
  const entry =
    signal.type === "SELL" && signal.option_recommendation
      ? `${formatPrice(signal.option_recommendation.premium)} (P${formatPrice(signal.option_recommendation.strike)})`
      : formatPrice(signal.entry);

  return (
    <Link
      href={`/signals/${signal.id}`}
      className="block rounded-xl border border-slate-800 bg-slate-900/60 p-4 transition hover:border-slate-700"
    >
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2">
            <span className="font-semibold text-emerald-400">{signal.ticker}</span>
            <TypeBadge type={signal.type} />
          </div>
          <div className="mt-0.5 text-xs text-slate-500">{signal.sector ?? signal.name ?? ""}</div>
        </div>
        <ConfidenceBadge value={signal.confidence} />
      </div>

      <div className="mt-3 grid grid-cols-3 gap-2 text-center">
        <div className="rounded-lg bg-slate-800/50 p-2">
          <div className="text-[11px] text-slate-400">Entry</div>
          <div className="font-mono text-sm">{entry}</div>
        </div>
        <div className="rounded-lg bg-slate-800/50 p-2">
          <div className="text-[11px] text-slate-400">Target</div>
          <div className="font-mono text-sm text-emerald-400">{formatPrice(signal.target)}</div>
        </div>
        <div className="rounded-lg bg-slate-800/50 p-2">
          <div className="text-[11px] text-slate-400">Stop</div>
          <div className="font-mono text-sm text-red-400">{formatPrice(signal.stop)}</div>
        </div>
      </div>

      <div className="mt-3 flex items-center justify-between">
        <EventFlags signal={signal} />
        <span className="text-xs text-slate-500">View chart →</span>
      </div>
    </Link>
  );
}
