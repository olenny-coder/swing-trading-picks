import type { SignalOutcome } from "@/lib/types";
import { OUTCOME_LABELS } from "@/lib/labels";
import { formatDate, formatPrice } from "@/lib/format";

const STYLES: Record<string, string> = {
  TARGET_HIT: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
  STOP_HIT: "bg-red-500/15 text-red-300 border-red-500/30",
  OPEN: "bg-sky-500/15 text-sky-300 border-sky-500/30",
  EXPIRED: "bg-slate-500/15 text-slate-300 border-slate-500/30",
};

/** How a past pick actually turned out. */
export function OutcomeBadge({ outcome }: { outcome: SignalOutcome | null }) {
  if (!outcome) {
    return (
      <span className="text-xs text-slate-500" title="Not evaluated yet">
        awaiting data
      </span>
    );
  }

  const style = STYLES[outcome.status] ?? STYLES.EXPIRED;
  const pnl = outcome.pnl_pct ?? 0;
  const sign = pnl > 0 ? "+" : "";

  return (
    <span
      title={
        `${OUTCOME_LABELS[outcome.status] ?? outcome.status}` +
        (outcome.exit_price != null ? ` at ${formatPrice(outcome.exit_price)}` : "") +
        (outcome.exit_date ? ` on ${formatDate(outcome.exit_date)}` : "") +
        ` · held ${outcome.bars_held} session(s)`
      }
      className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-semibold ${style}`}
    >
      {OUTCOME_LABELS[outcome.status] ?? outcome.status}
      <span className="opacity-80">
        {sign}
        {pnl.toFixed(1)}%
      </span>
    </span>
  );
}
