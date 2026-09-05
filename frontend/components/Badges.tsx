import type { SignalType } from "@/lib/types";
import { confidenceLabel } from "@/lib/format";

const TYPE_STYLES: Record<SignalType, { label: string; cls: string }> = {
  BUY_STANDARD: { label: "BUY", cls: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30" },
  BUY_DOJI_REVERSAL: { label: "DOJI", cls: "bg-violet-500/15 text-violet-300 border-violet-500/30" },
  PUT: { label: "PUT", cls: "bg-red-500/15 text-red-300 border-red-500/30" },
};

export function TypeBadge({ type }: { type: SignalType }) {
  const s = TYPE_STYLES[type] ?? { label: type, cls: "bg-slate-500/15 text-slate-300" };
  return (
    <span className={`inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-semibold ${s.cls}`}>
      {s.label}
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
