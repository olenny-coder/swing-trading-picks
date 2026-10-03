import type { SetupCode, SignalType } from "@/lib/types";
import { SETUP_LABELS } from "@/lib/types";
import { confidenceLabel } from "@/lib/format";

const TYPE_STYLES: Record<SignalType, { label: string; cls: string }> = {
  BUY: { label: "BUY", cls: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30" },
  SELL: { label: "SELL", cls: "bg-red-500/15 text-red-300 border-red-500/30" },
};

export function TypeBadge({ type }: { type: SignalType }) {
  const s = TYPE_STYLES[type] ?? { label: type, cls: "bg-slate-500/15 text-slate-300" };
  return (
    <span className={`inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-semibold ${s.cls}`}>
      {s.label}
    </span>
  );
}

/** The setup code is the primary label (UC1, UC2, DC1, DC2, UR1, DR1, UR2, DR2). */
export function SetupBadge({ setup, type }: { setup: SetupCode; type: SignalType }) {
  const cls =
    type === "BUY"
      ? "bg-emerald-500/15 text-emerald-300 border-emerald-500/30"
      : "bg-red-500/15 text-red-300 border-red-500/30";
  return (
    <span
      title={SETUP_LABELS[setup] ?? setup}
      className={`inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-bold tracking-wide ${cls}`}
    >
      {setup}
    </span>
  );
}

export function ConfidenceBadge({ value }: { value: number }) {
  const label = confidenceLabel(value);
  const cls =
    label === "High"
      ? "bg-emerald-500/15 text-emerald-300"
      : label === "Medium"
        ? "bg-amber-500/15 text-amber-300"
        : "bg-red-500/15 text-red-300";
  return (
    <span className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs font-semibold ${cls}`}>
      {Math.round(value)}
      <span className="opacity-60">· {label}</span>
    </span>
  );
}

// --- LLM research agent -----------------------------------------------------

const SENTIMENT_STYLES: Record<string, string> = {
  bullish: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
  bearish: "bg-red-500/15 text-red-300 border-red-500/30",
  neutral: "bg-slate-500/15 text-slate-300 border-slate-500/30",
  mixed: "bg-amber-500/15 text-amber-300 border-amber-500/30",
};

export function sentimentClass(sentiment: string): string {
  return SENTIMENT_STYLES[sentiment] ?? SENTIMENT_STYLES.neutral;
}

/** The research agent's read on the stock (not the trade). */
export function SentimentBadge({ sentiment }: { sentiment: string }) {
  return (
    <span
      title={`LLM sentiment: ${sentiment}`}
      className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-semibold ${sentimentClass(sentiment)}`}
    >
      <span aria-hidden="true">◆</span>
      {sentiment}
    </span>
  );
}

/** Engine confidence -> LLM-adjusted confidence, with the signed delta. */
export function AdjustedConfidence({
  base,
  adjusted,
}: {
  base: number;
  adjusted: number;
}) {
  const delta = Math.round((adjusted - base) * 10) / 10;
  const color =
    delta > 0 ? "text-emerald-400" : delta < 0 ? "text-red-400" : "text-slate-400";
  return (
    <span className="inline-flex items-center gap-1 text-xs">
      <span className="text-slate-400">{Math.round(base)}</span>
      <span className="text-slate-500" aria-hidden="true">
        →
      </span>
      <span className="font-semibold text-slate-100">{Math.round(adjusted)}</span>
      <span className={color}>
        ({delta > 0 ? "+" : ""}
        {delta})
      </span>
    </span>
  );
}
