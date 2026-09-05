import type { Summary } from "@/lib/types";
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

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
      <Card label="Buy Signals" value={String(n(summary.total_buys))} accent="text-emerald-400" />
      <Card label="Doji Reversals" value={String(n(summary.total_doji))} accent="text-violet-400" />
      <Card label="Put Signals" value={String(n(summary.total_puts))} accent="text-red-400" />
      <Card label="Avg Confidence" value={formatPct(n(summary.avg_confidence))} />
      <Card label="Regime" value={summary.regime ?? "—"} accent={regimeColor} />
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
    </div>
  );
}
