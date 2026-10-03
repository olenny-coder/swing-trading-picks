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
