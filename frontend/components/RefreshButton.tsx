"use client";

import { useState } from "react";
import { api } from "@/lib/api";

export function RefreshButton({ onDone }: { onDone?: () => void }) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [warnings, setWarnings] = useState<string[]>([]);

  async function refresh() {
    setBusy(true);
    setMessage("Pulling latest market data…");
    setWarnings([]);
    try {
      await api.refreshData();
      let done = false;
      // Poll up to ~6 minutes (120 x 3s) for the background pull to finish.
      for (let i = 0; i < 120; i++) {
        await new Promise((r) => setTimeout(r, 3000));
        const s = await api.refreshStatus();
        if (!s.running) {
          if (s.error) {
            setMessage(`Refresh error: ${s.error}`);
          } else if (s.result) {
            const r = s.result;
            const intraday = r.intraday_bars ?? 0;
            setMessage(
              `Done — ${r.bars.toLocaleString()} daily bars · ${intraday.toLocaleString()} 4-hour candles · ${r.tickers} tickers via ${r.refinement_source ?? r.provider} (signal date ${r.signal_date}).`,
            );
            // A refresh that loads no 4-hour candles looks like success but leaves
            // every setup refused, so say so rather than showing a green "Done".
            setWarnings(
              intraday === 0
                ? [
                    "No 4-hour candles were loaded — every setup will be reported as No Trade until they are.",
                    ...(r.warnings ?? []),
                  ]
                : (r.warnings ?? []),
            );
          } else {
            setMessage("Refresh finished.");
          }
          done = true;
          break;
        }
      }
      if (!done) setMessage("Refresh is still running in the background.");
      onDone?.();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Refresh failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col items-start gap-1 sm:items-end">
      <button
        onClick={refresh}
        disabled={busy}
        className="min-h-[44px] rounded-lg border border-emerald-600/60 bg-emerald-600/10 px-4 text-sm font-medium text-emerald-300 hover:bg-emerald-600/20 disabled:opacity-50"
      >
        {busy ? "Refreshing…" : "↻ Refresh data"}
      </button>
      {message && <span className="max-w-xs text-xs text-slate-400">{message}</span>}
      {warnings.map((warning) => (
        <span
          key={warning}
          className="max-w-xs rounded border border-amber-500/40 bg-amber-500/5 px-2 py-1 text-[11px] leading-relaxed text-amber-200"
        >
          {warning}
        </span>
      ))}
    </div>
  );
}
