import type { AccuracyResponse, Timeframe } from "@/lib/types";
import { SETUP_LABELS, TIMEFRAME_LABELS, type SetupCode } from "@/lib/types";

function Stat({
  label,
  value,
  hint,
  accent,
}: {
  label: string;
  value: string;
  hint?: string;
  accent?: string;
}) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
      <div className="text-xs uppercase tracking-wide text-slate-400">{label}</div>
      <div className={`mt-1 text-2xl font-bold ${accent ?? "text-slate-100"}`}>{value}</div>
      {hint && <div className="mt-0.5 text-[11px] text-slate-500">{hint}</div>}
    </div>
  );
}

/**
 * How the picks actually turned out.
 *
 * A pick counts as a win when price reached the target before the stop. When a
 * single candle spans both levels the stop is assumed to have been hit first, so
 * the number is deliberately conservative.
 */
export function AccuracyPanel({
  accuracy,
  timeframe,
}: {
  accuracy: AccuracyResponse | null;
  timeframe: Timeframe;
}) {
  if (!accuracy || accuracy.evaluated === 0) {
    return (
      <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4 text-sm text-slate-400">
        No {TIMEFRAME_LABELS[timeframe].toLowerCase()} picks have been evaluated yet. Results
        appear once a pick has had time to reach its target or its stop.
      </div>
    );
  }

  const decided = accuracy.decided;
  const winRate = accuracy.win_rate_pct;
  const rateColor =
    winRate == null
      ? "text-slate-100"
      : winRate >= 55
        ? "text-emerald-400"
        : winRate >= 45
          ? "text-amber-400"
          : "text-red-400";

  const fmt = (value: number | null) =>
    value == null ? "—" : `${value > 0 ? "+" : ""}${value.toFixed(1)}%`;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        <Stat
          label="Hit rate"
          value={winRate == null ? "—" : `${winRate.toFixed(0)}%`}
          hint={`${accuracy.target_hit} of ${decided} decided picks reached target`}
          accent={rateColor}
        />
        <Stat
          label="Average result"
          value={fmt(accuracy.avg_pnl_pct)}
          hint="across every evaluated pick"
        />
        <Stat
          label="Average win"
          value={fmt(accuracy.avg_win_pct)}
          hint="when the target was reached"
          accent="text-emerald-400"
        />
        <Stat
          label="Average loss"
          value={fmt(accuracy.avg_loss_pct)}
          hint="when the stop was reached"
          accent="text-red-400"
        />
        <Stat
          label="Evaluated"
          value={String(accuracy.evaluated)}
          hint={`${accuracy.open} still open · ${accuracy.expired} expired unresolved`}
        />
      </div>

      {accuracy.by_setup.length > 0 && (
        <div className="overflow-hidden rounded-xl border border-slate-800 bg-slate-900/60">
          <div className="border-b border-slate-800 px-4 py-3 text-sm font-semibold">
            Hit rate by setup ({TIMEFRAME_LABELS[timeframe]})
          </div>
          {/* Phones: one card per setup. A five-column table would need
              horizontal scrolling on a 375px screen. */}
          <ul className="divide-y divide-slate-800/60 md:hidden">
            {accuracy.by_setup.map((row) => (
              <li key={row.setup} className="px-4 py-3">
                <div className="flex items-baseline justify-between gap-3">
                  <span className="font-mono font-semibold text-slate-200">{row.setup}</span>
                  <span className="font-mono text-sm">
                    {row.win_rate_pct == null ? "—" : `${row.win_rate_pct.toFixed(0)}%`}
                  </span>
                </div>
                <p className="mt-0.5 text-[11px] leading-relaxed text-slate-500">
                  {SETUP_LABELS[row.setup as SetupCode] ?? ""}
                </p>
                <p className="mt-1 text-xs leading-relaxed text-slate-400">
                  {row.total} pick{row.total === 1 ? "" : "s"} ·{" "}
                  <span className="text-emerald-400">{row.TARGET_HIT} reached target</span> ·{" "}
                  <span className="text-red-400">{row.STOP_HIT} reached stop</span>
                </p>
              </li>
            ))}
          </ul>

          <div className="hidden overflow-x-auto md:block">
            <table className="w-full min-w-[520px] text-left text-sm">
              <thead className="bg-slate-900/80 text-xs uppercase tracking-wide text-slate-400">
                <tr>
                  <th className="px-4 py-2">Setup</th>
                  <th className="px-4 py-2">Picks</th>
                  <th className="px-4 py-2">Target reached</th>
                  <th className="px-4 py-2">Stop reached</th>
                  <th className="px-4 py-2">Hit rate</th>
                </tr>
              </thead>
              <tbody>
                {accuracy.by_setup.map((row) => (
                  <tr key={row.setup} className="border-t border-slate-800/60">
                    <td className="px-4 py-2">
                      <span className="font-mono font-semibold text-slate-200">{row.setup}</span>
                      <div className="text-[11px] text-slate-500">
                        {SETUP_LABELS[row.setup as SetupCode] ?? ""}
                      </div>
                    </td>
                    <td className="px-4 py-2 font-mono">{row.total}</td>
                    <td className="px-4 py-2 font-mono text-emerald-400">{row.TARGET_HIT}</td>
                    <td className="px-4 py-2 font-mono text-red-400">{row.STOP_HIT}</td>
                    <td className="px-4 py-2 font-mono">
                      {row.win_rate_pct == null ? "—" : `${row.win_rate_pct.toFixed(0)}%`}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <p className="text-xs leading-relaxed text-slate-500">
        A win means price reached the target before the stop. When one candle spans both levels the
        stop is counted first, so this figure is deliberately conservative.
      </p>
    </div>
  );
}
