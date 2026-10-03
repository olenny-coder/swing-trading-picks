import type { Summary } from "@/lib/types";
import { SETUP_CODES, SETUP_LABELS } from "@/lib/types";
import { formatPct, formatPrice } from "@/lib/format";

function Card({ label, value, accent }: { label: string; value: string; accent?: string }) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
      <div className="text-xs uppercase tracking-wide text-slate-400">{label}</div>
      <div className={`mt-1 text-2xl font-bold ${accent ?? "text-slate-100"}`}>{value}</div>
    </div>
  );
}

export function SummaryCards({ summary }: { summary: Summary | null }) {
  if (!summary) return null;
  const n = (v: number | null | undefined) => (v ?? 0);
  const regimeColor =
    summary.regime === "bullish"
      ? "text-emerald-400"
      : summary.regime === "bearish"
        ? "text-red-400"
        : "text-amber-400";

  const setupCounts = summary.setup_counts ?? {};

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <Card label="Buy Signals" value={String(n(summary.total_buys))} accent="text-emerald-400" />
        <Card label="Sell Signals" value={String(n(summary.total_sells))} accent="text-red-400" />
        <Card
          label="Continuation"
          value={String(n(summary.total_continuation))}
          accent="text-sky-400"
        />
        <Card label="Reversals" value={String(n(summary.total_reversal))} accent="text-violet-400" />
        <Card label="Avg Confidence" value={formatPct(n(summary.avg_confidence))} />
        <Card label="Regime" value={summary.regime ?? "—"} accent={regimeColor} />
      </div>

      <div className="grid grid-cols-3 gap-3 sm:grid-cols-4 lg:grid-cols-8">
        {SETUP_CODES.map((code) => (
          <div
            key={code}
            title={SETUP_LABELS[code]}
            className="rounded-lg border border-slate-800 bg-slate-900/60 px-3 py-2"
          >
            <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
              {code}
            </div>
            <div className="text-lg font-bold text-slate-100">{n(setupCounts[code])}</div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
        <Card label="VIX" value={summary.vix ? formatPrice(summary.vix) : "—"} />
        <Card
          label="Macro Events (upcoming)"
          value={String(n(summary.upcoming_macro_events))}
          accent={n(summary.upcoming_macro_events) > 0 ? "text-amber-400" : undefined}
        />
        <Card
          label="Earnings Risk"
          value={String(n(summary.earnings_risk_count))}
          accent={n(summary.earnings_risk_count) > 0 ? "text-amber-400" : undefined}
        />
        <Card label="High Confidence" value={String(n(summary.high_confidence_count))} />
      </div>
    </div>
  );
}
